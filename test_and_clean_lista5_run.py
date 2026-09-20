#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, parse_qsl, urlencode

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

TIMEOUT = 15
MAX_BYTES = 600000
ATTEMPTS = 3
WORKERS = 1


def parse_m3u(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = [l.rstrip("\r\n") for l in f]
    channels = []
    info = None
    for line in lines:
        if not line.strip():
            continue
        if line.startswith("#EXTINF:"):
            info = line
        elif line.startswith("#") or line.startswith("http://") is False and "://" not in line:
            continue
        else:
            if info is not None and ("://" in line):
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


def resolve_uri(base, uri):
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    return urljoin(base, uri)


def fetch(url, timeout=TIMEOUT):
    r = requests.get(url, headers=get_headers(), timeout=timeout,
                     stream=True, allow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError("HTTP %d" % r.status_code)
    return r.content[:MAX_BYTES]


def test_stream(url, timeout=TIMEOUT, attempts=ATTEMPTS):
    last_detail = "unknown"
    for _ in range(attempts):
        try:
            content = fetch(url, timeout)
            low = content[:250000].lower()

            if b"#ext-x-stream-inf" in low and b"#extinf" not in low:
                variant = None
                for line in content[:100000].splitlines():
                    line = line.decode("utf-8", "ignore").strip()
                    if line and not line.startswith("#"):
                        variant = line
                        break
                if not variant:
                    last_detail = "master no variant"
                    time.sleep(1)
                    continue
                variant_url = resolve_uri(url, variant)
                content = fetch(variant_url, timeout)
                low = content[:250000].lower()

            if b"#extm3u" in low:
                n_seg = low.count(b"#extinf")
                n_var = low.count(b"#ext-x-stream-inf")
                if n_seg > 0 or n_var > 0:
                    return True, "HLS ok extinf=%d streaminf=%d" % (n_seg, n_var)
                last_detail = "HLS empty playlist"
                time.sleep(1)
                continue

            if b"\x00\x00\x00\x18ftyp" in content[:4096] or b"mvhd" in content[:4096] \
                    or b"moov" in content[:4096] or b"\x1a\x45\xdf\xa3" in content[:4096]:
                return True, "media container ok (%dB)" % len(content)

            if len(content) > 2048:
                return True, "data ok (%dB)" % len(content)

            last_detail = "no content (%dB)" % len(content)
            time.sleep(1)
        except requests.exceptions.Timeout:
            last_detail = "timeout"
            time.sleep(1)
        except RuntimeError as e:
            last_detail = str(e)
            time.sleep(1)
        except Exception as e:
            last_detail = "err %s" % type(e).__name__
            time.sleep(1)
    return False, last_detail


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    out = path
    channels = parse_m3u(path)
    print("Total de entradas na lista: %d" % len(channels))

    seen = set()
    uniq = []
    for info, url in channels:
        if url not in seen:
            seen.add(url)
            uniq.append((info, url))
    print("URLs unicas a testar: %d" % len(uniq))
    print("-" * 70)

    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        fut_map = {ex.submit(test_stream, url): (info, url) for info, url in uniq}
        for i, fut in enumerate(as_completed(fut_map), 1):
            info, url = fut_map[fut]
            ok, detail = fut.result()
            name = info.split(",", 1)[-1].strip() if "," in info else url[:60]
            results[url] = (ok, detail)
            print("[%d/%d] %s | %-45s | %s" % (i, len(uniq), "OK  " if ok else "FAIL",
                                               name[:45], detail))
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

    print("-" * 70)
    print("Funcionando (mantidos, sem duplicatas): %d" % len(working))
    print("Nao funcionando (removidos): %d" % len(dead))
    if dead:
        print("Removidos:")
        for info, url, detail in dead:
            name = info.split(",", 1)[-1].strip() if "," in info else ""
            print("  - %s | %s" % (name[:60], detail))
    print("")
    print("Lista sobrescrita: %s" % out)


if __name__ == "__main__":
    main()