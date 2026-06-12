#!/usr/bin/env python3
import gzip
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from collections import OrderedDict
from io import StringIO
import os

M3U_PATH = "NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"

EPG_URLS = [
    "https://github.com/limaalef/BrazilTVEPG/raw/refs/heads/main/globo.xml",
    "https://github.com/limaalef/BrazilTVEPG/raw/refs/heads/main/claro.xml",
    "https://github.com/limaalef/BrazilTVEPG/raw/refs/heads/main/vivoplay.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
]

CHANNEL_NAMES = {
    "tv-globo": "TV Globo",
    "g1": "G1",
    "g1-caruaru": "G1 Caruaru",
    "ge-tv": "ge TV",
    "cbn-sp": "CBN SP",
    "cbn-rj": "CBN RJ",
    "tv-vanguarda": "TV Vanguarda",
    "tv-verdes-mares": "TV Verdes Mares",
    "tv-gazeta-es": "TV Gazeta ES",
    "tv-integracao-jf": "TV Integração Juiz de Fora",
    "tv-integracao-uberlandia": "TV Integração Uberlândia",
    "tv-integracao-uberaba": "TV Integração Uberaba",
    "rede-amazonica": "Rede Amazônica",
    "tv-liberal": "TV Liberal",
    "ABC.News.Live.us2": "ABC News Live",
    "FRANCE 24 HD": "France 24 Español",
    "DW-TV": "DW",
    "Bloomberg.HD.us2": "Bloomberg TV",
    "ESTRELLA.NEWS.us2": "Estrella News",
    "al-jazeera-english": "Al Jazeera English",
    "rt-espanol": "RT Español",
    "24-horas-rtve": "24 Horas RTVE",
    "univision-noticias": "Univision Noticias",
    "telemundo": "Telemundo",
}

EXACT_ALIASES = {
    "tv-globo": ["tv-globo"],
    "ge-tv": ["ge-tv", "ge tv hd", "ge"],
    "tv-gazeta-es": ["gazeta"],
    "tv-verdes-mares": ["tv-verdes-mares", "tvverdesmares"],
}

GENERIC_SCHEDULE = [
    ("04:00", "01:00", "Hora 1"),
    ("05:00", "02:00", "Bom Dia Local"),
    ("07:00", "02:00", "Bom Dia Brasil"),
    ("09:00", "01:00", "Mais Você"),
    ("10:00", "01:00", "Encontro com Fátima Bernardes"),
    ("11:00", "01:00", "Jornal Local 1ª Edição"),
    ("12:00", "01:00", "Globo Esporte"),
    ("13:00", "01:00", "Jornal Hoje"),
    ("14:00", "01:00", "Novela da Tarde"),
    ("15:00", "02:00", "Sessão da Tarde"),
    ("17:00", "01:00", "Vale a Pena Ver de Novo"),
    ("18:00", "01:00", "Novela das Seis"),
    ("19:00", "01:00", "Jornal Nacional"),
    ("20:00", "01:00", "Novela das Nove"),
    ("21:00", "01:00", "Big Brother Brasil"),
    ("22:00", "01:00", "Jornal da Globo"),
    ("23:00", "00:30", "Conversa com Bial"),
    ("23:30", "00:30", "Programa do Jô"),
    ("00:00", "04:00", "Filme / Série"),
]

GENERIC_SCHEDULE_G1 = [
    ("05:00", "03:00", "G1 em Revista"),
    ("08:00", "02:00", "G1 Notícias"),
    ("10:00", "02:00", "G1 Local"),
    ("12:00", "01:00", "G1 Meio-dia"),
    ("13:00", "03:00", "G1 Tarde"),
    ("16:00", "02:00", "G1 Local"),
    ("18:00", "01:00", "G1 Notícias"),
    ("19:00", "01:00", "G1 Nacional"),
    ("20:00", "04:00", "G1 Noite"),
    ("00:00", "05:00", "G1 Madrugada"),
]

GENERIC_SCHEDULE_CBN = [
    ("05:00", "03:00", "CBN no Ar"),
    ("08:00", "01:00", "CBN Entrevista"),
    ("09:00", "01:00", "CBN Dinheiro"),
    ("10:00", "01:00", "CBN Tecnologia"),
    ("11:00", "01:00", "CBN No Caminho"),
    ("12:00", "01:00", "CBN Esportes"),
    ("13:00", "03:00", "CBN No Ar"),
    ("16:00", "02:00", "CBN Dinheiro"),
    ("18:00", "01:00", "CBN Brasil"),
    ("19:00", "03:00", "CBN No Ar"),
    ("22:00", "07:00", "CBN Late Night"),
]

GENERIC_SCHEDULE_NEWS = [
    ("00:00", "01:00", "News Update"),
    ("01:00", "01:00", "News Update"),
    ("02:00", "01:00", "News Update"),
    ("03:00", "01:00", "News Update"),
    ("04:00", "01:00", "News Update"),
    ("05:00", "01:00", "News Update"),
    ("06:00", "01:00", "Morning News"),
    ("07:00", "01:00", "Morning News"),
    ("08:00", "01:00", "Morning News"),
    ("09:00", "01:00", "News Update"),
    ("10:00", "01:00", "News Update"),
    ("11:00", "01:00", "News Update"),
    ("12:00", "01:00", "Midday News"),
    ("13:00", "01:00", "News Update"),
    ("14:00", "01:00", "News Update"),
    ("15:00", "01:00", "News Update"),
    ("16:00", "01:00", "News Update"),
    ("17:00", "01:00", "Evening News"),
    ("18:00", "01:00", "Evening News"),
    ("19:00", "01:00", "Evening News"),
    ("20:00", "01:00", "Prime Time News"),
    ("21:00", "01:00", "Prime Time News"),
    ("22:00", "01:00", "Late Night News"),
    ("23:00", "01:00", "Late Night News"),
]


def slugify(name):
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_only = nfkd.encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'[^a-z0-9]+', '-', ascii_only.lower()).strip('-')

def get_tvg_ids_from_m3u(m3u_path):
    ids = OrderedDict()
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m:
                ids[m.group(1)] = True
            elif line.startswith("#EXTINF:"):
                name_m = re.search(r',\s*(.+?)\s*$', line)
                if name_m:
                    name = name_m.group(1).strip().split("|")[0].strip()
                    gen_id = slugify(name)
                    if gen_id and gen_id not in ids:
                        ids[gen_id] = True
    return list(ids.keys())


def fetch_epg_xml(url):
    import urllib.request
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            if url.endswith(".gz"):
                import gzip
                data = gzip.decompress(data)
            return data.decode("utf-8")
    except Exception as e:
        print(f"  Erro ao baixar {url}: {e}")
        return None


def find_source_channel_id(tvg_id, epg_roots):
    aliases = EXACT_ALIASES.get(tvg_id, [])
    aliases.append(tvg_id)

    for root in epg_roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "").lower().strip()
            for alias in aliases:
                if cid == alias.lower():
                    return ch.get("id"), root
            dn = ch.find("display-name")
            if dn is not None and dn.text:
                dnt = dn.text.strip().lower()
                for alias in aliases:
                    if dnt == alias.lower():
                        return ch.get("id"), root
    return None, None


def main():
    print("=" * 60)
    print("Gerador de EPGFULL.xml.gz filtrado pelo M3U")
    print("=" * 60)

    print("\n1. Lendo tvg-ids do M3U...")
    wanted_ids = get_tvg_ids_from_m3u(M3U_PATH)
    print(f"   IDs encontrados: {wanted_ids}")

    print("\n2. Baixando EPGs de origem...")
    epg_roots = []
    for url in EPG_URLS:
        fname = url.rstrip("/").split("/")[-1]
        print(f"   {fname}...", end=" ", flush=True)
        content = fetch_epg_xml(url)
        if not content:
            print("FALHOU")
            continue
        print("OK")
        try:
            tree = ET.parse(StringIO(content))
            epg_roots.append(tree.getroot())
        except Exception as e:
            print(f"   Erro ao parsear: {e}")

    print("\n3. Mapeando canais do M3U para fontes EPG...")
    channel_map = {}
    for wid in wanted_ids:
        src_id, src_root = find_source_channel_id(wid, epg_roots)
        if src_id:
            channel_map[wid] = (src_id, src_root)
            print(f"   {wid} -> fonte: {src_id}")
        else:
            print(f"   {wid} -> não encontrado (será gerado)")

    tv_root = ET.Element("tv", {
        "source-info-url": "https://epgshare01.online",
        "source-info-name": "EPGShare01 + BrazilTVEPG + JCTV",
        "generator-info-name": "JCTV EPG Filter"
    })

    for wid in wanted_ids:
        name = CHANNEL_NAMES.get(wid, wid)
        ch = ET.SubElement(tv_root, "channel", id=wid)
        ET.SubElement(ch, "display-name", lang="pt").text = name

    print("\n4. Extraindo programmes das fontes EPG...")
    matched_progs = 0
    for wid in wanted_ids:
        if wid not in channel_map:
            continue
        src_id, src_root = channel_map[wid]
        for prog in src_root.findall("programme"):
            if prog.get("channel", "").lower() == src_id.lower():
                prog.set("channel", wid)
                tv_root.append(prog)
                matched_progs += 1
    print(f"   Programmes copiados das fontes: {matched_progs}")

    print("\n5. Gerando programação genérica para canais sem EPG...")
    generated_progs = 0
    for wid in wanted_ids:
        if wid in channel_map:
            continue
        name = CHANNEL_NAMES.get(wid, wid)
        print(f"   {wid} ({name})...")

        if wid in ("g1", "g1-caruaru"):
            sched = GENERIC_SCHEDULE_G1
        elif wid in ("cbn", "cbn-sp", "cbn-rj"):
            sched = GENERIC_SCHEDULE_CBN
        elif wid in ("ABC.News.Live.us2", "FRANCE 24 HD", "DW-TV", "Bloomberg.HD.us2", "ESTRELLA.NEWS.us2",
                     "al-jazeera-english", "rt-espanol", "24-horas-rtve", "univision-noticias", "telemundo"):
            sched = GENERIC_SCHEDULE_NEWS
        else:
            sched = GENERIC_SCHEDULE

        days = 3
        today = datetime.now()
        tz = "-0300"

        for day_offset in range(days):
            day = today + timedelta(days=day_offset)
            for time_str, duration_str, prog_name in sched:
                h, m = map(int, time_str.split(":"))
                start = day.replace(hour=h, minute=m, second=0, microsecond=0)
                dur_parts = duration_str.split(":")
                dur = timedelta(hours=int(dur_parts[0]), minutes=int(dur_parts[1]))
                end = start + dur

                start_fmt = start.strftime("%Y%m%d%H%M%S") + f" {tz}"
                end_fmt = end.strftime("%Y%m%d%H%M%S") + f" {tz}"

                prog = ET.SubElement(tv_root, "programme", {
                    "channel": wid,
                    "start": start_fmt,
                    "end": end_fmt,
                })
                ET.SubElement(prog, "title", lang="pt").text = prog_name
                generated_progs += 1
    print(f"   Programmes gerados: {generated_progs}")

    print(f"\n6. Salvando {OUTPUT}...")
    xml_str = ET.tostring(tv_root, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

    with gzip.open(OUTPUT, "wb") as f:
        f.write(pretty_xml)

    total_channels = len(list(tv_root.findall("channel")))
    total_programmes = len(list(tv_root.iter("programme")))
    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"\nConcluído! {OUTPUT} gerado:")
    print(f"  Canais: {total_channels}")
    print(f"  Programas: {total_programmes}")
    print(f"  Tamanho: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
