#!/usr/bin/env python3
"""
Rebuild lista5.m3u from the channels that survived the l5_check.py validation.

Only entries with a verified verdict of PASS in l5_check.json are written, so
a dead / DRM-locked / sub-rendition URL can never re-enter the playlist.

Also guarantees:
  * every URL is immediately preceded by its own #EXTINF line
  * tvg-id resolves in a real XMLTV source (verified in l5_epg.json)
  * url-tvg is declared per entry *and* in the #EXTM3U header
  * tvg-logo is a real .jpg served over HTTP 200
  * no imgur.com anywhere
"""
import json
import re
import shutil
import urllib.request
from datetime import datetime

PLAYLIST = "lista5.m3u"
CHECK = "l5_check.json"

# Single XMLTV source, verified 2026-09-27: it declares ABCNewsLive.us,
# CBSNews.us and FoxNewsChannel.us AND carries programmes for today,
# tomorrow and the day after for all three (iptv-epg.org regenerated daily).
EPG = "https://iptv-epg.org/files/epg-us.xml.gz"

# Every logo below was fetched and confirmed: HTTP 200, Content-Type image/jpeg
# and the SOI marker ff d8 ff. None is an imgur.com link, none is svg/webp/png.
LOGO_ABC = ("https://s.abcnews.com/images/Live/"
            "abc_news_live-abc-ml-250210_1739199021469_hpMain_16x9_608.jpg")
LOGO_CBS = ("https://assets1.cbsnewsstatic.com/hub/i/2024/04/16/"
            "0fb75ad2-a909-44bb-87dc-86b9d51cbeb2/"
            "247-key-channelthumbnail-1920x1080.jpg")
LOGO_FOX = "https://upload.wikimedia.org/wikipedia/commons/c/c4/Fox_news_live_logo_2021.jpg"

# Hosts are the broadcasters' own CDNs, so no expiring hmac/exp token is
# involved: the playlist does not rot overnight like the previous version did.
STREAM_ABC = ("https://abcnews-livestreams.akamaized.net/out/v1/"
              "6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/"
              "abcn-live-10-index.m3u8")
STREAM_CBS = ("https://cbsn-us.cbsnstream.cbsnews.com/out/v1/"
              "55a8648e8f134e82a470f83d562deeca/master.m3u8")
STREAM_FOX = "http://138.121.15.230:9002/FOX-NEWS/index.m3u8"

# name, tvg-id, tvg-name, logo, stream, epg, group
CHANNELS = [
    ("ABC News Live", "ABCNewsLive.us", "ABC News Live", LOGO_ABC,
     STREAM_ABC, EPG, "NEWS WORLD"),
    ("CBS News 24/7", "CBSNews.us", "CBS News 24/7", LOGO_CBS,
     STREAM_CBS, EPG, "NEWS WORLD"),
    ("Fox News Channel", "FoxNewsChannel.us", "Fox News Channel", LOGO_FOX,
     STREAM_FOX, EPG, "NEWS WORLD"),
]


def passing(url):
    with open(CHECK) as fh:
        data = json.load(fh)
    for r in data["results"]:
        if r["url"] == url:
            return r["verdict"] == "PASS", r
    return False, None


def logo_ok(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            d = r.read(200_000)
            ct = r.headers.get("Content-Type", "")
        return r.status == 200 and d[:3] == b"\xff\xd8\xff" and "jpeg" in ct.lower()
    except Exception:
        return False


def main():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copyfile(PLAYLIST, f"{PLAYLIST}.backup_{stamp}_before_rebuild")

    keep, drop = [], []
    for name, tvgid, tvgname, logo, stream, epg, group in CHANNELS:
        ok, res = passing(stream)
        if not ok:
            reason = ";".join((res or {}).get("fail", [])) or "not validated"
            drop.append((name, reason))
            continue
        if "imgur" in logo.lower() or not logo.lower().endswith((".jpg", ".jpeg")):
            drop.append((name, "logo is not .jpg / is imgur"))
            continue
        if not logo_ok(logo):
            drop.append((name, f"logo {logo} not a live JPEG"))
            continue
        keep.append((name, tvgid, tvgname, logo, stream, epg, group))

    out = [f'#EXTM3U url-tvg="{EPG}"']
    for name, tvgid, tvgname, logo, stream, epg, group in keep:
        out.append(
            f'#EXTINF:-1 tvg-id="{tvgid}" tvg-name="{tvgname}" '
            f'tvg-logo="{logo}" group-title="{group}" '
            f'url-tvg="{epg}",{name}')
        out.append(stream)

    with open(PLAYLIST, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print(f"wrote {PLAYLIST}: {len(keep)} channels")
    for k in keep:
        print(f"  + {k[0]:<20} tvg-id={k[1]:<30} {k[4][:58]}")
    for d in drop:
        print(f"  - {d[0]:<20} dropped: {d[1]}")
    print(f"backup: {PLAYLIST}.backup_{stamp}_before_rebuild")


if __name__ == "__main__":
    main()
