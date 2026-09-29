"""Rewrite lista5.m3u keeping only entries whose URL actually decoded video."""
import json
import sys

SRC = "lista5.m3u"
RESULTS = "l5_final_check.json"


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


def main():
    results = json.load(open(RESULTS))
    entries = parse_m3u(SRC)

    kept, removed, seen = [], [], set()
    for e in entries:
        ok = results.get(e["url"], {}).get("ok")
        if not ok:
            removed.append(e)
            continue
        key = (e["extinf"], e["url"])
        if key in seen:
            removed.append(dict(e, _dup=True))
            continue
        seen.add(key)
        kept.append(e)

    with open(SRC, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for e in kept:
            fh.write(e["extinf"] + "\n")
            for x in e["extra"]:
                fh.write(x + "\n")
            fh.write(e["url"] + "\n")

    print("kept:    %d entries (%d unique URLs)"
          % (len(kept), len(seen)))
    print("removed: %d entries" % len(removed))
    print("\n-- removed (dead/DRM/audio-only/duplicate) --")
    for e in removed:
        why = "duplicate" if e.get("_dup") else results[e["url"]]["reason"]
        print("  [%-9s] %s" % (why[:9], e["url"][:100]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
