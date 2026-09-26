#!/usr/bin/env python3
"""
Final acceptance test for lista5.m3u.

Checks every explicit requirement against the file as it now stands on disk,
re-fetching the network so nothing is taken on trust:

  R1  #EXTM3U header present
  R2  every URL line is immediately preceded by its own #EXTINF (no orphans)
  R3  no duplicate URLs
  R4  no sub-rendition masquerading as a channel (variant / audio-only /
      DVR index / DRM / dead)
  R5  every stream is LIVE and decodable (video + audio), fetched now
  R6  ANTI-VIRUS: no malware / polyglot / exfil signature in manifest,
      init segment or media segments
  R7  tvg-id present, non-empty and unique
  R8  tvg-logo present, URL ends in .jpg, no imgur.com, live JPEG
  R9  url-tvg present and the EPG really answers 200 + real XMLTV
  R10 the tvg-id actually exists in the referenced EPG, and that EPG carries
      programmes for today, tomorrow AND the day after
  R11 group-title present
  R12 no leftover placeholder / dead tokens
"""
from __future__ import annotations

import gzip
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

import l5_check as V

UA = V.UA
PLAYLIST = "lista5.m3u"
EXTINF = re.compile(r'^#EXTINF:(?P<dur>-?[\d.]+)\s*(?P<attrs>.*?),(?P<name>.*)$')
ATTR = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')

results = []


def rec(rid, name, ok, detail=""):
    results.append((rid, name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {rid} {name}" + (f" -- {detail}" if detail else ""))


def parse():
    entries, pending, header = [], None, None
    with open(PLAYLIST, encoding="utf-8") as fh:
        for i, raw in enumerate(fh, 1):
            l = raw.strip()
            if not l:
                continue
            if l.startswith("#EXTM3U"):
                header = l
                continue
            if l.startswith("#EXTINF"):
                m = EXTINF.match(l)
                pending = (i, dict(ATTR.findall(m.group("attrs"))) if m else {},
                           m.group("name").strip() if m else l)
                continue
            if l.startswith("#"):
                continue
            if pending is None:
                entries.append((i, None, {}, None, l, True))
            else:
                entries.append((pending[0], pending[2], pending[1], pending[2], l, False))
                pending = None
    if pending is not None:
        entries.append((pending[0], pending[2], pending[1], pending[2], None, False))
    return header, entries


def fetch_xmltv(url, want_ids, today, tomorrow, day2):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read()
        ctype = r.headers.get("Content-Type", "")
    try:
        xml = gzip.decompress(raw).decode("utf-8", "replace")
        gz = True
    except OSError:
        xml = raw.decode("utf-8", "replace")
        gz = False
    if "<tv" not in xml[:4000]:
        raise ValueError("not XMLTV")
    ids = set(re.findall(r'<channel id="([^"]+)"', xml))
    per = {i: Counter() for i in want_ids}
    # attribute order differs between providers
    # (US2: <programme channel=".." start=".."> / epg-us: <programme start=".." channel="..">)
    for m in re.finditer(r'<programme\s+([^>]*?)/?>', xml):
        at = m.group(1)
        c = re.search(r'channel="([^"]+)"', at)
        s = re.search(r'start="(\d{8})', at)
        if c and s and c.group(1) in per and s.group(1) in (today, tomorrow, day2):
            per[c.group(1)][s.group(1)] += 1
    return {"gz": gz, "ctype": ctype, "ids": ids, "per": per,
            "bytes": len(raw)}


def main():
    now = datetime.now(timezone.utc)
    days = [now.strftime("%Y%m%d"),
            (now + timedelta(days=1)).strftime("%Y%m%d"),
            (now + timedelta(days=2)).strftime("%Y%m%d")]

    print(f"=== lista5.m3u acceptance test  ({now.isoformat()}) ===\n")
    header, entries = parse()

    # R1 -----------------------------------------------------------------
    rec("R1", "#EXTM3U header present", header is not None and header.startswith("#EXTM3U"),
        (header or "")[:70])

    # R2 -----------------------------------------------------------------
    orphans = [e for e in entries if e[5]]
    dangling = [e for e in entries if e[4] is None]
    bad = [e[0] for e in entries if e[5] or e[4] is None]
    rec("R2", "every URL has an #EXTINF directly above it",
        not orphans and not dangling, f"{len(entries)} entries, problems on lines {bad}")

    # R3 -----------------------------------------------------------------
    urls = [e[4] for e in entries if e[4]]
    dups = [u for u, c in Counter(urls).items() if c > 1]
    rec("R3", "no duplicate stream URLs", not dups, f"{len(urls)} urls, dups={len(dups)}")

    # R7 / R11 (cheap, do before network) --------------------------------
    ids = [e[2].get("tvg-id", "") for e in entries]
    rec("R7", "tvg-id present, non-empty and unique",
        all(ids) and len(set(ids)) == len(ids), f"ids={ids}")
    rec("R11", "group-title present on every entry",
        all(e[2].get("group-title") for e in entries),
        sorted({e[2].get("group-title") for e in entries}))

    # R8 -----------------------------------------------------------------
    for e in entries:
        ln, _, at, name, url, _ = e
        logo = at.get("tvg-logo", "")
        prob = []
        if not logo:
            prob.append("missing")
        else:
            if "imgur" in logo.lower():
                prob.append("IMGUR")
            if not logo.lower().endswith((".jpg", ".jpeg")):
                prob.append(f"not .jpg ({logo.rsplit('.', 1)[-1]})")
            if not V.ADVER.ok(logo) if hasattr(V, "ADVER") else False:
                pass
            try:
                rq = urllib.request.Request(logo, headers={"User-Agent": UA})
                with urllib.request.urlopen(rq, timeout=25) as r:
                    d = r.read(300_000)
                    ct = r.headers.get("Content-Type", "")
                if not (r.status == 200 and d[:3] == b"\xff\xd8\xff"):
                    prob.append("not a real JPEG")
                if "jpeg" not in ct.lower():
                    prob.append(f"content-type={ct}")
            except Exception as ex:
                prob.append(f"unreachable {type(ex).__name__}")
        rec("R8", f"tvg-logo .jpg, live, no imgur [{name}]", not prob, ";".join(prob))

    # R4 / R5 / R6 --------------------------------------------------------
    checked = {}
    for e in entries:
        ln, _, at, name, url, _ = e
        r = V.check(url, name)
        checked[name] = r
        sub = []
        if r["kind"] == "index" or r["variants"] == 0 and not r["checks"].get("L2_is_channel"):
            sub.append("sub-rendition/index")
        if not r["checks"].get("L3_no_drm", True):
            sub.append("DRM")
        if r.get("live") is False:
            sub.append("VOD/not live")
        if not r["checks"].get("L5_audio_present"):
            sub.append("no audio")
        if r["http"] != 200:
            sub.append(f"HTTP {r['http']}")
        rec("R4", f"is a real live channel, not a sub-rendition [{name}]", not sub,
            ";".join(sub) or f"{r['kind']}/{r['variants']} variants")
        rec("R5", f"live + decodable video and audio [{name}]",
            bool(r["checks"].get("L4_segments_decodable")) and
            bool(r["checks"].get("L5_audio_present")) and
            r["checks"].get("L6_live", True) is not False,
            f"{(r.get('video') or {}).get('res', '?')} {r['segs_ok']} segs ok")
        rec("R6", f"anti-virus scan clean [{name}]", not r["threats"],
            ";".join(r["threats"]) or "0 threats in manifest+init+segments")

    # R9 / R10 ------------------------------------------------------------
    epgs = sorted({at.get("url-tvg", "").split(",")[0].strip()
                   for _, _, at, _, _, _ in entries if at.get("url-tvg")})
    for epg in epgs:
        want = {at.get("tvg-id") for _, _, at, _, _, _ in entries
                if at.get("url-tvg", "").split(",")[0].strip() == epg}
        try:
            info = fetch_xmltv(epg, want, *days)
            rec("R9", f"EPG answers with real XMLTV [{epg.rsplit('/', 1)[-1]}]", True,
                f"{info['bytes']/1e6:.1f} MB gz={info['gz']} type={info['ctype']}")
            for cid in sorted(want):
                c = info["per"].get(cid, Counter())
                ok = cid in info["ids"] and all(c.get(d, 0) > 0 for d in days)
                rec("R10", f"tvg-id {cid} in EPG w/ today+tomorrow+day+2", ok,
                    f"declared={'yes' if cid in info['ids'] else 'NO'} "
                    f"today={c.get(days[0], 0)} tomorrow={c.get(days[1], 0)} "
                    f"day+2={c.get(days[2], 0)}")
        except Exception as ex:
            rec("R9", f"EPG answers with real XMLTV [{epg.rsplit('/', 1)[-1]}]",
                False, f"{type(ex).__name__}: {str(ex)[:70]}")
            for cid in sorted(want):
                rec("R10", f"tvg-id {cid} in EPG w/ today+tomorrow+day+2", False, "EPG down")

    # R12 -----------------------------------------------------------------
    txt = open(PLAYLIST, encoding="utf-8").read()
    junk = [p for p in ("imgur", "TODO", "FIXME", "example.com", "localhost",
                        "127.0.0.1", "0.0.0.0", "your-epg", "PLACEHOLDER")
            if p.lower() in txt.lower()]
    rec("R12", "no imgur / placeholders / dead tokens", not junk, f"hits={junk}")

    npass = sum(1 for _, _, ok, _ in results if ok)
    print(f"\n=== {npass}/{len(results)} checks passed "
          f"({sum(1 for _,_,ok,_ in results if not ok)} failed) ===")
    if npass != len(results):
        print("\nfailures:")
        for rid, n, ok, d in results:
            if not ok:
                print(f"  {rid} {n}: {d}")
    return 0 if npass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
