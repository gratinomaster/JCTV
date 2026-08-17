#!/usr/bin/env python3
"""Gera EPGFULL.xml.gz com APENAS os canais que existem no NEWSWORLDNOVOS.m3u.

O guia sai enxuto: so entram os tvg-ids presentes na playlist e os programas
dentro da janela de retencao (2 dias antes ate 10 dias depois, fuso de
Pyongyang). Fontes usadas, em ordem:

  1. KORYO.TV (https://koryo.tv/schedule) para a Korean Central Television
     (KCTV). Se o endpoint do KORYO.TV estiver fora do ar, usa o snapshot
     mais recente arquivado no Internet Archive (Wayback Machine) e, se ainda
     assim nao houver dados na janela, a API diaria do Juche TV
     (https://juche-tv.vercel.app/schedules).
  2. epgshare01 (https://epgshare01.online/epgshare01/) para os demais
     canais. O arquivo e escolhido pelo pais indicado no sufixo do tvg-id
     (ex.: "...ar" -> AR1, "...us" -> US2), usando o indice do proprio site.
  3. GLOBOEPG.xml.gz local, como fonte complementar.

Se EPGFULL.xml.gz ja existir, ele e sobrescrito. O resultado e XMLTV valido
e compativel com TiviMate (todo <programme> referencia um <channel> que
existe no guia e os tvg-ids casam com a playlist).
"""
import gzip
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax
from datetime import datetime, timedelta, timezone

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"
GLOBO_EPG = "GLOBOEPG.xml.gz"

PYONGYANG = timezone(timedelta(hours=9))

# Janela de retencao: nao deixar o guia maior do que o necessario.
KEEP_BEFORE = timedelta(days=2)
KEEP_AFTER = timedelta(days=10)

KORYO_EPG_URL = "https://koryo.tv/api/epg/b2ad0bb59619601b6dd7069a.dat"
KORYO_HEADER = {
    "X-Koryo-Epg": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://koryo.tv/schedule",
}

EPGSHARE01_INDEX = "https://epgshare01.online/epgshare01/"
EPGSHARE01_URL = "https://epgshare01.online/epgshare01/{}"

# Pluto TV: o canal "Big Brother 24/7" (tvg-id BigBrother.us) tem guia real
# publicado no i.mjh.nz com o site_id 6661f11a41af6400080e90d8. Mapeamos o
# site_id de volta para o tvg-id usado na playlist para casar com o EPGFULL.
PLUTO_BB_ID = "BigBrother.us"
PLUTO_BB_SRC_ID = "6661f11a41af6400080e90d8"
PLUTO_EPG_URL = "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/all.xml.gz"

JUCHE_API = "https://juche-tv-epg-api.vercel.app/api/bloxyplaytv?ch=KCTV&date={}"

# Dados diarios de KCTV publicados no repo Bloxyplay/JucheTV-EPG-API (mesma
# fonte que o site Juche TV exibe), usados quando o KORYO.TV esta fora do ar.
JUCHE_GITHUB_URL = "https://raw.githubusercontent.com/Bloxyplay/JucheTV-EPG-API/main/epg/KCTV/{}.json"


def http_get(url, headers=None, timeout=90, retries=1, delay=5):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                print(f"      Tentativa {attempt+1}/{retries} falhou ({e}); aguardando {delay}s...")
                import time; time.sleep(delay)
    raise last_err


def parse_m3u(data):
    channels = {}
    for line in data.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        tvg_id = re.search(r'tvg-id="([^"]*)"', line)
        tvg_name = re.search(r'tvg-name="([^"]*)"', line)
        tvg_logo = re.search(r'tvg-logo="([^"]*)"', line)
        cid = tvg_id.group(1) if tvg_id else ""
        if cid and cid not in channels:
            channels[cid] = {
                "name": tvg_name.group(1) if tvg_name else cid,
                "logo": tvg_logo.group(1) if tvg_logo else "",
            }
    return channels


def wayback_latest(url):
    today = datetime.now(timezone.utc).date()
    for cand in (url.split("://", 1)[-1], url):
        for ts in (today, today + timedelta(days=1)):
            api = "http://archive.org/wayback/available?url={}&timestamp={}".format(
                urllib.parse.quote(cand, safe=""), ts.strftime("%Y%m%d")
            )
            try:
                info = json.loads(http_get(api, timeout=30).decode("utf-8", errors="ignore"))
            except Exception:
                continue
            snap = (info.get("archived_snapshots") or {}).get("closest") or {}
            if snap.get("available") and snap.get("status") == "200":
                return snap["url"]
    return None


def fetch_koryo():
    live = True
    source = "KORYO.TV (ao vivo)"
    try:
        raw = http_get(KORYO_EPG_URL, headers=KORYO_HEADER)
    except Exception as e:
        print(f"    ERRO no endpoint koryo ({e}); procurando snapshot no Wayback Machine...")
        raw = None
        try:
            snap_url = wayback_latest(KORYO_EPG_URL)
            if snap_url:
                print(f"    Snapshot encontrado: {snap_url}")
                # O sufixo "id_" faz o Wayback Machine servir o arquivo bruto
                # (sem a pagina HTML de confirmacao).
                snap_url = re.sub(r"/web/(\d+)/", r"/web/\1id_/", snap_url)
                raw = http_get(snap_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
                source = "Internet Archive (Wayback Machine)"
                live = False
        except Exception as e2:
            print(f"    ERRO ao consultar o Wayback Machine: {e2}")
    if not raw:
        raise RuntimeError("Nao foi possivel baixar o EPG do KORYO.TV (fonte e snapshot indisponiveis)")
    data = gzip.decompress(raw).decode("utf-8", errors="ignore")
    events = json.loads(data).get("events", [])
    return events, source, live


def fetch_juche(koryo_id, oldest_ok, newest_ok):
    """Fallback para KCTV: programacao diaria do Juche TV (API independente)."""
    programmes = []
    seen = set()
    day = oldest_ok.date()
    end_day = newest_ok.date()
    while day <= end_day:
        iso_day = day.strftime("%Y-%m-%d")
        try:
            data = json.loads(http_get(JUCHE_API.format(iso_day), timeout=60)
                              .decode("utf-8", errors="ignore"))
        except Exception:
            data = {}
        for prog in data.get("programs", []):
            try:
                start = datetime.fromisoformat(f"{iso_day}T{prog['start']}:00+09:00")
                end = datetime.fromisoformat(f"{iso_day}T{prog['end']}:00+09:00")
            except Exception:
                continue
            if end <= start:
                end += timedelta(days=1)
            if start < oldest_ok or start > newest_ok:
                continue
            title = prog.get("title") or {}
            category = prog.get("category") or {}
            ev = {
                "startUtc": start.isoformat(),
                "endUtc": end.isoformat(),
                "title": title.get("ko"),
                "titleEn": title.get("en"),
                "category": category.get("en") or category.get("ko"),
            }
            block = build_programme(ev, koryo_id)
            key = (koryo_id, block)
            if key not in seen:
                seen.add(key)
                programmes.append(block)
        day += timedelta(days=1)
    return programmes


def fetch_juche_github(koryo_id, oldest_ok, newest_ok):
    """Fallback para KCTV: arquivos diarios do Bloxyplay/JucheTV-EPG-API.

    Os arquivos (epg/KCTV/YYYY-MM-DD.json) contem a mesma programacao que o
    site Juche TV exibe; horarios em Pyongyang, sem depender do KORYO.TV.
    """
    programmes = []
    seen = set()
    day = oldest_ok.date()
    end_day = newest_ok.date()
    while day <= end_day:
        iso_day = day.strftime("%Y-%m-%d")
        try:
            data = json.loads(http_get(JUCHE_GITHUB_URL.format(iso_day), timeout=60)
                              .decode("utf-8", errors="ignore"))
        except Exception:
            day += timedelta(days=1)
            continue
        for prog in data.get("programs", []):
            try:
                start = datetime.strptime(f"{iso_day}T{prog['start']}:00+09:00",
                                          "%Y-%m-%dT%H:%M:%S%z")
                end = datetime.strptime(f"{iso_day}T{prog['end']}:00+09:00",
                                        "%Y-%m-%dT%H:%M:%S%z")
            except Exception:
                continue
            if end <= start:
                end += timedelta(days=1)
            if start < oldest_ok or start > newest_ok:
                continue
            title = prog.get("title") or {}
            ev = {
                "startUtc": start.isoformat(),
                "endUtc": end.isoformat(),
                "title": title.get("ko"),
                "titleEn": title.get("en"),
            }
            block = build_programme(ev, koryo_id)
            key = (koryo_id, block)
            if key not in seen:
                seen.add(key)
                programmes.append(block)
        day += timedelta(days=1)
    return programmes


def koryo_target_id(channels):
    for cid in channels:
        low = cid.lower()
        if "koreancentral" in low or "kctv" in low or low.endswith(".kp"):
            return cid
    return None


def iso_to_xmltv(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(PYONGYANG)
    return dt.strftime("%Y%m%d%H%M%S") + " +0900"


def build_programme(ev, tvg_id):
    title = ev.get("titleEn") or ev.get("title") or "Sem titulo"
    lang = "en" if ev.get("titleEn") else "ko"
    parts = [f'  <programme start="{iso_to_xmltv(ev["startUtc"])}" '
             f'stop="{iso_to_xmltv(ev["endUtc"])}" channel="{tvg_id}">']
    parts.append(f'    <title lang="{lang}">{sax.escape(title)}</title>')
    if ev.get("category"):
        parts.append(f'    <category lang="en">{sax.escape(ev["category"])}</category>')
    if ev.get("title") and ev.get("titleEn"):
        parts.append(f'    <sub-title lang="ko">{sax.escape(ev["title"])}</sub-title>')
    parts.append("  </programme>")
    return "\n".join(parts)


def parse_xmltv_time(s):
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")
    except ValueError:
        try:
            return datetime.strptime(s[:8], "%Y%m%d").replace(tzinfo=PYONGYANG)
        except Exception:
            return None


def list_epgshare01_files():
    html = http_get(EPGSHARE01_INDEX, timeout=60).decode("utf-8", errors="ignore")
    mapping = {}
    for fn in re.findall(r'href="(epg_ripper_[A-Za-z0-9]+\.xml\.gz)"', html):
        m = re.match(r"epg_ripper_([A-Za-z]+)\d*\.xml\.gz", fn)
        if m:
            mapping.setdefault(m.group(1).lower(), fn)
    return mapping


def extract_xmltv(url, wanted, oldest_ok, newest_ok, retries=1, delay=5):
    """Baixa um XMLTV .gz e extrai apenas os canais desejados.

    Retorna (channels, programmes): dicts de tvg-id -> lista de blocos XML.
    """
    channels = {}
    programmes = {}
    raw = http_get(url, timeout=180, retries=retries, delay=delay)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        with gzip.open(tmp.name, "rb") as f:
            for _event, elem in ET.iterparse(f, events=("end",)):
                if elem.tag == "channel":
                    cid = elem.get("id")
                    if cid in wanted:
                        channels.setdefault(cid, ET.tostring(elem, encoding="unicode"))
                    elem.clear()
                elif elem.tag == "programme":
                    cid = elem.get("channel")
                    if cid in wanted:
                        start = parse_xmltv_time(elem.get("start", ""))
                        if start is not None and oldest_ok <= start <= newest_ok:
                            programmes.setdefault(cid, []).append(
                                ET.tostring(elem, encoding="unicode")
                            )
                    elem.clear()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return channels, programmes


def remap_pluto_bb(channels, programmes):
    """Renomeia o site_id do Pluto (6661f11a41af6400080e90d8) para o tvg-id
    usado na playlist (BigBrother.us), nos blocos de canal e de programa."""
    out_channels = {}
    out_programmes = {}
    for cid, block in channels.items():
        out_channels[PLUTO_BB_ID] = block.replace(
            'id="{}"'.format(PLUTO_BB_SRC_ID), 'id="{}"'.format(PLUTO_BB_ID)
        )
    for cid, blocks in programmes.items():
        for b in blocks:
            out_programmes.setdefault(PLUTO_BB_ID, []).append(
                b.replace('channel="{}"'.format(PLUTO_BB_SRC_ID),
                          'channel="{}"'.format(PLUTO_BB_ID))
            )
    return out_channels, out_programmes


def channel_block_from_m3u(cid, info):
    parts = [f'  <channel id="{sax.escape(cid)}">']
    parts.append(f'    <display-name>{sax.escape(info["name"])}</display-name>')
    if info.get("logo"):
        parts.append(f'    <icon src="{sax.escape(info["logo"])}"/>')
    parts.append("  </channel>")
    return "\n".join(parts)


def add_programmes(all_programmes, seen, cid, blocks):
    for block in blocks:
        key = (cid, block)
        if key not in seen:
            seen.add(key)
            all_programmes.setdefault(cid, []).append(block)


def extend_last_programme(blocks, stop_str):
    """Estende o stop do programa mais recente para cobrir a janela de retencao.

    Usado para canais 24/7 (ex.: Pluto TV "Big Brother") cuja fonte so publica
    a programacao ate o fim do dia atual: o programa em exibicao continua ao
    vivo, entao estendemos o stop ate o fim da janela sem inventar titulos.
    """
    if not blocks:
        return blocks
    latest = None
    latest_idx = -1
    for i, b in enumerate(blocks):
        m = re.search(r'start="(\d{8}\d{6}\s+[+-]\d{4})"', b)
        if m and (latest is None or m.group(1) > latest):
            latest = m.group(1)
            latest_idx = i
    if latest_idx < 0:
        return blocks
    blocks[latest_idx] = re.sub(
        r'stop="\d{8}\d{6}\s+[+-]\d{4}"',
        'stop="{}"'.format(stop_str),
        blocks[latest_idx],
        count=1,
    )
    return blocks


def main():
    now = datetime.now(timezone.utc)
    pyongyang_now = now.astimezone(PYONGYANG)
    oldest_ok = pyongyang_now - KEEP_BEFORE
    newest_ok = pyongyang_now + KEEP_AFTER

    print("=== ETAPA 1: Baixar M3U ===")
    try:
        m3u_data = http_get(M3U_URL).decode("utf-8", errors="ignore")
        print(f"  M3U baixado de: {M3U_URL}")
    except Exception as e:
        print(f"  ERRO ao baixar M3U remoto ({e}); usando arquivo local NEWSWORLDNOVOS.m3u")
        with open("NEWSWORLDNOVOS.m3u", "r", encoding="utf-8") as f:
            m3u_data = f.read()
    channels = parse_m3u(m3u_data)
    wanted_ids = list(channels.keys())
    print(f"  Canais na playlist: {len(wanted_ids)}")
    for cid in wanted_ids:
        print(f"    - {cid} ({channels[cid]['name']})")

    print("\n=== ETAPA 2: Baixar EPGs ===")
    all_programmes = {}
    seen = set()
    channel_xml = {}
    files_cache = {}

    # 2.1 KCTV via KORYO.TV (live -> Wayback Machine)
    koryo_id = koryo_target_id(channels)
    if koryo_id:
        print(f"  KCTV detectado: {koryo_id}")
        print(f"  Baixando KORYO.TV: {KORYO_EPG_URL}")
        try:
            events, source, live = fetch_koryo()
            print(f"    Fonte: {source}")
            print(f"    Eventos recebidos: {len(events)}")
            kept = 0
            for ev in events:
                if ev.get("channel") != "kctv":
                    continue
                try:
                    start = datetime.fromisoformat(ev["startUtc"]).astimezone(PYONGYANG)
                except Exception:
                    continue
                if start < oldest_ok or start > newest_ok:
                    continue
                kept += 1
                add_programmes(all_programmes, seen, koryo_id,
                               [build_programme(ev, koryo_id)])
            print(f"    Programas na janela ({oldest_ok:%Y-%m-%d} a {newest_ok:%Y-%m-%d}): {kept}")
        except Exception as e:
            print(f"    ERRO: {e}")
        if not all_programmes.get(koryo_id):
            print(f"  KCTV sem dados do KORYO; baixando GitHub Bloxyplay como fallback")
            try:
                github_juche = fetch_juche_github(koryo_id, oldest_ok, newest_ok)
                add_programmes(all_programmes, seen, koryo_id, github_juche)
                print(f"    Programas Bloxyplay na janela: {len(github_juche)}")
            except Exception as e:
                print(f"    ERRO no GitHub Bloxyplay: {e}")
        if not all_programmes.get(koryo_id):
            print(f"  KCTV sem dados; baixando Juche TV como fallback")
            try:
                juche = fetch_juche(koryo_id, oldest_ok, newest_ok)
                add_programmes(all_programmes, seen, koryo_id, juche)
                print(f"    Programas Juche TV na janela: {len(juche)}")
            except Exception as e:
                print(f"    ERRO no Juche TV: {e}")
    else:
        print("  KCTV nao esta na playlist; pulando KORYO.TV.")

    # 2.2 epgshare01: escolhe arquivo pelo pais do sufixo do tvg-id
    try:
        epg_files = list_epgshare01_files()
    except Exception as e:
        print(f"  ERRO ao listar indice do epgshare01: {e}")
        epg_files = {}

    for cid in wanted_ids:
        if cid == koryo_id:
            continue
        if cid == PLUTO_BB_ID:
            print(f"    {cid}: baixando Pluto TV (i.mjh.nz): {PLUTO_EPG_URL}")
            try:
                src_channels, src_programmes = extract_xmltv(
                    PLUTO_EPG_URL, [PLUTO_BB_SRC_ID], oldest_ok, newest_ok, retries=3, delay=10
                )
                src_channels, src_programmes = remap_pluto_bb(
                    src_channels, src_programmes
                )
            except Exception as e:
                print(f"    ERRO ao baixar/ler {PLUTO_EPG_URL}: {e}")
                src_channels, src_programmes = {}, {}
            if cid in src_channels:
                channel_xml.setdefault(cid, src_channels[cid])
            blocks = src_programmes.get(cid, [])
            if blocks:
                blocks = extend_last_programme(
                    blocks, newest_ok.strftime("%Y%m%d%H%M%S") + " +0900"
                )
                src_programmes[cid] = blocks
            n = len(blocks)
            add_programmes(all_programmes, seen, cid, blocks)
            print(f"      {cid}: {n} programas (Pluto TV / i.mjh.nz)")
            continue
        last = cid.rsplit(".", 1)[-1]
        country = re.sub(r"\d+$", "", last).lower()
        filename = epg_files.get(country)
        if not filename:
            print(f"    {cid}: sem fonte epgshare01 para o pais '{country}' "
                  f"(so a definicao do canal entra no guia)")
            continue
        if filename in files_cache:
            src_channels, src_programmes = files_cache[filename]
        else:
            url = EPGSHARE01_URL.format(filename)
            print(f"    {cid}: baixando {filename}")
            try:
                src_channels, src_programmes = extract_xmltv(url, wanted_ids, oldest_ok, newest_ok)
                files_cache[filename] = (src_channels, src_programmes)
            except Exception as e:
                print(f"    ERRO ao baixar/ler {filename}: {e}")
                continue
        if cid in src_channels:
            channel_xml.setdefault(cid, src_channels[cid])
        n = len(src_programmes.get(cid, []))
        add_programmes(all_programmes, seen, cid, src_programmes.get(cid, []))
        print(f"      {cid}: {n} programas (epgshare01)")

    # 2.3 GLOBOEPG.xml.gz local como fonte complementar
    if os.path.exists(GLOBO_EPG):
        try:
            print(f"  Lendo EPG local: {GLOBO_EPG}")
            with gzip.open(GLOBO_EPG, "rt", encoding="utf-8") as f:
                globo = f.read()
            for cid in wanted_ids:
                pat = re.compile(
                    rf'<programme\s+[^>]*channel="{re.escape(cid)}"[^>]*>.*?</programme>',
                    re.DOTALL,
                )
                found = pat.findall(globo)
                if found:
                    add_programmes(all_programmes, seen, cid, found)
                    print(f"    {cid}: {len(found)} programas (Globo)")
        except Exception as e:
            print(f"    ERRO: {e}")

    print("\n=== ETAPA 3: Montar EPGFULL.xml.gz ===")
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<tv generator-info-name="JCTV EPG Generator" '
                 'generator-info-url="https://github.com/gratinomaster/JCTV">']
    for cid in wanted_ids:
        xml_parts.append(channel_xml.get(cid) or channel_block_from_m3u(cid, channels[cid]))
        for prog in all_programmes.get(cid, []):
            xml_parts.append(prog)
    xml_parts.append("</tv>")
    full_xml = "\n".join(xml_parts) + "\n"

    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(full_xml)
    print(f"  Arquivo gravado: {OUTPUT} ({os.path.getsize(OUTPUT):,} bytes)")

    print("\n=== ETAPA 4: Validar ===")
    with gzip.open(OUTPUT, "rt", encoding="utf-8") as f:
        content = f.read()

    root = ET.fromstring(content)
    ch_count = len(root.findall("channel"))
    prog_count = len(root.findall("programme"))
    print(f"  XML valido (ElementTree OK)")
    print(f"  Canais: {ch_count}")
    print(f"  Programas: {prog_count}")

    # Compatibilidade com TiviMate: todo <programme> deve referenciar um canal
    # que existe no XMLTV e tvg-ids devem casar com a playlist.
    defined = {ch.get("id") for ch in root.findall("channel")}
    orphan = [p.get("channel") for p in root.findall("programme") if p.get("channel") not in defined]
    missing = [cid for cid in wanted_ids if cid not in defined]
    print(f"  Programas sem canal correspondente: {len(orphan)}")
    print(f"  Canais do M3U ausentes no guia: {len(missing)}")

    today = pyongyang_now.date()
    tomorrow = today + timedelta(days=1)
    today_s = today.strftime("%Y%m%d")
    tomorrow_s = tomorrow.strftime("%Y%m%d")

    def overlaps(date_s):
        day_start = datetime.strptime(date_s, "%Y%m%d").replace(tzinfo=PYONGYANG)
        day_end = day_start + timedelta(days=1)
        count = 0
        for p in root.findall("programme"):
            s = parse_xmltv_time(p.get("start", ""))
            e = parse_xmltv_time(p.get("stop", ""))
            if s is None:
                continue
            if e is None or e <= s:
                e = s + timedelta(hours=1)
            if s < day_end and e > day_start:
                count += 1
        return count

    today_progs = overlaps(today_s)
    tomorrow_progs = overlaps(tomorrow_s)

    for cid in wanted_ids:
        ch_found = cid in defined
        c_progs = sum(1 for p in root.findall(f'programme[@channel="{cid}"]'))
        print(f"    {cid}: {'OK' if ch_found else 'FALTA'} ({c_progs} programas)")

    print(f"  Programas de HOJE   ({today_s}, Pyongyang): {today_progs}")
    print(f"  Programas de AMANHA ({tomorrow_s}, Pyongyang): {tomorrow_progs}")
    if today_progs:
        print("  Teste hoje: OK")
    else:
        print("  Teste hoje: FALHOU")
    if tomorrow_progs:
        print("  Teste amanha: OK")
    else:
        print("  Teste amanha: FALHOU (dados nao publicados pela fonte ainda)")

    print("\n=== CONCLUIDO ===")


if __name__ == "__main__":
    main()
