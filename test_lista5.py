#!/usr/bin/env python3
"""Test every stream in lista5.m3u, drop the dead ones, rewrite the file."""

import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LISTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lista5.m3u")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT = 15
WORKERS = 5
RETRIES = 3
TS_MAGIC = b"\x47"
# valid ISO-BMFF top-level box types seen at the head of a media segment
MP4_BOXES = (b"ftyp", b"styp", b"moof", b"sidx", b"free", b"skip", b"emsg", b"mdat")
STREAM_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "application/octet-stream",
}


def fetch(url, limit=None, retries=RETRIES):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "*/*"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read() if limit is None else r.read(limit)
                return r.status, r.headers.get("Content-Type", ""), body
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 404, 408, 425, 429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            return exc.code, "", b""
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 * (attempt + 1))
    raise last if last else RuntimeError("fetch failed")


def absolute(uri, base):
    uri, base = uri.strip(), base.strip()
    base_query = base.split("?", 1)[1] if "?" in base else ""
    if uri.startswith(("http://", "https://")):
        resolved = [uri]
    else:
        resolved = [urllib.parse.urljoin(base, uri)]
    # Akamai-style tokens (hdnea=exp=...~hmac=...) live in the base query and
    # must be forwarded to the variant/segment request.
    if base_query and "?" not in uri:
        resolved.append(resolved[0] + "?" + base_query)
    return resolved


def fetch_any(urls):
    """Try each candidate URL; return ((status, ctype, body), url_used)."""
    result = (0, "", b"")
    for url in urls:
        try:
            result = fetch(url)
        except Exception as exc:  # noqa: BLE001
            result = (type(exc).__name__, "", b"")
        if isinstance(result[0], int) and result[0] < 400 and result[2]:
            return result, url
    return result, (urls[0] if urls else "")


def bad_tags(body):
    text = body.decode("utf-8", "ignore")
    return "#EXT-X-ERROR" in text


def check_media(text, base):
    """Validate a media playlist; return (ok, reason)."""
    if "#EXT-X-ENDLIST" in text or "#EXT-X-PLAYLIST-TYPE:VOD" in text:
        return False, "VOD not live"
    media = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not media:
        return False, "no segments"

    # newest segments first: a live edge proves the stream is actually running
    last_reason = "segments unreachable"
    for seg in media[::-1][:2]:
        (scode, sctype, seg_body), _ = fetch_any(absolute(seg, base))
        if not isinstance(scode, int):
            last_reason = "segment %s" % scode
            continue
        if scode >= 400 or not seg_body:
            last_reason = "segment HTTP %d" % scode
            continue
        if len(seg_body) < 200:
            last_reason = "segment too small"
            continue
        if seg_body.lstrip()[:1] == b"<":
            return False, "segment is HTML"
        if seg_body[:1] == TS_MAGIC:
            return True, "ok (mpegts)"
        if len(seg_body) >= 8 and seg_body[4:8] in MP4_BOXES:
            boxsize = int.from_bytes(seg_body[:4], "big")
            if 8 <= boxsize <= len(seg_body) + 4096:
                return True, "ok (fmp4 %s)" % seg_body[4:8].decode()
        if sctype.split(";")[0] in ("application/octet-stream", "video/mp2t"):
            return True, "ok (octet-stream)"
        last_reason = "segment not media"
    return False, last_reason


def check(url):
    """Return (ok, reason). True only for a live playlist yielding real segments."""
    (code, ctype, body), base = fetch_any([url])

    if not isinstance(code, int):
        return False, str(code)
    if code >= 400:
        return False, "HTTP %d" % code
    if not body:
        return False, "empty body"

    head = body[:400].lstrip()
    if not (head.startswith(b"#EXTM3U") or b"#EXTM3U" in body[:200]):
        if ctype.split(";")[0] not in STREAM_TYPES:
            return False, "not a playlist"
    if bad_tags(body):
        return False, "#EXT-X-ERROR"

    text = body.decode("utf-8", "ignore")
    if "#EXT-X-STREAM-INF" not in text:
        return check_media(text, base)

    variants = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not variants:
        return False, "master with no variant"

    # any working variant is enough; only drop when all of them fail
    reason = "master with no variant"
    for variant in variants:
        (vcode, _vtype, vbody), vbase = fetch_any(absolute(variant, base))
        if not isinstance(vcode, int):
            reason = "variant %s" % vcode
            continue
        if vcode >= 400 or not vbody:
            reason = "variant HTTP %d" % vcode
            continue
        if bad_tags(vbody):
            reason = "variant #EXT-X-ERROR"
            continue
        ok, reason = check_media(vbody.decode("utf-8", "ignore"), vbase)
        if ok:
            return True, reason
    return False, reason


def parse(path):
    with open(path, encoding="utf-8", errors="ignore") as fh:
        lines = fh.read().splitlines()

    header = [ln for ln in lines if ln.startswith("#EXTM3U")]
    entries = []
    pending = None
    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith("#EXTINF"):
            pending = line
            continue
        if line.startswith("#"):
            continue
        if not line.strip():
            continue
        if pending is None:
            continue
        entries.append((pending, line.strip()))
        pending = None
    return header, entries


def name_of(extinf):
    m = re.search(r',([^,]*)$', extinf)
    return m.group(1).strip() if m else ""


def main():
    header, entries = parse(LISTA)
    total = len(entries)
    print("Testing %d streams from %s" % (total, os.path.basename(LISTA)))
    print("-" * 70)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda e: check(e[1]), entries))

    keep, drop = [], []
    for (extinf, url), (ok, reason) in zip(entries, results):
        name = name_of(extinf)
        if ok:
            keep.append((extinf, url))
            print("[KEEP] %-52s %s" % (name[:52], reason))
        else:
            drop.append((extinf, url, reason))
            print("[DROP] %-52s %s" % (name[:52], reason))

    print("-" * 70)
    print("Total: %d | Keep: %d | Drop: %d" % (total, len(keep), len(drop)))

    if "--write" in sys.argv:
        with open(LISTA, "w", encoding="utf-8") as fh:
            for line in header or ["#EXTM3U"]:
                fh.write(line + "\n")
            for extinf, url in keep:
                fh.write(extinf + "\n" + url + "\n")
        print("Rewrote %s with %d working streams." % (LISTA, len(keep)))
    else:
        print("Dry run. Re-run with --write to apply.")


if __name__ == "__main__":
    main()
