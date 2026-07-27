#!/usr/bin/env python3
"""Download Freeview EPG, filter to only M3U channels, save as EPGFULL.xml.gz"""
import re
import gzip
import os
import urllib.request
from datetime import datetime, timedelta

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
EPG_URL = "https://raw.githubusercontent.com/dp247/Freeview-EPG/master/epg.xml"
OUTPUT = "EPGFULL.xml.gz"

print("=== ETAPA 1: Baixar M3U ===")
req = urllib.request.Request(M3U_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    m3u_data = r.read().decode("utf-8", errors="ignore")

wanted_ids = re.findall(r'tvg-id="([^"]+)"', m3u_data)
wanted_set = set(wanted_ids)
print(f"  Canais: {len(wanted_ids)}")
for cid in wanted_ids:
    print(f"    - {cid}")

print("\n=== ETAPA 2: Baixar EPG ===")
req = urllib.request.Request(EPG_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=120) as r:
    epg_data = r.read().decode("utf-8", errors="ignore")
print(f"  Tamanho: {len(epg_data) / 1024 / 1024:.1f} MB")

print("\n=== ETAPA 3: Filtrar canais e programas ===")
now = datetime.utcnow()
tomorrow = now + timedelta(days=2)
cutoff_str = tomorrow.strftime("%Y%m%d235959")

channels_xml = []
for cid in wanted_ids:
    pat = re.compile(rf'<channel\s+id="{re.escape(cid)}"[^>]*>.*?</channel>', re.DOTALL)
    m = pat.search(epg_data)
    if m:
        channels_xml.append(m.group(0))
        print(f"  Canal OK: {cid}")
    else:
        print(f"  Canal FALTA: {cid}")

programmes_xml = []
for cid in wanted_ids:
    pat = re.compile(rf'<programme\s+[^>]*channel="{re.escape(cid)}"[^>]*>.*?</programme>', re.DOTALL)
    for m in pat.finditer(epg_data):
        start_match = re.search(r'start="(\d{14})', m.group(0))
        if start_match and start_match.group(1) <= cutoff_str:
            programmes_xml.append(m.group(0))

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
today_str = now.strftime("%Y%m%d")
tomorrow_str = (now + timedelta(days=1)).strftime("%Y%m%d")
day2_str = tomorrow.strftime("%Y%m%d")

print(f"  Canais: {ch_count}")
print(f"  Programas: {prog_count}")

for cid in wanted_ids:
    ch_found = f'id="{cid}"' in content
    progs = len(re.findall(rf'channel="{re.escape(cid)}"', content))
    print(f"    {cid}: {'OK' if ch_found else 'FALTA'} ({progs} programas)")

print(f"  Programas de hoje ({today_str}): {content.count(today_str)}")
print(f"  Programas de amanha ({tomorrow_str}): {content.count(tomorrow_str)}")
print(f"  Programas de depois ({day2_str}): {content.count(day2_str)}")

print("\n=== CONCLUIDO ===")
