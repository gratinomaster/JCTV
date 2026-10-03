#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testa todos os canais de uma lista M3U, remove os que nao funcionam e sobrescreve a lista."""
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

TIMEOUT = 15
ATTEMPTS = 3
WORKERS = 5
MAX_HEAD = 400000
UA_HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}


def parse_m3u(path):
    entries = []
    info = None
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                info = line
            elif line.startswith("#"):
                continue
            elif "://" in line:
                if info is not None:
                    entries.append((info, line))
                info = None
    return entries


def get(url, limit=MAX_HEAD, timeout=TIMEOUT, session=None):
    getter = session.get if session is not None else requests.get
    r = getter(url, headers=UA_HEADERS, timeout=timeout, stream=True,
               allow_redirects=True)
    if r.status_code != 200:
        raise RuntimeError("HTTP %d" % r.status_code)
    buf = bytearray()
    for chunk in r.iter_content(65536):
        buf += chunk
        if len(buf) >= limit:
            break
    r.close()
    return bytes(buf)


def abs_url(base, ref):
    ref = ref.strip()
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    return urljoin(base, ref)


def looks_media(data):
    if len(data) < 512:
        return False
    head = data[:4096]
    if b"ftyp" in head[:64] or b"moov" in head or b"moof" in head:
        return True
    if b"\x1a\x45\xdf\xa3" in head:
        return True
    return data[0] == 0x47 and (b"\x47" in data[:188])


def pick(lines, marker):
    for i, ln in enumerate(lines):
        if marker in ln:
            for nxt in lines[i + 1:]:
                if nxt and not nxt.startswith("#"):
                    return nxt
    return None


def check_once(url):
    sess = requests.Session()
    body = get(url, session=sess)
    head = body[:200000]
    if b"#EXTM3U" not in head:
        if looks_media(body):
            return True, "media direto (%dB)" % len(body)
        raise RuntimeError("sem manifesto HLS (%dB)" % len(body))

    lines = [l.decode("utf-8", "ignore").strip() for l in body.splitlines()]
    lines = [l for l in lines if l]

    if any("#EXT-X-STREAM-INF" in l for l in lines):
        ref = pick(lines, "#EXT-X-STREAM-INF")
        if not ref:
            raise RuntimeError("master sem variante")
        variant_url = abs_url(url, ref)
        vbody = get(variant_url, session=sess)
        if b"#EXTM3U" not in vbody[:200000]:
            raise RuntimeError("variante invalida")
        vlines = [l.decode("utf-8", "ignore").strip() for l in vbody.splitlines()]
        seg = pick([l for l in vlines if l], "#EXTINF")
        if not seg:
            raise RuntimeError("variante sem segmentos")
        seg_url = abs_url(variant_url, seg)
        sdata = get(seg_url, limit=262144, session=sess)
        if not looks_media(sdata):
            raise RuntimeError("segmento sem midia (%dB)" % len(sdata))
        return True, "HLS ok seg=%dB" % len(sdata)

    seg = pick(lines, "#EXTINF")
    if not seg:
        raise RuntimeError("playlist sem segmentos")
    seg_url = abs_url(url, seg)
    sdata = get(seg_url, limit=262144, session=sess)
    if not looks_media(sdata):
        raise RuntimeError("segmento sem midia (%dB)" % len(sdata))
    return True, "HLS ok seg=%dB" % len(sdata)


def test_stream(url, attempts=ATTEMPTS):
    detail = "desconhecido"
    for n in range(attempts):
        try:
            return check_once(url)
        except requests.exceptions.Timeout:
            detail = "timeout"
        except requests.exceptions.ConnectionError:
            detail = "conexao recusada"
        except Exception as e:
            detail = str(e)
        if n < attempts - 1:
            time.sleep(1.5)
    return False, detail


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    entries = parse_m3u(path)
    print("Entradas na lista: %d" % len(entries))

    uniq = []
    seen = set()
    for info, url in entries:
        if url not in seen:
            seen.add(url)
            uniq.append((info, url))
    print("URLs unicas a testar: %d" % len(uniq))
    print("-" * 78)

    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(test_stream, url): (info, url) for info, url in uniq}
        for i, fut in enumerate(as_completed(futs), 1):
            info, url = futs[fut]
            ok, detail = fut.result()
            results[url] = (ok, detail)
            name = info.split(",", 1)[-1].strip() if "," in info else url[:50]
            print("[%2d/%2d] %s  %-46s %s" % (i, len(uniq), "OK  " if ok else "FAIL",
                                               name[:46], detail))

    working, dead = [], []
    seen_w = set()
    for info, url in entries:
        ok, detail = results[url]
        if ok:
            if url not in seen_w:
                seen_w.add(url)
                working.append((info, url))
        else:
            dead.append((info, url, detail))

    with open(path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n" + url + "\n")

    print("-" * 78)
    print("Canais functioning (mantidos, sem URLs duplicadas): %d" % len(working))
    print("Nao funcionando (removidos): %d" % len(dead))
    for info, url, detail in dead:
        name = info.split(",", 1)[-1].strip() if "," in info else ""
        print("  - %s | %s" % (name[:70], detail))
    print("Lista sobrescrita: %s" % path)


if __name__ == "__main__":
    main()