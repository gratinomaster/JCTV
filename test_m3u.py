#!/usr/bin/env python3
import subprocess, sys

input_file = "lista5.m3u"
output_file = "lista5.m3u"

with open(input_file, "r") as f:
    lines = f.readlines()

entries = []
i = 0
while i < len(lines):
    line = lines[i]
    if line.startswith("#EXTINF:"):
        if i + 1 < len(lines) and not lines[i+1].startswith("#"):
            entries.append((line, lines[i+1]))
            i += 2
        else:
            i += 1
    elif line.startswith("#EXTM3U"):
        header = line
        i += 1
    else:
        i += 1

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def test_url(url):
    try:
        r = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "10", "--max-time", "15", "-L",
             "-A", UA, url],
            capture_output=True, text=True, timeout=20
        )
        code = r.stdout.strip()
        return code.startswith("2")
    except:
        return False

working = []
total = len(entries)
for extinf, url in entries:
    name = extinf.split(",")[-1].strip()
    ok = test_url(url)
    status = "OK" if ok else "FAIL"
    print(f"  {status}: {name} -> {url[:60]}...")
    if ok:
        working.append((extinf, url))

with open(output_file, "w") as f:
    f.write(header)
    for extinf, url in working:
        f.write(extinf)
        f.write(url)

print(f"\nDone. {len(working)}/{total} channels working.")
