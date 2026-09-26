#!/usr/bin/env python3
"""
Verify XMLTV EPG sources: which of our tvg-ids exist, and do they carry
programmes for today, tomorrow and the day after?

Streams the .gz so the 533 MB epg-us never lands on disk.
"""
import gzip
import io
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

EPGS = {
    "epg-us":  "https://iptv-epg.org/files/epg-us.xml.gz",
    "US2":     "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
}

# channel we care about -> regexes matched against channel id and display-name
WANT = {
    "ABC News Live":      [r"^ABC\.?News\.?Live", r"^ABCNewsLive"],
    "CBS News 24/7":      [r"^CBS\.?News\.?National", r"^CBSNews24", r"^CBSNews\.us$",
                           r"^CBSNews24/7"],
    "CBS News":           [r"^CBS\.?News\.", r"^CBSNews\."],
    "Fox News":           [r"^Fox\.?News\.?Channel", r"^FoxNewsChannel"],
    "MSNBC":              [r"^MSNBC"],
    "ABC News (alt)":     [r"^ABCEast_", r"^ABCWABC", r"^ABCKABC"],
}


def stream_lines(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    return gzip.decompress(raw).decode("utf-8", "replace")


def verify(key, url, today, tomorrow, day2):
    print(f"\n{'=' * 78}\n{key}  {url}")
    try:
        xml = stream_lines(url)
    except Exception as e:
        print(f"  FETCH FAILED: {type(e).__name__}: {e}")
        return None
    print(f"  decompressed: {len(xml) / 1e6:.1f} MB")

    # ---- channels -------------------------------------------------------
    chans = {}
    for m in re.finditer(
            r'<channel id="([^"]+)"\s*>\s*(?:.*?)</channel>', xml, re.S):
        cid = m.group(1)
        name = ""
        dn = re.search(r"<display-name[^>]*>(.*?)</display-name>", m.group(0), re.S)
        if dn:
            name = dn.group(1).strip()
        chans[cid] = name
    print(f"  channels: {len(chans)}")

    # ---- programmes per channel, and date histogram ---------------------
    progs = Counter()
    dates = Counter()
    perchan = defaultdict(Counter)
    for m in re.finditer(r'<programme\s+([^>]*)>', xml):
        at = m.group(1)
        c = re.search(r'channel="([^"]+)"', at)
        s = re.search(r'start="(\d{8})', at)
        if c:
            cid = c.group(1)
            progs[cid] += 1
            if s and s.group(1) in (today, tomorrow, day2):
                perchan[cid][s.group(1)] += 1
        if s:
            dates[s.group(1)] += 1
    print(f"  programmes: {sum(progs.values())}")
    top = ", ".join(f"{d}:{n}" for d, n in dates.most_common(6))
    print(f"  top dates : {top}")
    for label, d in (("today", today), ("tomorrow", tomorrow), ("day+2", day2)):
        print(f"  {label:<9} {d}: {dates.get(d, 0):>7} programmes")

    # ---- match our channels --------------------------------------------
    print(f"\n  {'channel':<20} {'tvg-id':<34} {'total':>6} "
          f"{'today':>6} {'tomo':>6} {'+2':>6}  display-name")
    print("  " + "-" * 108)
    result = {}
    for label, pats in WANT.items():
        rows = []
        for cid, name in chans.items():
            for p in pats:
                if re.search(p, cid, re.I) or re.search(p, name, re.I):
                    pc = perchan.get(cid, Counter())
                    rows.append((cid, name, progs.get(cid, 0),
                                 pc.get(today, 0), pc.get(tomorrow, 0),
                                 pc.get(day2, 0)))
                    break
        rows.sort(key=lambda r: (-r[5], -r[3], -r[4], -r[2]))
        for cid, name, tot, d0, d1, d2 in rows[:4]:
            ok = "OK " if (d0 and d1 and d2) else "   "
            print(f"  {ok}{label:<20} {cid:<34} {tot:>6} {d0:>6} {d1:>6} {d2:>6}  {name[:34]}")
        result[label] = [dict(tvg_id=c, name=n, total=t, today=a, tom=b, d2=c2)
                         for c, n, t, a, b, c2 in rows]
    return {"key": key, "url": url, "channels": len(chans),
            "programmes": sum(progs.values()),
            "dates": dict(dates.most_common(20)),
            "matches": result,
            "ids": sorted(chans)}


def main():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y%m%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y%m%d")
    day2 = (now + timedelta(days=2)).strftime("%Y%m%d")
    print(f"UTC today={today}  tomorrow={tomorrow}  day+2={day2}")
    out = {}
    only = sys.argv[1:] or list(EPGS)
    for k in only:
        out[k] = verify(k, EPGS[k], today, tomorrow, day2)
    with open("l5_epg.json", "w") as fh:
        json.dump(out, fh, indent=2)
    print("\n-> l5_epg.json")


if __name__ == "__main__":
    main()
