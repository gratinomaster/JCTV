#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testa todos os canais do M3U, remove os que nao funcionam e sobrescreve a lista."""
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

MAX_ENTRIES = 3
PLAYLIST_LIMIT = 800_000
SEGMENT_LIMIT = 400_000


def get_headers(ref=""):
    h = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "close",
    }
    if ref:
        h["Referer"] = ref
    return h


def parse_m3u(path):
    entries = []
    info = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                info = line
            elif line.startswith("#"):
                continue
            else:
                if info is not None:
                    entries.append([info, line])
                info = None
    return entries


def fetch(url, ref, timeout, limit, method="GET", headers=None):
    h = headers or get_headers(ref)
    r = requests.request(method, url, headers=h, timeout=timeout, stream=True, allow_redirects=True)
    data = r.content[:limit]
    return r, data


def looks_hls(data):
    low = data[:300000].lower()
    return b"#extm3u" in low


def has_segments(text):
    lines = text.splitlines()
    seg = 0
    var = 0
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if s.startswith("#EXT-X-STREAM-INF") or s.startswith("#EXT-X-I-FRAME-STREAM-INF"):
            var += 1
        elif s.startswith("#EXT-X-KEY") or s.startswith("#EXT-X-MAP") or s.startswith("#"):
            continue
        else:
            seg += 1
    return seg, var


def check_hls(url, base_url, timeout, attempts):
    last = "hls?"
    for _ in range(attempts):
        try:
            r, data = fetch(url, "", timeout, PLAYLIST_LIMIT)
            if r.status_code != 200:
                last = "HTTP %s" % r.status_code
                time.sleep(1)
                continue
            if not looks_hls(data):
                last = "nao-HLS (%s, %dB)" % (r.headers.get("content-type", "?"), len(data))
                time.sleep(1)
                continue
            text = data.decode("utf-8", "replace")
            seg, var = has_segments(text)

            target = url
            if seg == 0 and var > 0:
                # master playlist -> pegar primeira variant e checar segmentos
                variants = []
                lines = text.splitlines()
                for i, l in enumerate(lines):
                    if l.strip().startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
                        nxt = lines[i + 1].strip()
                        if nxt and not nxt.startswith("#"):
                            variants.append(urljoin(base_url, nxt))
                if not variants:
                    last = "master sem variants"
                    time.sleep(1)
                    continue
                target = variants[0]

            child_ok, child_info = check_media(target, base_url, timeout)
            if child_ok:
                return True, "HLS %s" % child_info
            last = "HLS %s" % child_info
            time.sleep(1)
        except requests.exceptions.Timeout:
            last = "timeout"
            time.sleep(1)
        except Exception as e:
            last = "erro %s" % type(e).__name__
            time.sleep(1)
    return False, last


def check_media(url, base_url, timeout):
    try:
        r, data = fetch(url, "", timeout, SEGMENT_LIMIT, headers=get_headers(base_url))
        if r.status_code != 200:
            return False, "HTTP %s" % r.status_code
        if len(data) < 1024:
            return False, "vazio (%dB)" % len(data)
        head = data[:8192]
        ct = (r.headers.get("content-type") or "").lower()
        if b"ftyp" in head or b"moov" in head or b"moof" in head:
            return True, "media %dB ct=%s" % (len(data), ct or "?")
        if b"\x00\x00\x01" in head[:2048] or b"\x00\x00\x00\x01" in head[:2048]:
            return True, "ts %dB" % len(data)
        if looks_hls(data):
            text = data.decode("utf-8", "replace")
            seg, var = has_segments(text)
            if seg > 0:
                return True, "nested-playlist seg=%d" % seg
            return False, "playlist vazia"
        if len(data) > 2048:
            return True, "bytes %dB ct=%s" % (len(data), ct or "?")
        return False, "sem dados (%dB)" % len(data)
    except requests.exceptions.Timeout:
        return False, "timeout"
    except Exception as e:
        return False, "erro %s" % type(e).__name__


def test_stream(url, attempts=3, timeout=20):
    is_hls_hint = url.lower().split("?")[0].endswith(".m3u8") or ".m3u8" in url.lower()
    for _ in range(attempts):
        try:
            r = requests.head(url, headers=get_headers(), timeout=timeout, allow_redirects=True)
            if r.status_code == 405:
                r, _data = fetch(url, "", timeout, 1)
            if r.status_code >= 500:
                time.sleep(1)
                continue
            break
        except requests.exceptions.RequestException:
            time.sleep(1)
        except Exception:
            break

    if is_hls_hint:
        ok, detail = check_hls(url, url, timeout, 1)
        if ok:
            return True, detail
        ok2, detail2 = check_media(url, "", timeout)
        if ok2:
            return True, detail2
        return False, detail

    ok, detail = check_media(url, "", timeout)
    if ok:
        return True, detail
    ok2, detail2 = check_hls(url, url, timeout, 1)
    if ok2:
        return True, detail2
    return False, "%s | %s" % (detail, detail2)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    entries = parse_m3u(path)
    if not entries:
        print("Nenhuma entrada encontrada em %s" % path)
        return 1

    seen = set()
    uniq = []
    for info, url in entries:
        if url not in seen:
            seen.add(url)
            uniq.append((info, url))

    print("Entradas: %d | URLs unicas: %d" % (len(entries), len(uniq)))
    print("-" * 70)

    results = {}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fut_map = {ex.submit(test_stream, url): (info, url) for info, url in uniq}
        for i, fut in enumerate(as_completed(fut_map), 1):
            info, url = fut_map[fut]
            try:
                ok, detail = fut.result()
            except Exception as e:
                ok, detail = False, "excecao %s" % type(e).__name__
            results[url] = (ok, detail)
            name = info.split(",", 1)[-1].strip() if "," in info else url[:60]
            print("[%3d/%d] %s | %-45s | %s" % (i, len(uniq), "OK  " if ok else "FAIL", name[:45], detail))

    working = []
    dead = []
    seen_w = set()
    for info, url in entries:
        ok, detail = results.get(url, (False, "nao testado"))
        if ok:
            if url not in seen_w:
                seen_w.add(url)
                working.append((info, url))
        else:
            dead.append((info, url, detail))

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = "%s.backup_%s_pre_test" % (path, stamp)
    shutil.copy2(path, backup)
    print("-" * 70)
    print("Backup: %s" % backup)

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for info, url in working:
            f.write(info + "\n" + url + "\n")
    os.replace(tmp, path)

    with open("lista5.m3u.removidos.txt", "a", encoding="utf-8") as f:
        f.write("\n===== %s =====\n" % stamp)
        for info, url, detail in dead:
            f.write("FAIL | %s | %s\n" % (info.split(",", 1)[-1].strip(), detail))
            f.write("     %s\n" % url)

    print("Mantidos: %d | Removidos: %d" % (len(working), len(dead)))
    print("Log dos removidos: lista5.m3u.removidos.txt")
    if dead:
        print("\nRemovidos:")
        for info, url, detail in dead:
            print("  - %-45s %s" % (info.split(",", 1)[-1].strip()[:45], detail))
    print("\nLista sobrescrita: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
