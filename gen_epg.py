#!/usr/bin/env python3
"""Download EPG, filter to only M3U channels, save as EPGFULL.xml.gz"""
import re
import gzip
import os
import urllib.request
from datetime import datetime, timedelta, timezone
import xml.etree.ElementTree as ET

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"
EPG_SOURCES = [
    "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml",
]
GLOBO_EPG = "GLOBOEPG.xml.gz"

print("=== ETAPA 1: Baixar M3U ===")
req = urllib.request.Request(M3U_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    m3u_data = r.read().decode("utf-8", errors="ignore")

channel_info = {}
extinf_pattern = re.compile(
    r'#EXTINF:.*?tvg-id="(?P<tvg_id>[^"]*)"\s+'
    r'tvg-name="(?P<tvg_name>[^"]*)"\s+'
    r'tvg-logo="(?P<tvg_logo>[^"]*)"'
)
for m in extinf_pattern.finditer(m3u_data):
    cid = m.group("tvg_id")
    if cid and cid not in channel_info:
        channel_info[cid] = {
            "name": m.group("tvg_name"),
            "logo": m.group("tvg_logo"),
        }

wanted_ids = list(channel_info.keys())
print(f"  Canais: {len(wanted_ids)}")
for cid in wanted_ids:
    print(f"    - {cid} ({channel_info[cid]['name']})")

epg_url_match = re.search(r'x-tvg-url="([^"]+)"', m3u_data)
if epg_url_match:
    epg_url = epg_url_match.group(1)
    if epg_url not in EPG_SOURCES:
        EPG_SOURCES.insert(0, epg_url)
    print(f"\n  Fonte EPG do M3U: {epg_url}")

print("\n=== ETAPA 2: Baixar EPGs ===")
all_epg_data = []
for url in EPG_SOURCES:
    try:
        print(f"  Baixando: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
        if url.endswith(".gz"):
            data = gzip.decompress(raw).decode("utf-8", errors="ignore")
        else:
            data = raw.decode("utf-8", errors="ignore")
        print(f"    Tamanho: {len(data) / 1024 / 1024:.1f} MB")
        all_epg_data.append(data)
    except Exception as e:
        print(f"    ERRO: {e}")

if os.path.exists(GLOBO_EPG):
    try:
        print(f"  Lendo EPG local: {GLOBO_EPG}")
        with gzip.open(GLOBO_EPG, "rt", encoding="utf-8") as f:
            all_epg_data.append(f.read())
        print(f"    OK: {os.path.getsize(GLOBO_EPG):,} bytes")
    except Exception as e:
        print(f"    ERRO: {e}")

print(f"\n  Total EPGs carregados: {len(all_epg_data)}")

print("\n=== ETAPA 3: Filtrar canais e programas ===")
now = datetime.now(timezone.utc)
cutoff = now + timedelta(days=2)
cutoff_str = cutoff.strftime("%Y%m%d235959")
today_str = now.strftime("%Y%m%d")
tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")

channels_xml = []
programmes_xml = []
channels_found = set()
channels_not_found = set(wanted_ids)

for epg_data in all_epg_data:
    for cid in list(channels_not_found):
        pat = re.compile(rf'<channel\s+id="{re.escape(cid)}"[^>]*>.*?</channel>', re.DOTALL)
        m = pat.search(epg_data)
        if m:
            channels_xml.append(m.group(0))
            channels_found.add(cid)
            channels_not_found.discard(cid)

    for cid in wanted_ids:
        pat = re.compile(rf'<programme\s+[^>]*channel="{re.escape(cid)}"[^>]*>.*?</programme>', re.DOTALL)
        for m in pat.finditer(epg_data):
            start_match = re.search(r'start="(\d{14})', m.group(0))
            if start_match and start_match.group(1) <= cutoff_str:
                programmes_xml.append(m.group(0))

for cid in wanted_ids:
    if cid in channels_found:
        print(f"  Canal OK: {cid}")
    else:
        print(f"  Canal FALTA (criando definicao): {cid}")
        name = channel_info[cid]["name"]
        logo = channel_info[cid]["logo"]
        chan_xml = f'  <channel id="{cid}">\n    <display-name>{name}</display-name>\n'
        if logo:
            chan_xml += f'    <icon src="{logo}"/>\n'
        chan_xml += "  </channel>"
        channels_xml.append(chan_xml)

print(f"  Programas coletados: {len(programmes_xml)}")

print("\n=== ETAPA 4: Gerar EPGFULL.xml.gz ===")
xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv>']
xml_parts.extend(channels_xml)
xml_parts.extend(programmes_xml)
xml_parts.append('</tv>')
full_xml = '\n'.join(xml_parts)

with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
    f.write(full_xml)

size = os.path.getsize(OUTPUT)
print(f"  Arquivo: {OUTPUT} ({size:,} bytes)")

print("\n=== ETAPA 5: Validar ===")
with gzip.open(OUTPUT, "rt", encoding="utf-8") as f:
    content = f.read()

ch_count = content.count("<channel ")
prog_count = content.count("<programme ")

print(f"  Canais: {ch_count}")
print(f"  Programas: {prog_count}")

for cid in wanted_ids:
    ch_found = f'id="{cid}"' in content
    progs = len(re.findall(rf'channel="{re.escape(cid)}"', content))
    print(f"    {cid}: {'OK' if ch_found else 'FALTA'} ({progs} programas)")

print(f"  Programas de hoje ({today_str}): {content.count(today_str)}")
print(f"  Programas de amanha ({tomorrow_str}): {content.count(tomorrow_str)}")

print("\n=== CONCLUIDO ===")
