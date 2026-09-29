#!/usr/bin/env python3
"""Audit a M3U: structure violations, duplicates, attribute gaps, logo formats."""
import re
import sys
from collections import Counter, OrderedDict
from urllib.parse import urlparse

ATTR = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')

def parse(path):
    entries, cur = [], None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, raw in enumerate(fh, 1):
            line = raw.rstrip("\n").strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                cur = {"n": n, "extinf": line, "attrs": dict(ATTR.findall(line)),
                       "url": None, "urlline": None}
                entries.append(cur)
            elif line.startswith("#"):
                (cur.setdefault("extra", []).append(line) if cur else None)
            else:
                if cur is None:
                    entries.append({"n": n, "extinf": None, "attrs": {},
                                    "url": line, "urlline": n, "orphan": True})
                else:
                    cur["url"] = line
                    cur["urlline"] = n
    return entries

def title(extinf):
    if not extinf:
        return "?"
    body = extinf.split("#EXTINF:", 1)[1]
    return body.split(",", 1)[1] if "," in body else "?"

def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "lista5.m3u"
    entries = parse(path)
    print(f"file={path}  entries={len(entries)}")

    orphans = [e for e in entries if e.get("orphan")]
    nourl = [e for e in entries if not e.get("orphan") and not e["url"]]
    print(f"\n[structure] orphan URL lines (no #EXTINF above): {len(orphans)}")
    for e in orphans:
        print(f"   L{e['n']}: {e['url'][:110]}")
    print(f"[structure] #EXTINF with no URL after it: {len(nourl)}")

    noid = [e for e in entries if not e.get("orphan") and "tvg-id" not in e["attrs"]]
    nologo = [e for e in entries if not e.get("orphan") and not e["attrs"].get("tvg-logo")]
    print(f"\n[attrs] entries without tvg-id : {len(noid)}")
    print(f"[attrs] entries without tvg-logo: {len(nologo)}")

    bad_logo = []
    for e in entries:
        if e.get("orphan"):
            continue
        lg = e["attrs"].get("tvg-logo", "")
        if lg and not re.search(r"\.jpg(\?|$)", lg, re.I):
            bad_logo.append((e["n"], lg))
    print(f"[attrs] tvg-logo NOT ending in .jpg: {len(bad_logo)}")
    for n, lg in bad_logo[:20]:
        print(f"   L{n}: {lg[:110]}")

    hosts = Counter()
    for e in entries:
        if e["url"]:
            hosts[urlparse(e["url"]).netloc] += 1
    print(f"\n[hosts] {len(hosts)} distinct")
    for h, c in hosts.most_common():
        print(f"   {c:>4}  {h}")

    print("\n[by title]")
    byt = OrderedDict()
    for e in entries:
        byt.setdefault(title(e["extinf"]), []).append(e)
    for t, es in byt.items():
        hosts_t = Counter(urlparse(e["url"]).netloc for e in es if e["url"])
        print(f"  {len(es):>3}x  {t[:78]}")
        for h, c in hosts_t.most_common():
            print(f"        {c:>3} {h}")

    seen = Counter(e["url"] for e in entries if e["url"])
    dups = {u: c for u, c in seen.items() if c > 1}
    print(f"\n[dups] identical URLs repeated: {len(dups)} url(s), "
          f"{sum(dups.values())} lines")
    for u, c in list(dups.items())[:10]:
        print(f"   {c}x {u[:100]}")

    audio = [e for e in entries if e["url"] and re.search(r"/audio-aac|/audio_only|\.aac$", e["url"], re.I)]
    drm = [e for e in entries if e["url"] and re.search(r"cmaf-cenc|cenc-|\.key$|widevine|playready|fairplay", e["url"], re.I)]
    print(f"\n[media] audio-only rendition URLs : {len(audio)}")
    print(f"[media] DRM-looking URLs (cenc/key): {len(drm)}")

    with open(path, encoding="utf-8", errors="replace") as fh:
        head = [next(fh, "") for _ in range(1)]
    print(f"\n[header] {head[0].rstrip()!r}")

if __name__ == "__main__":
    main()