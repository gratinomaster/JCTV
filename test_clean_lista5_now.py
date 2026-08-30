#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Referer": "https://www.google.com/",
}


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


def resolve_url(uri, base):
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    base_path, _, base_query = base.partition("?")
    dir_part = base_path.rsplit("/", 1)[0] + "/"
    url = dir_part + uri
    if base_query and "?" not in url:
        url += "?" + base_query
    return url


def get(url, timeout=12, max_bytes=200000):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        data = r.content[:max_bytes]
        return r.status_code, data, r.headers.get("content-type", "").lower()
    except requests.exceptions.Timeout:
        return None, b"", "timeout"
    except Exception as e:
        return None, b"", f"err {type(e).__name__}"


def is_hls(data):
    low = data[:60000].lower()
    return any(m in low for m in (b"#extm3u", b"#ext-x-stream-inf", b"#ext-x-media-sequence",
                                  b"#ext-x-targetduration"))


def test_stream(url, attempts=2):
    """Return (ok, detail). Verify HLS playlist -> variant -> segment playable."""
    last_detail = "unknown"
    for _ in range(attempts):
        code, data, ct = get(url)
        if code is None:
            last_detail = f"req {ct}"
            time.sleep(1)
            continue
        if code != 200:
            last_detail = f"HTTP {code}"
            time.sleep(1)
            continue
        if not is_hls(data):
            if b"\x00\x00\x00\x18ftyp" in data[:4096] or b"mvhd" in data[:4096] or b"moov" in data[:4096]:
                return True, f"MP4 ok ({len(data)}B)"
            if ct.startswith(("video/", "audio/", "application/octet-stream")) and len(data) > 1024:
                return True, f"media ok ({ct}, {len(data)}B)"
            last_detail = f"not HLS ({ct}, {len(data)}B)"
            time.sleep(1)
            continue
        return True, f"HLS ok"
    return False, last_detail


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    channels = parse_m3u(path)
    print(f"Total de canais/URLs: {len(channels)}")

    working = []
    dead = []
    for i, (info, url) in enumerate(channels, 1):
        name = info.split(",", 1)[-1].strip() if "," in info else f"Canal {i}"
        ok, detail = test_stream(url)
        print(f"[{i}/{len(channels)}] {'OK ' if ok else 'FAIL'} | {name[:50]} | {detail}")
        if ok:
            working.append((info, url))
        else:
            dead.append((info, url, detail))
        time.sleep(0.2)

    out = path
    with open(out, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n")
            f.write(url + "\n")

    print(f"\nFuncionando: {len(working)}")
    print(f"Não funcionando: {len(dead)}")
    if dead:
        print("\nRemovidos:")
        for info, url, detail in dead:
            name = info.split(",", 1)[-1].strip() if "," in info else ""
            print(f"  - {name} | {detail}")


if __name__ == "__main__":
    main()
