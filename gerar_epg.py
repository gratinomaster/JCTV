#!/usr/bin/env python3
import gzip
import re
import unicodedata
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
    "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_BR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_CO1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
]

# Manual mapping: M3U tvg-name -> list of EPG channel IDs (priority order)
CHANNEL_MAP = {
    # === Argentine broadcast ===
    "TyC Sports (1080p)": ["Canal.TyC.Sports.ar"],
    "TyC Sports 2 (720p)": ["Canal.TyC.Sports.ar"],
    "TyC Sports USA": ["TyC.Sports.Internacional.USA.us2"],
    "Telefe Buenos Aires (1080p)": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Internacional": ["Telefe.international.us2", "Canal.Telefe.Internacional.mx"],
    "El Trece (480p)": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "America TV": ["Canal.America.TV.(Argentina).ar"],
    "Televisión Pública": ["Canal.Televisión.Pública.(Argentina).ar"],
    "Todo Noticias": ["Canal.Cablenoticias.ar"],

    # === Argentine cable/paid ===
    "Disney Channel Latin America": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America (1080p)": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America (1080p) RAW": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Mexico (576p)": ["Canal.Disney.Channel.(México).mx"],
    "Disney Channel Latin America Mexico (720p)": ["Canal.Disney.Channel.(México).mx"],
    "Disney Channel Latin America Center (1080p)": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Panregional HD (1080p)": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Panregional HD (1080p) RAW": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Jr. Latin America": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America (576p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America North HD (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America North HD (1080p) RAW": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South HD (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South HD (1080p) RAW": ["Canal.Disney.Junior.(Argentina).ar"],
    "Sony Channel (1080p)": ["Canal.Sony.(Argentina).ar", "Sony.co"],
    "AMC Latin America (1080p) AR": ["AMC.HD.us2", "AMC.co"],
    "MTV Latin America (1080p) AR": ["Canal.MTV.(Argentina).ar", "MTV.co"],
    "Comedy Central Latin America (1080p) AR": ["Comedy.Central.HD.us2", "Comedy.Central.co"],
    "E! Latin America (1080p) AR": ["E!.Entertainment.Television.HD.us2", "E!.Entertainment.TV.co"],
    "El Gourmet (720p)": ["Canal.Elgourmet.ar", "El.Gourmet.co"],
    "El Gourmet (1080p)": ["Canal.Elgourmet.ar", "El.Gourmet.co"],
    "Fox Sports": ["FS1.Fox.Sports.1.HD.us2", "Canal.Fox.Sports.(México).mx"],
    "DSports (1080p) AR": ["DIRECTV.Sports.5(DTS6).co"],
    "FIFA+ Hispanic America (720p) AR": ["FIFA", "Canal.FIFA.ar"],

    # === Argentina educational ===
    "Pakapaka": ["Canal.Pakapaka.ar"],
    "DeporTV.ar": ["DeporTV"],

    # === Mexico ===
    "Azteca Uno": ["Canal.Azteca.Uno.mx"],
    "ADN 40": ["Canal.ADN.40.mx"],
    "Telemundo": ["Telemundo.Satellite.Feed.us2", "Canal.Telemundo.(México).mx"],
    "Telemundo Internacional (1080p) AR": ["Telemundo.co", "Canal.Telemundo.(México).mx"],
    "TeleFórmula": ["Canal.Telefórmula.mx"],
    "Canal 22": ["Canal.22.de.México.mx", "Canal.22.Internacional.mx", "CANAL.22.INTERNACIONAL.us2"],

    # === USA ===
    "ABC": ["ABC.National.Feed.us2"],
    "ABC News": ["ABC.News.Live.us2"],
    "Estrella TV": ["Estrella.TV.us2"],
    "Univision": ["Univision.Network.HD.us2"],
    "DW Español": ["Canal.DW.(Latinoamérica).ar", "Canal.DW.(Latinoamérica).mx"],
}

# Skip channels with no EPG available anywhere
SKIP_CHANNELS = {
    "5tv", "Argentinisima Satelital", "Cadena103.TV", "Bravo TV",
    "Canal 9 Link", "San Pedro TV", "TV Mana Argentina", "TV Solidaria",
    "Unife TV", "Unife TV RAW", "Kpop Mix", "Cumbia Mix", "Plim Plim",
}


def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_url(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
            if url.endswith(".gz"):
                data = gzip.decompress(data)
            return data.decode("utf-8")
    except Exception as e:
        print(f"  Erro ao baixar {url}: {e}")
        return None


def get_channels_from_m3u(m3u_path):
    channels = OrderedDict()
    current_name = None
    current_tvg_id = None
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#EXTINF"):
                name_m = re.search(r'tvg-name="([^"]*)"', line)
                id_m = re.search(r'tvg-id="([^"]*)"', line)
                current_name = name_m.group(1).strip() if name_m else ""
                current_tvg_id = id_m.group(1).strip() if id_m else ""
            elif current_name and line and not line.startswith("#"):
                channels[current_name] = current_tvg_id
                current_name = None
                current_tvg_id = None
    return channels


def find_epg_channel(epg_id_pattern, epg_roots):
    pattern = normalize(epg_id_pattern)
    if not pattern:
        return None, None
    for root_idx, root in enumerate(epg_roots):
        for ch in root.findall("channel"):
            ch_id = ch.get("id", "")
            if normalize(ch_id) == pattern:
                return ch_id, root_idx
    # Fallback: partial match
    for root_idx, root in enumerate(epg_roots):
        for ch in root.findall("channel"):
            ch_id = ch.get("id", "")
            if pattern in normalize(ch_id) or normalize(ch_id) in pattern:
                return ch_id, root_idx
    return None, None


def main():
    print("=" * 60)
    print("Gerador de EPGFULL.xml.gz - filtrado pelo M3U")
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

    # Step 2: Extract channels from M3U
    print("\n2. Lendo canais do M3U...")
    m3u_channels = get_channels_from_m3u(M3U_PATH)
    print(f"   {len(m3u_channels)} canais encontrados no M3U")

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
            count = len(tree.getroot().findall("channel"))
            prog_count = len(tree.getroot().findall("programme"))
            print(f"OK ({count} canais, {prog_count} programas)")
        except Exception as e:
            print(f"ERRO: {e}")

    if not epg_roots:
        print("\n   ERRO: Nenhuma fonte EPG carregada!")
        return

    # Step 4: Match channels
    print("\n4. Mapeando canais do M3U para fontes EPG...")
    channel_map = {}
    skipped = []
    unmapped = []

    for name, tvg_id in m3u_channels.items():
        if name in SKIP_CHANNELS:
            skipped.append(name)
            continue

        epg_ids = CHANNEL_MAP.get(name)
        found = False

        if epg_ids:
            for epg_id in epg_ids:
                src_id, src_root_idx = find_epg_channel(epg_id, epg_roots)
                if src_id:
                    channel_map[name] = (src_id, src_root_idx)
                    print(f"   OK   {name} -> {src_id}")
                    found = True
                    break

        if not found and tvg_id:
            src_id, src_root_idx = find_epg_channel(tvg_id, epg_roots)
            if src_id:
                channel_map[name] = (src_id, src_root_idx)
                print(f"   OK   {name} -> {src_id} (via tvg-id)")
                found = True

        if not found:
            unmapped.append(name)

    print(f"\n   Resumo:")
    print(f"   Mapeados: {len(channel_map)}/{len(m3u_channels)}")
    print(f"   Sem EPG:  {len(unmapped)}")
    print(f"   Pulados:  {len(skipped)}")

    # Step 5: Build filtered XML
    print("\n5. Construindo XML filtrado...")
    tv_root = ET.Element("tv", {
        "generator-info-name": "JCTV EPG Generator",
        "source-info-url": "https://epgshare01.online",
    })

    added_channels = set()

    # Add channel definitions
    for name, (src_id, src_root_idx) in channel_map.items():
        if src_id in added_channels:
            continue
        epg_root = epg_roots[src_root_idx]
        for ch in epg_root.findall("channel"):
            if ch.get("id") == src_id:
                new_ch = ET.SubElement(tv_root, "channel", id=src_id)
                dn = ch.find("display-name")
                if dn is not None and dn.text:
                    ET.SubElement(new_ch, "display-name").text = dn.text
                icon = ch.find("icon")
                if icon is not None:
                    new_ch.append(icon)
                added_channels.add(src_id)
                break

    # Copy programmes from matched channels
    print("   Copiando programas...")
    matched_progs = 0
    for name, (src_id, src_root_idx) in channel_map.items():
        epg_root = epg_roots[src_root_idx]
        for prog in epg_root.findall("programme"):
            if prog.get("channel", "") == src_id:
                new_prog = ET.SubElement(tv_root, "programme", {
                    "channel": src_id,
                    "start": prog.get("start", ""),
                    "stop": prog.get("stop", ""),
                })
                for child in prog:
                    new_prog.append(child)
                matched_progs += 1

    print(f"   Programas copiados: {matched_progs}")

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

    print(f"\n{'=' * 60}")
    print(f"Concluido! {OUTPUT}:")
    print(f"  Canais: {total_channels}")
    print(f"  Programas: {total_programmes}")
    print(f"  Tamanho: {size_kb:.1f} KB")
    print(f"  Mapeados: {len(channel_map)}/{len(m3u_channels)}")
    print(f"{'=' * 60}")

    if unmapped:
        print(f"\nCanais sem EPG ({len(unmapped)}):")
        for name in unmapped:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
