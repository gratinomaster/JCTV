#!/usr/bin/env python3
import gzip
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from collections import OrderedDict
from io import StringIO
import os

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
M3U_PATH = "NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"

EPG_URLS = [
    "https://iptv-epg.org/files/epg-us.xml.gz",
    "https://iptv-epg.org/files/epg-mx.xml.gz",
    "https://iptv-epg.org/files/epg-ar.xml.gz",
    "https://iptv-epg.org/files/epg-pt.xml.gz",
    "https://iptv-epg.org/files/epg-co.xml.gz",
    "https://iptv-epg.org/files/epg-ve.xml.gz",
    "https://iptv-epg.org/files/epg-es.xml.gz",
    "https://i.mjh.nz/SamsungTVPlus/us.xml.gz",
    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/us.xml.gz",
]

CHANNEL_NAMES = {
    "CNBC.us": "CNBC",
    "BBCNewsNorthAmerica.us": "BBC News North America",
    "SkyNews.pluto": "Sky News",
    "AlJazeera.us": "Al Jazeera English",
    "DWEnglish.us": "DW English",
    "Euronews.us": "Euronews",
    "France24enEspanol.us": "France 24 Español",
    "France24.us": "France 24 English",
    "France24.fr": "France 24 Français",
    "CGTNCCTVNews.us": "CGTN News",
    "RussiaToday.ar": "RT News Español",
    "TeleSur.ve": "TeleSUR",
    "RTP1.pt": "RTP 1",
    "RTP2.pt": "RTP 2",
    "RTP3.pt": "RTP 3",
    "RTPMemoria.pt": "RTP Memória",
    "AztecaUno.mx": "Azteca Uno",
    "LasEstrellas.mx": "Las Estrellas",
    "Canal5.mx": "Canal 5",
    "ImagenTV.mx": "Imagen TV",
    "Azteca7.mx": "Azteca 7",
    "MilenioTV.mx": "Milenio Televisión",
    "adn40.mx": "ADN 40",
    "CaracolTV.co": "Caracol TV",
    "RCN.co": "Canal RCN",
    "ELTrece.ar": "El Trece",
    "Telefe.ar": "Telefe",
    "AmericaTV.ar": "América TV",
    "TyCSports.ar": "TyC Sports",
    "TN.ar": "TN",
    "Canal26.ar": "Canal 26",
    "CronicaTV.ar": "Crónica TV",
    "LN+.ar": "LN+",
    "C5N.ar": "C5N",
    "Telemundo.us": "Telemundo",
    "EstrellaTV.us": "Estrella News",
    "Venevision.ve": "Venevision",
    "Globovision.ve": "Globovision",
}

EXACT_ALIASES = {
    "CNBC.us": ["cnbc"],
    "BBCNewsNorthAmerica.us": ["bbc news north america", "bbc news"],
    "SkyNews.pluto": ["sky news"],
    "AlJazeera.us": ["al jazeera", "al jazeera english"],
    "DWEnglish.us": ["dw english"],
    "Euronews.us": ["euronews"],
    "France24enEspanol.us": ["france 24 español", "france 24"],
    "France24.us": ["france 24 english"],
    "France24.fr": ["france 24 français", "france 24 francais"],
    "CGTNCCTVNews.us": ["cgtn news", "cctv news"],
    "RussiaToday.ar": ["rt news", "rt español", "rt noticias"],
    "TeleSur.ve": ["telesur"],
    "RTP1.pt": ["rtp 1", "rtp1"],
    "RTP2.pt": ["rtp 2", "rtp2"],
    "RTP3.pt": ["rtp 3", "rtp3"],
    "RTPMemoria.pt": ["rtp memória", "rtp memoria"],
    "AztecaUno.mx": ["azteca uno"],
    "LasEstrellas.mx": ["las estrellas", "estrellas"],
    "Canal5.mx": ["canal 5"],
    "ImagenTV.mx": ["imagen tv", "imagen television"],
    "Azteca7.mx": ["azteca 7"],
    "MilenioTV.mx": ["milenio television", "milenio tv"],
    "adn40.mx": ["adn 40"],
    "CaracolTV.co": ["caracol tv", "caracol television"],
    "RCN.co": ["rcn", "canal rcn", "rcn television"],
    "ELTrece.ar": ["el trece", "eltrece"],
    "Telefe.ar": ["telefe"],
    "AmericaTV.ar": ["américa tv", "america tv"],
    "TyCSports.ar": ["tyc sports"],
    "TN.ar": ["tn", "todo noticias"],
    "Canal26.ar": ["canal 26"],
    "CronicaTV.ar": ["crónica tv", "cronica tv"],
    "LN+.ar": ["ln+", "la nacion+"],
    "C5N.ar": ["c5n"],
    "Telemundo.us": ["telemundo"],
    "EstrellaTV.us": ["estrella tv", "estrella news"],
    "Venevision.ve": ["venevision", "venevision internacional"],
    "Globovision.ve": ["globovision"],
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
                tvg_id = m.group(1).strip()
                if tvg_id:
                    ids[tvg_id] = True
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
    exact_id = tvg_id.lower()

    for root in epg_roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "").lower().strip()
            if cid == exact_id:
                return ch.get("id"), root

    for root in epg_roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "").lower().strip()
            for alias in aliases:
                al = alias.lower()
                if cid == al:
                    return ch.get("id"), root
                if len(al) >= 4 and al in cid:
                    return ch.get("id"), root
            dn = ch.find("display-name")
            if dn is not None and dn.text:
                dnt = dn.text.strip().lower()
                for alias in aliases:
                    al = alias.lower()
                    if dnt == al:
                        return ch.get("id"), root
                    if len(al) >= 4 and al in dnt:
                        return ch.get("id"), root
    return None, None


def main():
    print("=" * 60)
    print("Gerador de EPGFULL.xml.gz filtrado pelo M3U")
    print("=" * 60)

    print(f"\n1. Baixando M3U de: {M3U_URL}")
    m3u_content = fetch_epg_xml(M3U_URL)
    if m3u_content:
        with open(M3U_PATH, "w", encoding="utf-8") as f:
            f.write(m3u_content)
        print("   M3U salvo em", M3U_PATH)
    else:
        print("   Falha ao baixar M3U, usando existente")

    print("\n2. Lendo tvg-ids do M3U...")
    wanted_ids = get_tvg_ids_from_m3u(M3U_PATH)
    print(f"   IDs encontrados: {wanted_ids}")

    print("\n3. Baixando EPGs de origem...")
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

    print("\n4. Mapeando canais do M3U para fontes EPG...")
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

    print("\n5. Extraindo programmes das fontes EPG...")
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

    print("\n6. Gerando programação genérica para canais sem EPG...")
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
        elif wid in ("CNBC.us", "BBCNewsNorthAmerica.us", "SkyNews.pluto",
                     "AlJazeera.us", "DWEnglish.us", "Euronews.us",
                     "France24enEspanol.us", "France24.us", "France24.fr",
                     "CGTNCCTVNews.us", "RussiaToday.ar", "TeleSur.ve",
                     "adn40.mx", "MilenioTV.mx", "Telemundo.us", "EstrellaTV.us",
                     "TN.ar", "C5N.ar", "LN+.ar", "CronicaTV.ar", "Canal26.ar"):
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
                    "stop": end_fmt,
                })
                ET.SubElement(prog, "title", lang="pt").text = prog_name
                generated_progs += 1
    print(f"   Programmes gerados: {generated_progs}")

    print(f"\n7. Salvando {OUTPUT}...")
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
