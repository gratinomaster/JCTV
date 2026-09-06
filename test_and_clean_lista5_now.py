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


def is_hls(data):
    low = data[:200000].lower()
    return any(m in low for m in (b"#extm3u", b"#ext-x-stream-inf", b"#ext-x-media-sequence",
                                  b"#ext-x-targetduration", b"#extinf"))


def test_stream(url, timeout=20, max_bytes=500000, attempts=2):
    """Return (ok, detail). HLS playlists must contain real entries/segments."""
    last_detail = "unknown"
    for _ in range(attempts):
        try:
            r = requests.get(url, headers=get_headers(), timeout=timeout,
                             stream=True, allow_redirects=True)
            if r.status_code != 200:
                last_detail = f"HTTP {r.status_code}"
                time.sleep(1)
                continue
            ct = r.headers.get("content-type", "").lower()
            data = r.content[:max_bytes]
            low = data[:250000].lower()

            is_hls_url = url.rstrip("/").lower().endswith(".m3u8") \
                or "/hls/" in url.lower() or ".m3u8?" in url.lower()

            if is_hls_url or b"#extm3u" in low or "mpegurl" in ct or "apple" in ct:
                if not is_hls(data):
                    last_detail = f"NOT HLS ({ct}, {len(data)}B)"
                    time.sleep(1)
                    continue
                n_seg = low.count(b"#extinf")
                n_var = low.count(b"#ext-x-stream-inf")
                return True, f"HLS ok extinf={n_seg} streaminf={n_var}"
            elif is_hls(data):
                n_seg = low.count(b"#extinf")
                n_var = low.count(b"#ext-x-stream-inf")
                return True, f"HLS ok extinf={n_seg} streaminf={n_var}"

            if b"\x00\x00\x00\x18ftyp" in data[:4096] or b"mvhd" in data[:4096] \
                    or b"moov" in data[:4096]:
                return True, f"MP4 ok ({ct}, {len(data)}B)"

            if ct.startswith(("video/", "audio/", "application/octet-stream")):
                if len(data) > 1024:
                    return True, f"media ok ({ct}, {len(data)}B)"
                last_detail = f"media small ({ct}, {len(data)}B)"
                time.sleep(1)
                continue

            if len(data) > 2048:
                return True, f"data ({ct}, {len(data)}B)"

            last_detail = f"no content ({ct}, {len(data)}B)"
            time.sleep(1)
        except requests.exceptions.Timeout:
            last_detail = "timeout"
            time.sleep(1)
        except Exception as e:
            last_detail = f"err {type(e).__name__}"
            time.sleep(1)
    return False, last_detail


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    out = path
    channels = parse_m3u(path)
    print(f"Total de entradas na lista: {len(channels)}")

    seen = set()
    uniq = []
    for info, url in channels:
        if url not in seen:
            seen.add(url)
            uniq.append((info, url))
    print(f"URLs únicas a testar: {len(uniq)}")
    print("-" * 60)

    results = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        fut_map = {ex.submit(test_stream, url): (info, url) for info, url in uniq}
        for i, fut in enumerate(as_completed(fut_map), 1):
            info, url = fut_map[fut]
            ok, detail = fut.result()
            name = info.split(",", 1)[-1].strip() if "," in info else url[:60]
            results[url] = (ok, detail)
            print(f"[{i}/{len(uniq)}] {'OK  ' if ok else 'FAIL'} | {name[:50]:50s} | {detail}")
            time.sleep(0.05)

    working = []
    dead = []
    seen_w = set()
    for info, url in channels:
        ok, detail = results[url]
        if ok:
            if url not in seen_w:
                seen_w.add(url)
                working.append((info, url))
        else:
            dead.append((info, url, detail))

    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n")
            f.write(url + "\n")

    print("-" * 60)
    print(f"Funcionando (mantidos, sem duplicatas): {len(working)}")
    print(f"Não funcionando (removidos): {len(dead)}")
    if dead:
        print("Removidos:")
        for info, url, detail in dead:
            name = info.split(",", 1)[-1].strip() if "," in info else ""
            print(f"  - {name[:60]} | {detail}")

    print(f"\nLista sobrescrita: {out}")


if __name__ == "__main__":
    main()
