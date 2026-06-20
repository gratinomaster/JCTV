#!/usr/bin/env python3
import subprocess
import sys
import re
import urllib.parse

M3U_FILE = "/home/runner/work/JCTV/JCTV/lista5.m3u"

with open(M3U_FILE, "r") as f:
    lines = f.readlines()

if not lines or not lines[0].strip() == "#EXTM3U":
    print("Invalid M3U file", file=sys.stderr)
    sys.exit(1)

entries = []
i = 1
while i < len(lines):
    line = lines[i].strip()
    if line.startswith("#EXTINF:"):
        extinf = line
        i += 1
        if i < len(lines):
            url = lines[i].strip()
            entries.append((extinf, url))
            i += 1
        else:
            break
    else:
        i += 1

print(f"Total entries: {len(entries)}")

channel_groups = []
current_group = []

for extinf, url in entries:
    if not current_group:
        current_group.append((extinf, url))
    else:
        prev_extinf = current_group[-1][0]
        if extinf == prev_extinf:
            current_group.append((extinf, url))
        else:
            channel_groups.append(current_group)
            current_group = [(extinf, url)]

if current_group:
    channel_groups.append(current_group)

print(f"Unique channel groups: {len(channel_groups)}")

working_groups = []
for idx, group in enumerate(channel_groups):
    primary_url = group[0][1]
    channel_name = group[0][0]
    print(f"[{idx+1}/{len(channel_groups)}] Testing: {channel_name[:60]}...", end=" ", flush=True)

    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "10", "--max-time", "15", "-I", primary_url],
            capture_output=True, text=True, timeout=20
        )
        http_code = result.stdout.strip()
        
        if http_code and http_code[0] in ("2", "3"):
            print(f"OK ({http_code})")
            working_groups.append(group)
        elif http_code == "0" or not http_code:
            result2 = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--connect-timeout", "10", "--max-time", "15", primary_url],
                capture_output=True, text=True, timeout=20
            )
            http_code2 = result2.stdout.strip()
            if http_code2 and http_code2[0] in ("2", "3"):
                print(f"OK ({http_code2})")
                working_groups.append(group)
            else:
                print(f"DEAD ({http_code2 or 'no response'})")
        else:
            print(f"DEAD ({http_code})")
    except subprocess.TimeoutExpired:
        print("DEAD (timeout)")
    except Exception as e:
        print(f"DEAD ({e})")

print(f"\nWorking channels: {len(working_groups)}/{len(channel_groups)}")

with open(M3U_FILE, "w") as f:
    f.write("#EXTM3U\n")
    for group in working_groups:
        for extinf, url in group:
            f.write(extinf + "\n")
            f.write(url + "\n")

print(f"Updated {M3U_FILE}")
