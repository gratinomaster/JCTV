#!/usr/bin/env python3
"""Test every channel in lista5.m3u, drop the dead ones, rewrite the file."""
from __future__ import annotations

import re
import shutil
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import l5_check as V

PLAYLIST = "lista5.m3u"
EXTINF = re.compile(r'^#EXTINF:(?P<dur>-?[\d.]+)\s*(?P<attrs>.*?),(?P<name>.*)$')
ATTR = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')


def parse(path):
    entries, pending, header = [], None, None
    with open(path, encoding="utf-8") as fh:
        for i, raw in enumerate(fh, 1):
            l = raw.strip()
            if not l:
                continue
            if l.startswith("#EXTM3U"):
                header = l
                continue
            if l.startswith("#EXTINF"):
                m = EXTINF.match(l)
                pending = (l,
                           dict(ATTR.findall(m.group("attrs"))) if m else {},
                           m.group("name").strip() if m else l)
                continue
            if l.startswith("#"):
                continue
            if pending is None:
                entries.append({"line": i, "extinf": None, "attrs": {},
                                "name": "", "url": l})
            else:
                entries.append({"line": i, "extinf": pending[0],
                                "attrs": pending[1], "name": pending[2],
                                "url": l})
                pending = None
    if pending is not None:
        entries.append({"line": pending and entries[-1]["line"] if entries else 0,
                        "extinf": pending[0], "attrs": pending[1],
                        "name": pending[2], "url": None})
    return header or "#EXTM3U", entries


def verdict(r):
    """Returns (ok, reasons). ok = playable live channel right now."""
    if r["http"] != 200:
        return False, [f"HTTP {r['http']}"]
    if not r["checks"].get("L1_http_200_hls"):
        return False, ["not an HLS manifest"]
    if r["variants"] == 0 and not r["checks"].get("L2_is_channel"):
        return False, ["not a channel (no variants, no segments)"]
    if r["threats"]:
        return False, list(r["threats"])
    if r["checks"].get("L3_no_drm") is False:
        return False, ["DRM protected (needs licence)"]
    if r.get("live") is False:
        return False, ["VOD, not live"]
    if not r["checks"].get("L4_segments_decodable"):
        return False, ["no decodable media segment"]
    if not r["checks"].get("L5_audio_present"):
        return False, ["no audio track"]
    return True, [f"{r['variants']} variants, {r['segs_ok']} segs, audio ok"]


def main():
    header, entries = parse(PLAYLIST)
    uniq, seen = [], {}
    for e in entries:
        if not e["url"]:
            continue
        seen.setdefault(e["url"], len(seen))
        uniq.append(e)

    print(f"=== teste de {len(entries)} entradas / {len(seen)} URLs unicas  "
          f"({datetime.utcnow().isoformat()}Z) ===\n")

    results = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {}
        for u, i in seen.items():
            name = next(e["name"] for e in uniq if e["url"] == u)
            futs[ex.submit(V.check, u, name)] = u
        for f in futs:
            u = futs[f]
            try:
                results[u] = f.result()
            except Exception as e:
                results[u] = {"http": None, "variants": 0, "threats": [],
                              "checks": {}, "fail": [f"{type(e).__name__}"],
                              "segs_ok": 0, "live": None}

    order = sorted(seen, key=seen.get)
    keep, drop = [], []
    for u in order:
        r = results[u]
        ok, why = verdict(r)
        n = sum(1 for e in uniq if e["url"] == u)
        name = next(e["name"] for e in uniq if e["url"] == u)
        print(f"[{'OK  ' if ok else 'FAIL'}] x{n:<2} {r.get('host', '?')[:34]:<34} {why[0][:60]}")
        if ok:
            keep.append(u)
        else:
            drop.append((u, name, n, "; ".join(why)))

    print(f"\nURLs unicas funcionais: {len(keep)}  |  removidas: {len(drop)}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(PLAYLIST, f"{PLAYLIST}.backup_{ts}_pre_test")

    with open(PLAYLIST, "w", encoding="utf-8") as fh:
        fh.write(header + "\n")
        for u in keep:
            e = next(x for x in uniq if x["url"] == u)
            fh.write((e["extinf"] or f'#EXTINF:-1 group-title="NEWS WORLD",{e["name"]}') + "\n")
            fh.write(u + "\n")

    print(f"\nlista5.m3u sobrescrita: {len(keep)} canais "
          f"(antes {len(entries)} entradas / {len(seen)} URLs)")
    print(f"backup: {PLAYLIST}.backup_{ts}_pre_test")
    with open("lista5.m3u.removidos.txt", "a", encoding="utf-8") as fh:
        fh.write(f"\n=== {datetime.utcnow().isoformat()}Z  "
                 f"removidos {len(drop)} URLs ===\n")
        for u, name, n, why in drop:
            fh.write(f"[x{n}] {name}\n  {why}\n  {u}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())