#!/usr/bin/env python3
import subprocess
import sys
import os
import re
from urllib.parse import urlparse

M3U_FILE = 'lista5.m3u'

with open(M3U_FILE, 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

if not lines or lines[0].strip() != '#EXTM3U':
    print("ERROR: Not a valid M3U file (missing #EXTM3U header)")
    sys.exit(1)

entries = []
i = 1
while i < len(lines):
    line = lines[i].strip()
    if line.startswith('#EXTINF:'):
        if i + 1 < len(lines):
            url = lines[i + 1].strip()
            entries.append((lines[i], lines[i + 1], line, url))
            i += 2
        else:
            i += 1
    else:
        i += 1

print(f"Found {len(entries)} channel entries")

working_entries = []
tested = {}

for extinf, url_line, extinf_raw, url in entries:
    if url in tested:
        if tested[url]:
            working_entries.append((extinf, url_line))
        continue

    print(f"Testing: {url[:80]}...", end=' ', flush=True)
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', '10', '-I', url],
            capture_output=True, text=True, timeout=15
        )
        http_code = result.stdout.strip()
        if http_code and http_code[0] in ('2', '3'):
            print(f"OK ({http_code})")
            tested[url] = True
            working_entries.append((extinf, url_line))
        else:
            print(f"FAIL ({http_code})")
            tested[url] = False
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        tested[url] = False
    except Exception as e:
        print(f"ERROR: {e}")
        tested[url] = False

print(f"\nWorking entries: {len(working_entries)} / {len(entries)}")

if len(working_entries) == 0:
    print("No working channels found. Keeping original file.")
    sys.exit(0)

with open(M3U_FILE, 'w', encoding='utf-8') as f:
    f.write('#EXTM3U\n')
    for extinf, url_line in working_entries:
        f.write(extinf + '\n')
        f.write(url_line + '\n')

print(f"Overwritten {M3U_FILE} with {len(working_entries)} working channels")
