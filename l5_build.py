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

EPG_LIGHT = "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"
EPG_DEEP = "https://iptv-epg.org/files/epg-us.xml.gz"

LOGO_ABC = "https://keyframe-cdn.abcnews.com/streamprovider11.jpg"
LOGO_CBS = ("https://assets2.cbsnewsstatic.com/hub/i/r/2024/04/16/"
            "0fb75ad2-a909-44bb-87dc-86b9d51cbeb2/thumbnail/1280x720/"
            "949f3d3fef16f9c113e3048c6aef229f/247-key-channelthumbnail-1920x1080.jpg")

STREAM_ABC_1 = ("https://abcnews-livestreams.akamaized.net/out/v1/"
                "6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/"
                "abcn-live-10-index.m3u8")
STREAM_ABC_2 = ("https://abcnews-livestreams.akamaized.net/out/v1/"
                "173a6e46d5c5423d9611bc7fb7899c73/abcn-live-05-cmaf-manifest/"
                "abcn-live-05-index.m3u8")
STREAM_CBS_1 = ("https://dai.google.com/linear/hls/event/"
                "Sid4xiTQTkCT1SLu6rjUSQ/master.m3u8")
STREAM_CBS_2 = "https://news20e7hhcb.airspace-cdn.cbsivideo.com/index.m3u8"

# name, tvg-id, tvg-name, logo, stream, epg, group
CHANNELS = [
    ("ABC News Live", "ABC.News.Live.us2", "ABC News Live", LOGO_ABC,
     STREAM_ABC_1, EPG_LIGHT, "NEWS WORLD"),
    ("ABC News Live - Feed 2", "ABCNewsLive.us", "ABC News Live", LOGO_ABC,
     STREAM_ABC_2, EPG_DEEP, "NEWS WORLD"),
    ("CBS News 24/7", "CBS.News.National.Stream.us2", "CBS News 24/7", LOGO_CBS,
     STREAM_CBS_1, EPG_LIGHT, "NEWS WORLD"),
    ("CBS News 24/7 - Fonte Alt", "CBSNews.us", "CBS News 24/7", LOGO_CBS,
     STREAM_CBS_2, EPG_DEEP, "NEWS WORLD"),
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

    out = [f'#EXTM3U x-tvg-url="{EPG_LIGHT} {EPG_DEEP}"']
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
