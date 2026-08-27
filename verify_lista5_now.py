#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def parse_m3u(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]
    channels = []
    info = None
    for line in lines:
        line = line.strip()
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


def test_stream(url, timeout=12, max_bytes=400000):
    """Return (ok, detail). Check for real playable stream content."""
    try:
        r = requests.get(url, headers=get_headers(), timeout=timeout, stream=True, allow_redirects=True)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"

        ct = r.headers.get("content-type", "").lower()
        # .content auto-decompresses gzip/br
        data = r.content[:max_bytes]

        low = data[:250000].lower()

        is_hls_url = url.rstrip("/").lower().endswith(".m3u8") or "/hls/" in url.lower() \
            or ".m3u8?" in url.lower()

        if b"#extm3u" in low or is_hls_url:
            # HLS playlist. Must contain real entries.
            markers = (b"#extinf", b"#ext-x-stream-inf", b"#ext-x-media-sequence",
                       b"#ext-x-targetduration", b"#ext-x-media:")
            if any(m in low for m in markers):
                n_seg = low.count(b"#extinf")
                n_var = low.count(b"#ext-x-stream-inf")
                return True, f"HLS ok ({ct}, extinf={n_seg}, streaminf={n_var})"
            else:
                return False, f"HLS no entries ({ct}, {len(data)}B)"

        if b"\x00\x00\x00\x18ftyp" in data[:4096] or b"mvhd" in data[:4096] or b"moov" in data[:4096]:
            # ftyp/mp4 container
            return True, f"MP4 ok ({ct}, {len(data)}B)"

        if ct.startswith("video/") or ct.startswith("audio/") or ct.startswith("application/octet-stream"):
            if len(data) > 1024:
                return True, f"media ok ({ct}, {len(data)}B)"
            return False, f"media small ({ct}, {len(data)}B)"

        if len(data) > 2048:
            return True, f"data ({ct}, {len(data)}B)"

        return False, f"no content ({ct}, {len(data)}B)"
    except requests.exceptions.Timeout:
        return False, "timeout"
    except Exception as e:
        return False, f"err {type(e).__name__}"


def main():
    path = "lista5.m3u" if len(sys.argv) < 2 else sys.argv[1]
    channels = parse_m3u(path)
    print(f"Total de canais/URLs: {len(channels)}")

    working = []
    dead = []
    for i, (info, url) in enumerate(channels, 1):
        name = info.split(",", 1)[-1].strip() if "," in info else f"Canal {i}"
        ok, detail = test_stream(url)
        print(f"[{i}/{len(channels)}] {'OK ' if ok else 'FAIL'} | {name[:55]} | {detail}")
        if ok:
            working.append((info, url))
        else:
            dead.append((info, url, detail))
        time.sleep(0.2)

    out = "lista5.m3u"
    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n")
            f.write(url + "\n")

    print(f"\nFuncionando: {len(working)}")
    print(f"Não funcionando: {len(dead)}")
    if dead:
        print("Removidos:")
        for info, url, detail in dead:
            name = info.split(",", 1)[-1].strip() if "," in info else ""
            print(f"  - {name} | {detail}")


if __name__ == "__main__":
    main()
