#!/usr/bin/env python3
"""Audit lista5.m3u: catalog entries, detect sub-streams vs real channels."""
import re
import sys
from collections import Counter, OrderedDict
from urllib.parse import urlparse

PLAYLIST = "lista5.m3u"

EXTINF_RE = re.compile(r'^#EXTINF:(?P<dur>-?[\d.]+)\s*(?P<attrs>.*?),(?P<name>.*)$')
ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')

# patterns that identify a sub-rendition of a master manifest, not a channel
SUBSTREAM_PATTERNS = [
    (re.compile(r'/variant/'), "HLS variant (bandwidth rendition)"),
    (re.compile(r'/audio-[a-z0-9]+-[\d.]+K/'), "audio-only rendition"),
    (re.compile(r'/video-[a-z0-9]+-[\d.]+K/'), "video-only rendition"),
    (re.compile(r'/cmaf-cenc-ctr-'), "CMAF CENC rendition"),
    (re.compile(r'/\d+_hdri_slide\.m3u8'), "CMAF rendition"),
    (re.compile(r'/ctr-all-hdri-sliding\.m3u8'), "CMAF rendition"),
    (re.compile(r'/unenc-all-'), "internal unencrypted rendition"),
    (re.compile(r'/\d+_complete(-\w+)?\.m3u8'), "internal DVR segment list"),
    (re.compile(r'/\d+_complete$'), "internal DVR segment list"),
    (re.compile(r'-index(_\d+)+(_\d+)?\.m3u8$'), "ABCN video/audio rendition"),
]


def parse(path):
    entries = []
    pending = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#EXTM3U"):
                continue
            if line.startswith("#EXTINF"):
                m = EXTINF_RE.match(line)
                attrs = dict(ATTR_RE.findall(m.group("attrs"))) if m else {}
                pending = {
                    "line": lineno,
                    "dur": m.group("dur") if m else None,
                    "attrs": attrs,
                    "name": (m.group("name").strip() if m else line),
                    "url": None,
                }
                continue
            if line.startswith("#"):
                continue
            if pending is None:
                entries.append({"line": lineno, "orphan": True, "url": line,
                                "attrs": {}, "name": None, "dur": None})
            else:
                pending["url"] = line
                entries.append(pending)
                pending = None
    return entries


def classify(url):
    for rx, label in SUBSTREAM_PATTERNS:
        if rx.search(url):
            return label
    return "MASTER CANDIDATE"


def main():
    entries = parse(PLAYLIST)
    print(f"Total entries: {len(entries)}")
    orphans = [e for e in entries if e.get("orphan")]
    print(f"Orphan URLs (no #EXTINF above): {len(orphans)}")
    for o in orphans:
        print(f"  L{o['line']}: {o['url'][:110]}")

    uniq = OrderedDict()
    for e in entries:
        if e.get("orphan"):
            continue
        uniq.setdefault(e["url"], e)

    print(f"\nUnique URLs: {len(uniq)}")
    dupes = Counter(e["url"] for e in entries if not e.get("orphan"))
    print(f"Exact duplicate URLs: {sum(c - 1 for c in dupes.values() if c > 1)}")

    print("\n--- Unique URLs classified ---")
    for url, e in uniq.items():
        print(f"[{classify(url)}]\n  name: {e['name'][:80]}\n  url : {url[:130]}\n")

    print("\n--- Attribute audit ---")
    for attr in ("tvg-id", "tvg-logo", "tvg-name", "group-title", "url-tvg"):
        present = sum(1 for e in uniq.values() if e["attrs"].get(attr))
        print(f"  {attr:<12} present on {present}/{len(uniq)} unique entries")

    print("\n--- tvg-logo formats ---")
    for logo in sorted({e["attrs"].get("tvg-logo", "<none>") for e in uniq.values()}):
        ext = "n/a"
        if logo != "<none>":
            path = urlparse(logo).path.lower()
            ext = os.path.splitext(path)[1] or "(no extension)"
        flag = "OK" if ext in (".jpg", ".jpeg") else "NOT-JPG"
        host = urlparse(logo).netloc if logo != "<none>" else ""
        bad = " <-- imgur!" if "imgur" in host else ""
        print(f"  [{flag}] ext={ext:<14} {logo}{bad}")

    print("\n--- Channel names / affiliate signals ---")
    for e in uniq.values():
        print(f"  {e['name']}")


if __name__ == "__main__":
    import os
    main()
