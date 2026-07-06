#!/usr/bin/env python3
import subprocess
import sys
import re
from urllib.parse import urlparse

M3U_FILE = "/home/runner/work/JCTV/JCTV/lista5.m3u"

with open(M3U_FILE, "r") as f:
    lines = f.readlines()

# Parse EXTINF + URL pairs
entries = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    if line.startswith("#EXTM3U"):
        i += 1
        continue
    if line.startswith("#EXTINF:"):
        if i + 1 < len(lines):
            url = lines[i + 1].strip()
            entries.append((line, url))
            i += 2
            continue
    i += 1

print(f"Total entries found: {len(entries)}")

# Deduplicate by URL (keeping first occurrence per channel name)
seen_urls = set()
unique_entries = []
for extinf, url in entries:
    if url not in seen_urls:
        seen_urls.add(url)
        unique_entries.append((extinf, url))

print(f"Unique URLs: {len(unique_entries)}")

# Test each URL
import concurrent.futures

def test_url(url, timeout=10):
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        code = result.stdout.strip()
        if code in ("200", "201", "202", "204", "301", "302", "303", "307", "308"):
            return True
        return False
    except Exception as e:
        return False

working_entries = []
for extinf, url in unique_entries:
    print(f"  Testing: {extinf[:80]}...", end=" ", flush=True)
    if test_url(url):
        print("WORKING")
        working_entries.append((extinf, url))
    else:
        print("FAILED")

print(f"\nWorking channels: {len(working_entries)}")

# Write new M3U
with open(M3U_FILE, "w") as f:
    f.write("#EXTM3U\n")
    for extinf, url in working_entries:
        f.write(extinf + "\n")
        f.write(url + "\n")

print(f"Written {len(working_entries)} entries to {M3U_FILE}")
