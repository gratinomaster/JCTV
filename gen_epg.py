#!/usr/bin/env python3
"""Stream-download the big EPG, filter to only M3U channels, save as EPGFULL.xml.gz"""
import re
import gzip
import subprocess
import sys
from datetime import datetime, timedelta

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
EPG_URL = "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"
OUTPUT = "EPGFULL.xml.gz"

import urllib.request

print("=== ETAPA 1: Baixar M3U ===")
req = urllib.request.Request(M3U_URL, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    m3u_data = r.read().decode("utf-8", errors="ignore")

wanted_ids = re.findall(r'tvg-id="([^"]+)"', m3u_data)
wanted_set = set(wanted_ids)
print(f"  Canais: {len(wanted_ids)}")
for cid in wanted_ids:
    print(f"    - {cid}")

print("\n=== ETAPA 2: Baixar e filtrar EPG (streaming) ===")

now = datetime.utcnow()
tomorrow = now + timedelta(days=1)
cutoff_str = tomorrow.strftime("%Y%m%d235959")

proc = subprocess.Popen(
    ["curl", "-s", "--max-time", "300", EPG_URL],
    stdout=subprocess.PIPE,
    bufsize=65536
)

channels_xml = []
programmes_xml = []
channel_ids_found = set()
in_programme = False
buf = b""
bytes_read = 0

try:
    while True:
        chunk = proc.stdout.read(65536)
        if not chunk:
            break
        buf += chunk
        bytes_read += len(chunk)

        if bytes_read % (5 * 1024 * 1024) < 65536:
            print(f"  Progresso: {bytes_read / 1024 / 1024:.1f} MB lidos, {len(channel_ids_found)} canais, {len(programmes_xml)} programas", flush=True)

        text = buf.decode("utf-8", errors="ignore")
        
        # Process complete tags
        while True:
            # Find channel tag
            ch_match = re.search(r'<channel\s+id="([^"]*)"[^>]*>.*?</channel>', text, re.DOTALL)
            if ch_match:
                ch_id = ch_match.group(1)
                if ch_id in wanted_set:
                    channels_xml.append(ch_match.group(0))
                    channel_ids_found.add(ch_id)
                    print(f"    Canal encontrado: {ch_id}")
                text = text[:ch_match.start()] + text[ch_match.end():]
                continue
            
            # Find programme tag  
            prog_match = re.search(r'<programme\s+[^>]*?channel="([^"]*)"[^>]*?>.*?</programme>', text, re.DOTALL)
            if prog_match:
                ch_id = prog_match.group(1)
                if ch_id in wanted_set:
                    # Check start time
                    start_match = re.search(r'start="(\d{14})"', prog_match.group(0))
                    if start_match:
                        start = start_match.group(1)
                        if start <= cutoff_str:
                            programmes_xml.append(prog_match.group(0))
                text = text[:prog_match.start()] + text[prog_match.end():]
                continue
            
            break
        
        buf = text.encode("utf-8")

except KeyboardInterrupt:
    pass
finally:
    proc.terminate()

print(f"\n  Total bytes lidos: {bytes_read / 1024 / 1024:.1f} MB")
print(f"  Canais encontrados: {len(channel_ids_found)}/{len(wanted_ids)}")
print(f"  Programas coletados: {len(programmes_xml)}")

missing = wanted_set - channel_ids_found
if missing:
    print(f"  SEM EPG: {missing}")

print("\n=== ETAPA 3: Gerar EPGFULL.xml.gz ===")
xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv>']
xml_parts.extend(channels_xml)
xml_parts.extend(programmes_xml)
xml_parts.append('</tv>')
full_xml = '\n'.join(xml_parts)

with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
    f.write(full_xml)

import os
size = os.path.getsize(OUTPUT)
print(f"  Arquivo: {OUTPUT} ({size:,} bytes)")

print("\n=== ETAPA 4: Validar ===")
with gzip.open(OUTPUT, "rt", encoding="utf-8") as f:
    content = f.read()

ch_count = content.count("<channel ")
prog_count = content.count("<programme ")
today_str = now.strftime("%Y%m%d")
tomorrow_str = tomorrow.strftime("%Y%m%d")
today_progs = content.count(today_str)
tomorrow_progs = content.count(tomorrow_str)

print(f"  Canais: {ch_count}")
print(f"  Programas: {prog_count}")
print(f"  Programas de hoje ({today_str}): {today_progs}")
print(f"  Programas de amanha ({tomorrow_str}): {tomorrow_progs}")

for cid in wanted_ids:
    found = f'"{cid}"' in content
    print(f"    {cid}: {'OK' if found else 'FALTA'}")

print("\n=== CONCLUIDO ===")
