#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def parse_m3u(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    channels = []
    info = None
    for line in lines:
        line = line.rstrip()
        if line.startswith("#EXTINF:"):
            info = line
        elif line.startswith("#") or not line:
            continue
        else:
            if info is not None:
                channels.append((info, line))
            info = None
    return channels


def get_headers():
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": "https://www.google.com/",
    }


def test_stream(url, timeout=15, max_bytes=500000):
    try:
        r = requests.get(url, headers=get_headers(), timeout=timeout, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        ct = r.headers.get("content-type", "").lower()
        data = r.content[:max_bytes]
        low = data[:250000].lower()

        is_hls_url = url.rstrip("/").lower().endswith(".m3u8") or "/hls/" in url.lower() or ".m3u8?" in url.lower()

        if b"#extm3u" in low or is_hls_url:
            markers = (b"#extinf", b"#ext-x-stream-inf", b"#ext-x-media-sequence",
                       b"#ext-x-targetduration", b"#ext-x-media:")
            if any(m in low for m in markers):
                return True, "HLS ok"
            else:
                return False, "HLS no entries"

        if any(x in data[:4096] for x in (b"\x00\x00\x00\x18ftyp", b"mvhd", b"moov")):
            return True, "MP4 ok"

        if ct.startswith(("video/", "audio/", "application/octet-stream")):
            if len(data) > 1024:
                return True, "media ok"
            return False, "media small"

        if len(data) > 2048:
            return True, "data ok"

        return False, "no content"
    except requests.exceptions.Timeout:
        return False, "timeout"
    except Exception as e:
        return False, f"err {type(e).__name__}"


def main():
    path = "lista5.m3u" if len(sys.argv) < 2 else sys.argv[1]
    out = path
    channels = parse_m3u(path)
    print(f"Total de URLs/canais: {len(channels)}")

    # Deduplicate by URL
    seen = set()
    uniq = []
    for info, url in channels:
        if url not in seen:
            seen.add(url)
            uniq.append((info, url))
    print(f"URLs únicas: {len(uniq)}")

    results = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        fut_map = {ex.submit(test_stream, url): (info, url) for info, url in uniq}
        for i, fut in enumerate(as_completed(fut_map), 1):
            info, url = fut_map[fut]
            ok, detail = fut.result()
            name = info.split(",", 1)[-1].strip() if "," in info else url[:60]
            results[url] = (ok, detail)
            print(f"[{i}/{len(uniq)}] {'OK ' if ok else 'FAIL'} | {name[:50]} | {detail}")
            time.sleep(0.05)

    working = []
    dead = []
    for info, url in channels:
        ok, detail = results[url]
        if ok:
            working.append((info, url))
        else:
            dead.append((info, url, detail))

    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n")
            f.write(url + "\n")

    print(f"\nFuncionando: {len(working)}")
    print(f"Não funcionando: {len(dead)}")
    names_removed = {}
    for info, url, detail in dead:
        name = info.split(",", 1)[-1].strip() if "," in info else url[:60]
        names_removed.setdefault(name, []).append(detail)
    for name, details in names_removed.items():
        print(f"  - REMOVIDO: {name} | {details[0]}")


if __name__ == "__main__":
    main()
