#!/usr/bin/env python3
import urllib.request
import urllib.error
import ssl
import sys
import time

INPUT = "lista5.m3u"
OUTPUT = "lista5.m3u"
TIMEOUT = 15
MAX_RETRIES = 2

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

def test_url(url):
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36")
            resp = urllib.request.urlopen(req, timeout=TIMEOUT, context=ssl_ctx)
            code = resp.getcode()
            if code == 200 or code == 206:
                return True
            else:
                return False
        except (urllib.error.HTTPError, urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as e:
            if attempt < MAX_RETRIES - 1:
                time.sleep(2)
                continue
            return False
    return False

with open(INPUT, "r", encoding="utf-8") as f:
    lines = f.readlines()

entries = []
i = 0
while i < len(lines):
    line = lines[i].strip()
    if line.startswith("#EXTM3U"):
        entries.append(("#EXTM3U\n", None))
        i += 1
    elif line.startswith("#EXTINF:"):
        extinf = lines[i]
        i += 1
        if i < len(lines):
            url = lines[i]
            entries.append((extinf, url))
            i += 1
    else:
        i += 1

print(f"Found {len(entries) - 1} channel entries to test (excluding header)", flush=True)

working = []
for idx, (extinf, url) in enumerate(entries):
    if extinf.strip() == "#EXTM3U":
        working.append((extinf, url))
        continue
    
    channel_name = extinf.strip().split(",")[-1] if "," in extinf else "unknown"
    sys.stdout.write(f"[{idx}/{len(entries)-1}] Testing: {channel_name[:50]:50s} ... ")
    sys.stdout.flush()
    
    if test_url(url.strip()):
        print("OK")
        working.append((extinf, url))
    else:
        print("FAIL")

with open(OUTPUT, "w", encoding="utf-8") as f:
    for extinf, url in working:
        f.write(extinf)
        if url is not None:
            f.write(url)

print(f"\nDone. {len(working) - 1} working channels kept out of {len(entries) - 1}.")
