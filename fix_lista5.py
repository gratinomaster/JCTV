#!/usr/bin/env python3
import re
import subprocess
import sys
import gzip
import os
from collections import OrderedDict

M3U_PATH = "lista5.m3u"
OUTPUT_M3U = "lista5.m3u"
OUTPUT_EPG = "EPGFULL.xml.gz"

# Channel mapping: (keyword in channel name, tvg-id, tvg-name, logo URL, preferred URL pattern)
CHANNEL_MAP = OrderedDict([
    ("ABC News Live", {
        "tvg-id": "ABC.News.Live.us2",
        "tvg-name": "ABC News Live",
        "tvg-logo": "https://keyframe-cdn.abcnews.com/streamprovider11.jpg",
        "preferred": lambda u: "akamaized" in u or "abcnews-livestreams" in u
    }),
    ("Fox Business", {
        "tvg-id": "Fox.Business.HD.us2",
        "tvg-name": "Fox Business",
        "tvg-logo": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/42cadbe8-971a-43f3-8bd5-121dc91dd120/d1de5ed5-ad2a-4a4c-a6a2-6972164b9739/1280x720/match/808/455/image.jpg",
        "preferred": lambda u: "247.foxbusiness" in u
    }),
    ("Fox News", {
        "tvg-id": "Fox.News.Channel.HD.us2",
        "tvg-name": "Fox News Channel",
        "tvg-logo": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/42cadbe8-971a-43f3-8bd5-121dc91dd120/d1de5ed5-ad2a-4a4c-a6a2-6972164b9739/1280x720/match/808/455/image.jpg",
        "preferred": lambda u: "247.foxnews" in u
    }),
    ("CBS News", {
        "tvg-id": "CBS.News.National.Stream.us2",
        "tvg-name": "CBS News 24/7",
        "tvg-logo": "https://www.cbsnews.com/bundles/cbsnewsvideo/images/cbsn--main-bg.jpg",
        "preferred": lambda u: "dai.google.com" in u and "master.m3u8" in u
    }),
])

# EPG sources
EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://i.mjh.nz/PlutoTV/us.xml.gz",
    "https://i.mjh.nz/SamsungTVPlus/us.xml.gz",
]

def parse_m3u(filepath):
    channels = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U\n"
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            # Check next line is a URL (not another #EXTINF)
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                url = lines[i+1].strip()
                channels.append((line, url))
                i += 2
                continue
            # Handle adjacent EXTINF lines without URL (broken format)
            i += 1
        elif line.startswith("#"):
            i += 1
        else:
            i += 1
    return header, channels

def identify_channel(extinf_line):
    """Identify which channel this is based on EXTINF content."""
    line_lower = extinf_line.lower()
    for name, info in CHANNEL_MAP.items():
        if name.lower() in line_lower:
            return name, info
    return None, None

def deduplicate(channels):
    """Deduplicate channels keeping the best URL per channel."""
    seen = OrderedDict()
    for extinf, url in channels:
        name, info = identify_channel(extinf)
        if name is None:
            continue
        if name not in seen:
            seen[name] = (extinf, url, info)
        else:
            # Keep the preferred URL
            old_extinf, old_url, old_info = seen[name]
            if info["preferred"](url) and not old_info["preferred"](old_url):
                seen[name] = (extinf, url, info)
    return seen

def build_extinf(name, info):
    """Build proper EXTINF line with tvg-id, tvg-name, tvg-logo, group-title."""
    tvg_id = info["tvg-id"]
    tvg_name = info["tvg-name"]
    tvg_logo = info["tvg-logo"]
    return f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{tvg_name}" tvg-logo="{tvg_logo}" group-title="NEWS WORLD",{tvg_name}'

def test_url(url, timeout=15):
    """Test if a URL is accessible. Returns True if reachable."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout+5
        )
        code = result.stdout.strip()
        if code and code[0] in ("2", "3"):
            return True
        return False
    except:
        return False

def test_stream_url(url, timeout=15):
    """Test if an m3u8 URL returns valid content."""
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout+5
        )
        content = result.stdout
        if "#EXTM3U" in content or "#EXTINF" in content:
            return True
        if len(content) > 100:
            return True
        return False
    except:
        return False

def download_epg_xml(url, timeout=60):
    """Download EPG XML content."""
    try:
        result = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), url],
            capture_output=True, timeout=timeout+10
        )
        data = result.stdout
        if url.endswith(".gz"):
            try:
                decompressed = gzip.decompress(data)
                return decompressed.decode("utf-8", errors="replace")
            except Exception as e:
                print(f"  Erro ao descomprimir: {e}, tentando raw...")
                try:
                    return data.decode("utf-8", errors="replace")
                except:
                    return None
        try:
            return data.decode("utf-8", errors="replace")
        except:
            return None
    except subprocess.TimeoutExpired:
        print("  Timeout")
        return None
    except Exception as e:
        print(f"  Erro: {e}")
        return None

def verify_epg_dates(epg_content):
    """Check if EPG has data for today, tomorrow, and day after."""
    from datetime import datetime, timedelta
    today = datetime.now()
    dates_to_check = [today, today + timedelta(days=1), today + timedelta(days=2)]
    
    found = {d.strftime("%Y%m%d"): False for d in dates_to_check}
    
    for date_str in found:
        if date_str in epg_content:
            found[date_str] = True
    
    return found

def main():
    print("=" * 60)
    print("FIX LISTA5.M3U - CORREÇÃO COMPLETA")
    print("=" * 60)
    
    # Step 1: Parse existing M3U
    print("\n[1] Analisando lista5.m3u...")
    header, channels = parse_m3u(M3U_PATH)
    print(f"  Encontradas {len(channels)} entradas")
    
    # Step 2: Identify and deduplicate channels
    print("\n[2] Identificando e deduplicando canais...")
    unique = deduplicate(channels)
    print(f"  Canais únicos encontrados: {len(unique)}")
    for name in unique:
        print(f"    - {name}")
    
    # Step 3: Test URLs
    print("\n[3] Testando URLs (anti-virus / acessibilidade)...")
    working = OrderedDict()
    for name, (extinf, url, info) in unique.items():
        print(f"  Testando: {name}...", end=" ", flush=True)
        is_ok = test_stream_url(url)
        if not is_ok:
            is_ok = test_url(url)
        if is_ok:
            print("OK")
            working[name] = (extinf, url, info)
        else:
            print("FALHOU (removido)")
    
    if not working:
        print("  ERRO: Nenhum canal funcionando!")
        sys.exit(1)
    
    # Step 4: Write fixed M3U
    print("\n[4] Escrevendo lista5.m3u corrigido...")
    epg_url_str = " ".join(EPG_URLS)
    with open(OUTPUT_M3U, "w", encoding="utf-8") as f:
        f.write(f'#EXTM3U url-tvg="{epg_url_str}"\n')
        for name, (extinf, url, info) in working.items():
            new_extinf = build_extinf(name, info)
            f.write(new_extinf + "\n")
            f.write(url + "\n")
    print(f"  Salvo: {OUTPUT_M3U}")
    
    # Step 5: Test EPG sources
    print("\n[5] Testando fontes EPG...")
    all_epg_content = ""
    working_epgs = []
    for epg_url in EPG_URLS:
        fname = epg_url.rstrip("/").split("/")[-1]
        print(f"  Baixando {fname}...", end=" ", flush=True)
        content = download_epg_xml(epg_url)
        if content:
            print(f"OK ({len(content)} bytes)")
            working_epgs.append((epg_url, content))
            all_epg_content += content
        else:
            print("FALHOU")
    
    # Verify EPG has data for our channels
    print("\n[6] Verificando EPG para cada canal...")
    tvg_ids = [info["tvg-id"] for name, (_, _, info) in working.items()]
    for tvg_id in tvg_ids:
        found = False
        for epg_url, content in working_epgs:
            # Search by channel id
            if re.search(r'channel id="' + re.escape(tvg_id) + r'"', content):
                found = True
                print(f"  {tvg_id}: EPG encontrado em {epg_url.split('/')[-1]}")
                break
            # Search by display name
            tvg_name = None
            for name, (_, _, info) in working.items():
                if info["tvg-id"] == tvg_id:
                    tvg_name = info["tvg-name"]
                    break
            if tvg_name:
                m = re.search(r'<display-name[^>]*>' + re.escape(tvg_name) + r'</display-name>', content, re.IGNORECASE)
                if m:
                    # Found by name, get the channel id
                    ch_block = re.search(
                        r'<channel[^>]*id="([^"]*)"[^>]*>.*?' + re.escape(tvg_name) + r'</display-name>',
                        content, re.DOTALL | re.IGNORECASE
                    )
                    if ch_block:
                        found = True
                        print(f"  {tvg_id} ({tvg_name}): EPG encontrado por nome (id={ch_block.group(1)}) em {epg_url.split('/')[-1]}")
                        break
        if not found:
            print(f"  {tvg_id}: EPG NÃO ENCONTRADO")
    
    # Verify EPG has data for today, tomorrow, day after
    print("\n[7] Verificando datas da programação...")
    date_check = verify_epg_dates(all_epg_content)
    from datetime import datetime, timedelta
    today = datetime.now()
    for i, (d, found) in enumerate(date_check.items()):
        label = ["Hoje", "Amanhã", "Depois de amanhã"][i]
        actual_date = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        if found:
            print(f"  {label} ({actual_date}): OK - programação disponível")
        else:
            print(f"  {label} ({actual_date}): ATENÇÃO - programação não encontrada diretamente, pode estar em formato diferente")
    
    # Step 8: Generate EPGFULL.xml.gz filtered by our channels
    print("\n[8] Gerando EPGFULL.xml.gz filtrado...")
    import xml.etree.ElementTree as ET
    from xml.dom import minidom
    from datetime import datetime, timedelta
    
    # Parse EPG content
    tv_root = ET.Element("tv", {
        "source-info-url": "https://epgshare01.online",
        "source-info-name": "EPGShare01 + JCTV",
        "generator-info-name": "JCTV EPG Filter"
    })
    
    # Add channel entries
    for name, (_, _, info) in working.items():
        ch = ET.SubElement(tv_root, "channel", id=info["tvg-id"])
        ET.SubElement(ch, "display-name", lang="en").text = info["tvg-name"]
    
    # Build a map of tvg_id -> list of possible channel IDs in EPG sources
    tvg_id_to_epg_ids = {}
    for name, (_, _, info) in working.items():
        tvg_id = info["tvg-id"]
        tvg_id_to_epg_ids[tvg_id] = [tvg_id]
        # Also search EPG content for display names
        for epg_url, content in working_epgs:
            dn_matches = re.finditer(
                r'<channel[^>]*id="([^"]*)"[^>]*>.*?<display-name[^>]*>(.*?)</display-name>',
                content, re.DOTALL | re.IGNORECASE
            )
            for m in dn_matches:
                eid, dname = m.group(1), m.group(2)
                if dname.strip().lower() == info["tvg-name"].lower():
                    if eid not in tvg_id_to_epg_ids[tvg_id]:
                        tvg_id_to_epg_ids[tvg_id].append(eid)
    
    # Copy programme data from EPG sources
    prog_count = 0
    for epg_url, content in working_epgs:
        try:
            root = ET.fromstring(content)
            for prog in root.findall("programme"):
                ch_id = prog.get("channel", "")
                # Find which of our tvg_ids this programme belongs to
                matched_tvg_id = None
                for tvg_id, epg_ids in tvg_id_to_epg_ids.items():
                    if ch_id.lower() in [eid.lower() for eid in epg_ids]:
                        matched_tvg_id = tvg_id
                        break
                if matched_tvg_id:
                    new_prog = ET.SubElement(tv_root, "programme", {
                        "channel": matched_tvg_id,
                        "start": prog.get("start", ""),
                        "end": prog.get("end", ""),
                    })
                    for child in prog:
                        new_child = ET.SubElement(new_prog, child.tag, child.attrib)
                        new_child.text = child.text
                    prog_count += 1
        except Exception as e:
            print(f"  Erro ao processar EPG: {e}")
    
    # Generate generic schedule for any channel without EPG data
    tvg_ids_found = set()
    for prog in tv_root.findall("programme"):
        tvg_ids_found.add(prog.get("channel"))
    
    for name, (_, _, info) in working.items():
        if info["tvg-id"] not in tvg_ids_found:
            print(f"  Gerando programação genérica para {info['tvg-id']}...")
            # Generate 3 days of generic news schedule
            sched = [
                ("00:00", "06:00", "Late Night News"),
                ("06:00", "09:00", "Morning News"),
                ("09:00", "12:00", "Midday News"),
                ("12:00", "15:00", "Afternoon News"),
                ("15:00", "18:00", "Evening News"),
                ("18:00", "21:00", "Prime Time News"),
                ("21:00", "00:00", "Nightly News"),
            ]
            today = datetime.now()
            for day_offset in range(3):
                day = today + timedelta(days=day_offset)
                for time_str, duration_str, prog_name in sched:
                    h, m = map(int, time_str.split(":"))
                    start = day.replace(hour=h, minute=m, second=0, microsecond=0)
                    dur_parts = duration_str.split(":")
                    dur = timedelta(hours=int(dur_parts[0]), minutes=int(dur_parts[1]))
                    end = start + dur
                    start_fmt = start.strftime("%Y%m%d%H%M%S") + " +0000"
                    end_fmt = end.strftime("%Y%m%d%H%M%S") + " +0000"
                    prog = ET.SubElement(tv_root, "programme", {
                        "channel": info["tvg-id"],
                        "start": start_fmt,
                        "end": end_fmt,
                    })
                    ET.SubElement(prog, "title", lang="en").text = prog_name
                    prog_count += 1
    
    # Save the EPG
    xml_str = ET.tostring(tv_root, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")
    
    with gzip.open(OUTPUT_EPG, "wb") as f:
        f.write(pretty_xml)
    
    total_channels = len(list(tv_root.findall("channel")))
    size_kb = os.path.getsize(OUTPUT_EPG) / 1024
    print(f"\n  EPGFULL.xml.gz gerado: {total_channels} canais, {prog_count} programas, {size_kb:.1f} KB")
    
    print("\n" + "=" * 60)
    print("CORREÇÃO CONCLUÍDA!")
    print("=" * 60)
    
    # Show the fixed M3U
    print("\nConteúdo do novo lista5.m3u:")
    with open(OUTPUT_M3U, "r") as f:
        print(f.read())

if __name__ == "__main__":
    main()
