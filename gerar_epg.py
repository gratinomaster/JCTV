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
    "https://epgshare01.online/epgshare01/epg_ripper_CO1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_BR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
]

# Strict manual mapping: M3U tvg-name -> list of (EPG channel ID, source index priority)
# Lower index = higher priority source
CHANNEL_MAP = {
    # === Argentine broadcast channels ===
    "TyC Sports": ["Canal.TyC.Sports.ar"],
    "TyC Sports (1080p)": ["Canal.TyC.Sports.ar"],
    "TyC Sports (1080p) Geo-blocked": ["Canal.TyC.Sports.ar"],
    "TyC Sports (1080p) RAW": ["Canal.TyC.Sports.ar"],
    "TyC Sports (720p)": ["Canal.TyC.Sports.ar"],
    "TyC Sports 2": ["Canal.TyC.Sports.ar"],
    "TyC Sports 2 (720p)": ["Canal.TyC.Sports.ar"],
    "TyC Sports (Argentina)": ["Canal.TyC.Sports.ar"],
    "TyC Sports USA": ["Canal.TyC.Sports.ar"],
    "Telefe": ["Canal.Telefé.(Argentina).ar"],
    "Telefe (1080p)": ["Canal.Telefé.(Argentina).ar"],
    "Telefe (1080p) RAW": ["Canal.Telefé.(Argentina).ar"],
    "Telefe (720p)": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Buenos Aires (1080p)": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Internacional": ["Telefe.international.us2"],
    "Telefe Rosario Geo-blocked": ["Canal.Telefé.(Argentina).ar"],
    "El Trece": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "El Trece (1080p)": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "El Trece (480p)": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "America TV": ["Canal.America.TV.(Argentina).ar"],
    "America TV (1080p)": ["Canal.America.TV.(Argentina).ar"],
    "America TV (1080p) RAW": ["Canal.America.TV.(Argentina).ar"],
    "America TV (720p)": ["Canal.America.TV.(Argentina).ar"],
    "TV Publica (Canal 7)": ["Canal.Televisión.Pública.(Argentina).ar"],
    "TV Publica": ["Canal.Televisión.Pública.(Argentina).ar"],
    "TV Publica (1080p)": ["Canal.Televisión.Pública.(Argentina).ar"],
    "TV Publica (1080p) RAW": ["Canal.Televisión.Pública.(Argentina).ar"],
    "Television Publica (720p)": ["Canal.Televisión.Pública.(Argentina).ar"],
    "TVPublica.ar": ["Canal.Televisión.Pública.(Argentina).ar"],
    "Televisión Pública Ⓧ": ["Canal.Televisión.Pública.(Argentina).ar"],
    "TN Todo Noticias": ["Canal.Cablenoticias.ar"],
    "TN (1080p)": ["Canal.Cablenoticias.ar"],
    "TN (720p)": ["Canal.Cablenoticias.ar"],
    "TN Todo Noticias Ⓧ": ["Canal.Cablenoticias.ar"],
    "TodoNoticias.ar": ["Canal.Cablenoticias.ar"],

    # === Argentine cable/paid channels ===
    "ESPN Argentina": ["Canal.ESPN.(Argentina).ar"],
    "Cinecanal South (1080p) AR": ["Canal.Cinecanal.(Argentina).ar"],
    "El Gourmet (1080p)": ["Canal.Elgourmet.ar"],
    "El Gourmet (720p)": ["El.Gourmet.co"],
    "El Gourmet South (1080p)": ["El.Gourmet.co"],
    "El Gourmet South (720p)": ["El.Gourmet.co"],
    "Film & Arts (1080p)": ["Canal.Film.&.Arts.ar"],
    "Film & Arts (720p)": ["Canal.Film.&.Arts.ar"],
    "Europa Europa (1080p)": ["Canal.Europa.Europa.ar"],
    "Europa Europa (720p)": ["Canal.Europa.Europa.ar"],
    "History Latin America South (1080p) AR": ["Canal.History.2.(Argentina).ar"],
    "MTV Latin America (1080p) AR": ["Canal.MTV.(Argentina).ar"],
    "Sony Channel (1080p)": ["Canal.Sony.(Argentina).ar"],
    "Sony Channel (720p)": ["Sony.co"],
    "Star Channel Latin America South (1080p) AR": ["Canal.Star.Channel.(Argentina).ar"],
    "Studio Universal Latin America South (720p) AR": ["Studio.Universal.co"],
    "TNT Novelas (720p) AR": ["Canal.TNT.Novelas.(Argentina).ar"],
    "AXN Latin America South (1080p) AR": ["Canal.AXN.(Argentina).ar"],
    "AMC Latin America (1080p) AR": ["AMC.HD.us2"],
    "AMC Series Latin America (720p) AR": ["AMC+.us2"],
    "Disney Channel Latin America": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America (1080p)": ["DISNEY.+.co"],
    "Disney Channel Latin America (1080p) RAW": ["DISNEY.+.co"],
    "Disney Channel Latin America Center (1080p)": ["DISNEY.+.co"],
    "Disney Channel Latin America Mexico (576p)": ["DISNEY.+.co"],
    "Disney Channel Latin America Mexico (576p) RAW": ["DISNEY.+.co"],
    "Disney Channel Latin America Mexico (720p)": ["DISNEY.+.co"],
    "Disney Channel Latin America Panregional HD (1080p)": ["DISNEY.+.co"],
    "Disney Channel Latin America Panregional HD (1080p) RAW": ["DISNEY.+.co"],
    "Disney Channel Latin America South (1080p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America (1080p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America (576p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America (720p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America North HD (1080p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America North HD (1080p) RAW": ["DISNEY.+.co"],
    "Disney Jr. Latin America South (1080p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America South (576p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America South HD (1080p)": ["DISNEY.+.co"],
    "Disney Jr. Latin America South HD (1080p) RAW": ["DISNEY.+.co"],
    "Comedy Central Latin America (1080p) AR": ["Comedy.Central.HD.us2"],
    "A&E Latin America South (1080p) AR": ["A.and.E.HD.East.us2"],
    "E! Latin America (1080p) AR": ["E!."],
    "FX Latin America South (1080p) AR": ["FX.HD.us2"],
    "Canal Encuentro": ["Encuentro"],
    "Encuentro (720p)": ["Encuentro"],
    "Pakapaka (720p)": ["Canal.Pakapaka.ar"],
    "Cine.Ar (576p)": ["Cine.Ar"],
    "Volver (576p)": ["Volver"],
    "Volver (720p)": ["Volver"],
    "FIFA+ Hispanic America (720p) AR": ["FIFA"],
    "Fox Sports": ["FS1.Fox.Sports.1.HD.us2"],
    "Fox Sports (720p)": ["FS1.Fox.Sports.1.HD.us2"],
    "Fox Sports (720p) RAW": ["FS1.Fox.Sports.1.HD.us2"],
    "Fox Sports 2 (720p)": ["FS2.Fox.Sports.2.HD.us2"],
    "Fox Sports 3 (720p)": ["FOX.Sports.3.HD(FXS3HD).co"],
    "Fox Sports 4K (USA)": ["Fox.Sports.4K.us2"],
    "DSports": ["DIRECTV.Sports.5(DTS6).co"],
    "DSports 2": ["DIRECTV.SPORTS(DTS7).co"],
    "DSports (1080p) AR": ["DIRECTV.Sports.5(DTS6).co"],
    "DeporTV": ["DeporTV"],
    "DeporTV (1080p)": ["DeporTV"],
    "DeporTV (720p)": ["DeporTV"],

    # === Colombia ===
    "Caracol TV (Colombia)": ["Caracol.co", "CARACOL.INTERNATIONAL.us2"],

    # === Mexico ===
    "Telemundo (USA)": ["Telemundo.Satellite.Feed.us2", "Telemundo.co"],
    "Telemundo Internacional (1080p) AR": ["Telemundo.co"],

    # === Canada (likely no EPG) ===
    "TSN1 (Canada)": ["TSN1.ca"],
    "CTV (Canada)": ["CTV.ca"],

    # === UK (likely no EPG) ===
    "ITV1 (UK)": ["ITV1.uk"],

    # === USA ===
    "Fubo Sports (USA)": ["Fubo"],

    # === Argentina news/local (no EPG) ===
    "C5N Noticias": ["C5N"],
    "C5N (720p)": ["C5N"],
    "C5N (720p) RAW": ["C5N"],
    "C5N Ⓧ": ["C5N"],
    "C5N.ar": ["C5N"],
    "Canal 26": ["Canal.26"],
    "Canal 26 (1080p)": ["Canal.26"],
    "Canal 26 (1080p) RAW": ["Canal.26"],
    "Canal 26 RAW": ["Canal.26"],
    "Canal 26 Ⓧ": ["Canal.26"],
    "Canal26.ar": ["Canal.26"],
}

# Skip these channels entirely (YouTube links, radio, no EPG possible)
SKIP_CHANNELS = [
    "Aunar", "Aunar.ar", "Channel", "LN+ Ⓧ", "TECTV.ar",
    "TN (1080p) RAW", "TN (2160p)", "TN Ⓧ",
    "Pakapaka Ⓧ Ⓖ", "Encuentro Ⓧ Ⓖ",
    "Kpop Mix", "Plim Plim", "Cumbia Mix",
    "Television Publica (720p)",
    "EPG id", "Tec TV", "TN Todo Noticias Ⓨ",
    "TyC Sports Play Online", "LaNacionPlus.ar",
]


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
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.search(r'tvg-name="([^"]*)"', line)
            if m:
                name = m.group(1).strip()
                if name:
                    channels[name] = True
    return list(channels.keys())


def find_epg_channel(epg_id_pattern, epg_roots):
    """Find an EPG channel by ID pattern (case-insensitive partial match)."""
    pattern = normalize(epg_id_pattern)
    for root_idx, root in enumerate(epg_roots):
        for ch in root.findall("channel"):
            ch_id = ch.get("id", "")
            if normalize(ch_id) == pattern or pattern in normalize(ch_id):
                return ch_id, root_idx
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

    # Step 2: Extract channel names from M3U
    print("\n2. Lendo canais do M3U (tvg-name)...")
    m3u_names = get_channels_from_m3u(M3U_PATH)
    print(f"   {len(m3u_names)} canais encontrados no M3U")

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

    for name in m3u_names:
        # Skip certain channels
        if name in SKIP_CHANNELS:
            skipped.append(name)
            print(f"   SKIP {name}")
            continue

        # Look up manual mapping
        epg_ids = CHANNEL_MAP.get(name)
        if epg_ids:
            found = False
            for epg_id in epg_ids:
                src_id, src_root_idx = find_epg_channel(epg_id, epg_roots)
                if src_id:
                    channel_map[name] = (src_id, src_root_idx)
                    print(f"   OK   {name} -> {src_id}")
                    found = True
                    break
            if not found:
                unmapped.append(name)
                print(f"   ---  {name} -> EPG ID '{epg_ids[0]}' não encontrado")
        else:
            unmapped.append(name)
            print(f"   ---  {name} -> sem mapeamento")

    print(f"\n   Resumo:")
    print(f"   Mapeados: {len(channel_map)}/{len(m3u_names)}")
    print(f"   Sem EPG:  {len(unmapped)}")
    print(f"   Pulados:  {len(skipped)}")

    # Step 5: Build filtered output XML
    print("\n5. Construindo XML filtrado...")
    tv_root = ET.Element("tv", {
        "generator-info-name": "JCTV EPG Generator",
        "source-info-url": "https://epgshare01.online",
    })

    # Add channel definitions from matched EPG channels
    for name, (src_id, src_root_idx) in channel_map.items():
        epg_root = epg_roots[src_root_idx]
        for ch in epg_root.findall("channel"):
            if ch.get("id") == src_id:
                new_ch = ET.SubElement(tv_root, "channel", id=src_id)
                dn = ch.find("display-name")
                if dn is not None and dn.text:
                    ET.SubElement(new_ch, "display-name", lang="en").text = dn.text
                ET.SubElement(new_ch, "display-name", lang="pt").text = name
                icon = ch.find("icon")
                if icon is not None:
                    new_ch.append(icon)
                break

    # Copy programmes from matched channels
    print("   Copiando programas de canais mapeados...")
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
    print(f"Concluído! {OUTPUT}:")
    print(f"  Canais: {total_channels}")
    print(f"  Programas: {total_programmes}")
    print(f"  Tamanho: {size_kb:.1f} KB")
    print(f"  Mapeados: {len(channel_map)}/{len(m3u_names)}")
    print(f"{'=' * 60}")

    if unmapped:
        print(f"\nCanais sem EPG ({len(unmapped)}):")
        for name in unmapped:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
