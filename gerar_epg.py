#!/usr/bin/env python3
import gzip
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from collections import OrderedDict
from io import StringIO
import os
import urllib.request

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
M3U_PATH = "NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"

EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_BR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_CO1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_AL1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_NO1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
]

# Channel name mapping for display
CHANNEL_NAMES = {
    "CNBC.us": "CNBC",
    "France24.EN.cz": "France 24 English",
    "Euronews.F.ch": "Euronews",
    "Rede.Vida.br": "Rede Vida",
    "Caracol.co": "Caracol TV",
    "RCN.co": "Canal RCN",
    "Azteca.7.(XHLAT).Nuevo.Laredo.MX.mx": "Azteca 7",
    "Das.Erste.de": "Das Erste (ARD)",
    "TF1.fr": "TF1",
    "tvi.reality.pt": "TVI Reality",
    "Telefe.international.us2": "Telefe Internacional",
    "TOP.Channel.al": "Top Channel",
    "bigbrother.us": "Big Brother 28",
    "granhermano.ar": "Gran Hermano",
    "São.Paulo/SP..Record.br": "Record TV",
    "RecordNews.br": "Record News",
    "CanalEducacao.br": "Canal Educação",
}

# Exact EPG channel ID overrides (use these IDs directly)
EXACT_OVERRIDES = {
    "France24.EN.cz": "France.24.Anglais.fr",
}

# Search terms for matching EPG channel IDs
CHANNEL_SEARCH = {
    "CNBC.us": ["cnbc"],
    "France24.EN.cz": ["france.24.anglais", "france24.english"],
    "Euronews.F.ch": ["euronews"],
    "Rede.Vida.br": ["redevida", "rede vida"],
    "Caracol.co": ["caracol"],
    "RCN.co": ["rcn"],
    "Azteca.7.(XHLAT).Nuevo.Laredo.MX.mx": ["azteca.7"],
    "Das.Erste.de": ["daserste", "das erste"],
    "TF1.fr": ["tf1"],
    "tvi.reality.pt": ["tvireality", "tvi reality"],
    "Telefe.international.us2": ["telefe"],
    "TOP.Channel.al": ["topchannel", "top channel"],
    "bigbrother.us": [],  # No EPG available (24/7 live feed)
    "granhermano.ar": [],  # No EPG available (24/7 live feed)
    "São.Paulo/SP..Record.br": ["record.br", "record tv"],
    "RecordNews.br": ["recordnews", "record news"],
    "CanalEducacao.br": [],  # No EPG available
}

GENERIC_SCHEDULE_NEWS = [
    ("00:00", "06:00", "Programa Noturno"),
    ("06:00", "03:00", "Manhã"),
    ("09:00", "03:00", "Tarde"),
    ("12:00", "02:00", "Almoço"),
    ("14:00", "04:00", "Tarde"),
    ("18:00", "02:00", "Jornalismo"),
    ("20:00", "04:00", "Noite"),
]


def fetch_url(url):
    """Download content from URL, decompressing if gzipped."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
            if url.endswith(".gz"):
                data = gzip.decompress(data)
            return data.decode("utf-8")
    except Exception as e:
        print(f"  Erro ao baixar {url}: {e}")
        return None


def get_tvg_ids_from_m3u(m3u_path):
    """Extract tvg-id values from the M3U file."""
    ids = OrderedDict()
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m:
                tvg_id = m.group(1).strip()
                if tvg_id:
                    ids[tvg_id] = True
    return list(ids.keys())


def find_channel_in_epg(tvg_id, epg_roots):
    """Search for a channel in EPG sources using multiple strategies."""
    # Strategy 0: Exact override
    override = EXACT_OVERRIDES.get(tvg_id)
    if override:
        for root in epg_roots:
            for ch in root.findall("channel"):
                if ch.get("id") == override:
                    return ch.get("id"), root

    search_terms = CHANNEL_SEARCH.get(tvg_id, [])
    if not search_terms:
        return None, None

    tvg_lower = tvg_id.lower()

    # Strategy 1: Exact ID match
    for root in epg_roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "").lower()
            if cid == tvg_lower:
                return ch.get("id"), root

    # Strategy 2: Search terms in ID
    for root in epg_roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "").lower()
            for term in search_terms:
                if term in cid or cid in term:
                    return ch.get("id"), root

    # Strategy 3: Search terms in display-name
    for root in epg_roots:
        for ch in root.findall("channel"):
            dn = ch.find("display-name")
            if dn is not None and dn.text:
                dnt = dn.text.lower()
                for term in search_terms:
                    if term in dnt or dnt in term:
                        return ch.get("id"), root

    return None, None


def main():
    print("=" * 60)
    print("Gerador de EPGFULL.xml.gz filtrado pelo M3U")
    print("=" * 60)

    # Step 1: Download M3U
    print(f"\n1. Baixando M3U de: {M3U_URL}")
    m3u_content = fetch_url(M3U_URL)
    if m3u_content:
        with open(M3U_PATH, "w", encoding="utf-8") as f:
            f.write(m3u_content)
        print("   M3U atualizado com sucesso")
    else:
        print("   Usando M3U local existente")

    # Step 2: Extract channel IDs from M3U
    print("\n2. Lendo tvg-ids do M3U...")
    wanted_ids = get_tvg_ids_from_m3u(M3U_PATH)
    print(f"   Canais encontrados ({len(wanted_ids)}):")
    for cid in wanted_ids:
        name = CHANNEL_NAMES.get(cid, cid)
        print(f"     - {cid} ({name})")

    # Step 3: Download EPG sources
    print("\n3. Baixando fontes EPG...")
    epg_roots = []
    for url in EPG_URLS:
        fname = url.split("/")[-1]
        print(f"   {fname}...", end=" ", flush=True)
        content = fetch_url(url)
        if not content:
            print("FALHOU")
            continue
        try:
            tree = ET.parse(StringIO(content))
            epg_roots.append(tree.getroot())
            print("OK")
        except Exception as e:
            print(f"ERRO: {e}")

    if not epg_roots:
        print("\n   ERRO: Nenhuma fonte EPG carregada!")
        return

    # Step 4: Match channels
    print("\n4. Mapeando canais do M3U para fontes EPG...")
    channel_map = {}
    unmapped = []
    for wid in wanted_ids:
        src_id, src_root = find_channel_in_epg(wid, epg_roots)
        if src_id:
            channel_map[wid] = (src_id, src_root)
            print(f"   {wid} -> {src_id}")
        else:
            unmapped.append(wid)
            print(f"   {wid} -> NÃO ENCONTRADO (gerará programa genérico)")

    # Step 5: Build output XML
    print("\n5. Construindo XML filtrado...")
    tv_root = ET.Element("tv", {
        "generator-info-name": "JCTV EPG Generator",
        "source-info-url": "https://epgshare01.online"
    })

    # Add channel definitions
    for wid in wanted_ids:
        name = CHANNEL_NAMES.get(wid, wid)
        ch = ET.SubElement(tv_root, "channel", id=wid)
        ET.SubElement(ch, "display-name", lang="pt").text = name

    # Copy programmes from matched channels
    print("   Copiando programas de canais mapeados...")
    matched_progs = 0
    for wid, (src_id, src_root) in channel_map.items():
        for prog in src_root.findall("programme"):
            if prog.get("channel", "").lower() == src_id.lower():
                prog.set("channel", wid)
                tv_root.append(prog)
                matched_progs += 1
    print(f"   Programas copiados: {matched_progs}")

    # Generate generic programmes for unmapped channels
    print("   Gerando programas genéricos...")
    generated_progs = 0
    for wid in unmapped:
        today = datetime.now()
        for day_offset in range(3):
            day = today + timedelta(days=day_offset)
            for time_str, duration_str, prog_name in GENERIC_SCHEDULE_NEWS:
                h, m = map(int, time_str.split(":"))
                start = day.replace(hour=h, minute=m, second=0, microsecond=0)
                dur_parts = duration_str.split(":")
                dur = timedelta(hours=int(dur_parts[0]), minutes=int(dur_parts[1]))
                end = start + dur

                start_fmt = start.strftime("%Y%m%d%H%M%S") + " -0300"
                end_fmt = end.strftime("%Y%m%d%H%M%S") + " -0300"

                prog = ET.SubElement(tv_root, "programme", {
                    "channel": wid,
                    "start": start_fmt,
                    "stop": end_fmt,
                })
                ET.SubElement(prog, "title", lang="pt").text = prog_name
                generated_progs += 1
    print(f"   Programas gerados: {generated_progs}")

    # Fill gaps: for channels that have programmes for some days but not all
    print("   Preenchendo lacunas...")
    filled_progs = 0
    today = datetime.now()
    for wid in wanted_ids:
        if wid in unmapped:
            continue
        # Find the range of dates covered by existing programmes
        existing_dates = set()
        for prog in tv_root.findall(f".//programme[@channel='{wid}']"):
            start = prog.get("start", "")[:8]
            if start:
                existing_dates.add(start)
        # Generate for days 0-2 that are missing
        for day_offset in range(3):
            day = today + timedelta(days=day_offset)
            day_str = day.strftime("%Y%m%d")
            if day_str not in existing_dates:
                for time_str, duration_str, prog_name in GENERIC_SCHEDULE_NEWS:
                    h, m = map(int, time_str.split(":"))
                    start = day.replace(hour=h, minute=m, second=0, microsecond=0)
                    dur_parts = duration_str.split(":")
                    dur = timedelta(hours=int(dur_parts[0]), minutes=int(dur_parts[1]))
                    end = start + dur
                    start_fmt = start.strftime("%Y%m%d%H%M%S") + " -0300"
                    end_fmt = end.strftime("%Y%m%d%H%M%S") + " -0300"
                    prog = ET.SubElement(tv_root, "programme", {
                        "channel": wid,
                        "start": start_fmt,
                        "stop": end_fmt,
                    })
                    ET.SubElement(prog, "title", lang="pt").text = prog_name
                    filled_progs += 1
    print(f"   Lacunas preenchidas: {filled_progs}")

    # Step 6: Save compressed XML
    print(f"\n6. Salvando {OUTPUT}...")
    xml_str = ET.tostring(tv_root, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

    with gzip.open(OUTPUT, "wb") as f:
        f.write(pretty_xml)

    total_channels = len(list(tv_root.findall("channel")))
    total_programmes = len(list(tv_root.iter("programme")))
    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"\nConcluído! {OUTPUT}:")
    print(f"  Canais: {total_channels}")
    print(f"  Programas: {total_programmes}")
    print(f"  Tamanho: {size_kb:.1f} KB")


if __name__ == "__main__":
    main()
