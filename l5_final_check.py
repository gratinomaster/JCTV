"""Test every entry in lista5.m3u by decoding real video with ffmpeg.

An entry only counts as WORKING if ffmpeg can open the URL, find a video
stream, and decode frames from it. Anything else (dead URL, expired token,
404/403, HTML error page, audio-only rendition, decode stall) is reported as
not working.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

FFMPEG = os.environ.get(
    "FFMPEG_BIN",
    "/tmp/opencode/ffmpeg-master-latest-linux64-gpl/bin/ffmpeg")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
SRC = "lista5.m3u"
OUT_JSON = "l5_final_check.json"
SECONDS = 10
HARD_TIMEOUT = 60


def parse_m3u(path):
    entries = []
    cur = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if line.startswith("#EXTINF:"):
                cur = {"extinf": line, "extra": [], "url": None}
            elif line.startswith(("#EXTVLCOPT", "#EXTGRP", "#KODIPROP")):
                if cur is not None:
                    cur["extra"].append(line)
            elif line.strip() and not line.startswith("#"):
                if cur is not None:
                    cur["url"] = line.strip()
                    entries.append(cur)
                    cur = None
    return entries


def probe(url):
    cmd = [
        FFMPEG, "-hide_banner", "-nostdin", "-loglevel", "info",
        "-user_agent", UA, "-rw_timeout", "25000000",
        "-i", url, "-t", str(SECONDS), "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=HARD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, "timeout after %ss" % HARD_TIMEOUT, 0, False

    err = proc.stderr or ""
    has_video = bool(re.search(r"Stream #\d+:\d+.*: Video:", err))
    frames = re.findall(r"frame=\s*(\d+)", err)
    nframes = int(frames[-1]) if frames else 0

    if proc.returncode != 0:
        reason = "ffmpeg exit=%d" % proc.returncode
        for pat in (r"403 Forbidden", r"404 Not Found", r"401 Unauthorized",
                    r"Invalid data found", r"Server returned 4\d\d",
                    r"Server returned 5\d\d", r"Connection timed out",
                    r"Name or service not known", r"Resource temporarily"):
            m = re.search(pat, err)
            if m:
                reason = m.group(0)
                break
        return False, reason, nframes, has_video
    if not has_video:
        return False, "no video stream (audio-only rendition)", nframes, False
    if nframes == 0:
        return False, "decoded 0 frames", nframes, has_video
    return True, "ok", nframes, has_video


def main():
    entries = parse_m3u(SRC)
    urls = []
    seen = set()
    for e in entries:
        if e["url"] and e["url"] not in seen:
            seen.add(e["url"])
            urls.append(e["url"])

    print("%d entries / %d unique URLs" % (len(entries), len(urls)), flush=True)

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, (ok, reason, nframes, has_video) in zip(
                urls, pool.map(probe, urls)):
            results[url] = {"ok": ok, "reason": reason,
                            "frames": nframes, "video": has_video}
            print("%-7s %-42s %s" % ("OK" if ok else "FAIL",
                                     reason[:42], url[:96]), flush=True)

    with open(OUT_JSON, "w") as fh:
        json.dump(results, fh, indent=1)

    good = [u for u in urls if results[u]["ok"]]
    bad = [u for u in urls if not results[u]["ok"]]
    print("\n%d/%d unique URLs working" % (len(good), len(urls)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
