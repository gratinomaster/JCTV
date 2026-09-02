#!/usr/bin/env python3
"""
Fix lista5.m3u v2 - Complete rewrite
"""
import re
import sys
from datetime import datetime

INPUT_FILE = "lista5.m3u"
BACKUP_FILE = f"lista5.m3u.bak.v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

EPG_URL = "https://iptv-org.github.io/epg/guides/us.xml.gz"

CHANNEL_EPG_MAP = {
    "ABC News Live": "ABCNewsLive.us",
    "CBS News": "CBSNews247.us",
    "Fox News": "FoxNewsChannel.us",
    "Fox Business": "FoxBusiness.us",
}

# Canonical names
CANONICAL_NAMES = {
    "ABC News Live": "ABC News Live",
    "CBS News 24/7": "CBS News 24/7",
    "Fox News Channel": "Fox News Channel",
    "Fox Business": "Fox Business",
}

# Best URLs to keep per channel (highest quality, most stable)
PREFERRED_URLS = {
    "ABC News Live": "https://abcnews-livestreams.akamaized.net/out/v1/6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/abcn-live-10-index.m3u8",
    "Fox News Channel": "https://247.foxnews.com/hls/live/2003586/FNCHLSv3/master.m3u8",
    "Fox Business": "https://247.foxbusiness.com/hls/live/2003756/FBNHLSv3/master.m3u8",
    "CBS News 24/7": "https://dai.google.com/linear/hls/pa/event/Sid4xiTQTkCT1SLu6rjUSQ/stream/88646b08-ab9e-47b0-ad28-a883c539d98b:MRN2/master.m3u8",
}

LOGOS = {
    "ABC News Live": "https://keyframe-cdn.abcnews.com/streamprovider10.jpg",
    "Fox News Channel": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/15de0523-3be4-4a9a-8159-7020114e7036/b6ff623a-26d6-4fd9-8bb8-0856adbf38ce/1280x720/match/676/380/image.jpg",
    "Fox Business": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/c9b2e2eb-7b87-435c-9510-eab2650ff944/8b584585-acf2-4c37-aa07-aaf2d077bb20/1280x720/match/676/380/image.jpg",
    "CBS News 24/7": "https://assets2.cbsnewsstatic.com/hub/i/r/2024/04/16/0fb75ad2-a909-44bb-87dc-86b9d51cbeb2/thumbnail/1280x720/949f3d3fef16f9c113e3048c6aef229f/247-key-channelthumbnail-1920x1080.jpg",
}

GROUP = "NEWS WORLD"

SUSPICIOUS = [r"imgur\.com", r"bit\.ly", r"tinyurl\.com", r"t\.co/", r"adfly"]

def identify_channel(url, extinf=""):
    """Identify which channel a URL belongs to."""
    url_lower = url.lower()
    name_lower = extinf.lower()
    
    if "abcnews" in url_lower or "abcn" in url_lower or "abc news" in name_lower:
        return "ABC News Live"
    if "foxnews" in url_lower or "fox news" in name_lower:
        return "Fox News Channel"
    if "foxbusiness" in url_lower or "fox business" in name_lower:
        return "Fox Business"
    if "cbsnews" in url_lower or "cbs" in url_lower or "cbs news" in name_lower:
        return "CBS News 24/7"
    if "dai.google" in url_lower:
        return "CBS News 24/7"
    return None

def is_suspicious(url):
    for p in SUSPICIOUS:
        if re.search(p, url, re.IGNORECASE):
            return True
    return False

def make_extinf(channel_name):
    """Create proper EXTINF line for a channel."""
    epg_id = CHANNEL_EPG_MAP.get(channel_name, "")
    logo = LOGOS.get(channel_name, "")
    parts = [f"#EXTINF:-1"]
    if epg_id:
        parts.append(f'tvg-id="{epg_id}"')
    if logo:
        parts.append(f'tvg-logo="{logo}"')
    parts.append(f'group-title="{GROUP}"')
    parts.append(channel_name)
    return " ".join(parts)

def main():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Backup
    with open(BACKUP_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Backup: {BACKUP_FILE}")
    
    # Parse all entries
    entries = []
    lines = content.strip().split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            extinf = line
            url = None
            i += 1
            while i < len(lines):
                next_line = lines[i].strip()
                if next_line.startswith('#') or next_line.startswith('#EXT'):
                    break
                if next_line and not next_line.startswith('#'):
                    url = next_line
                    i += 1
                    break
                i += 1
            if url:
                entries.append((extinf, url))
        else:
            i += 1
    
    print(f"Total entries parsed: {len(entries)}")
    
    # Identify and filter
    identified = {}
    skipped = 0
    for extinf, url in entries:
        if is_suspicious(url):
            skipped += 1
            continue
        ch = identify_channel(url, extinf)
        if ch:
            if ch not in identified:
                identified[ch] = []
            identified[ch].append(url)
    
    print(f"Suspicious removed: {skipped}")
    print(f"Identified channels: {list(identified.keys())}")
    
    # Select best URL per channel
    output_lines = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
    
    for ch_name in ["ABC News Live", "Fox News Channel", "Fox Business", "CBS News 24/7"]:
        if ch_name not in identified:
            print(f"  WARNING: {ch_name} not found!")
            continue
        
        urls = identified[ch_name]
        preferred = PREFERRED_URLS.get(ch_name)
        
        if preferred and preferred in urls:
            best_url = preferred
        else:
            # Pick master.m3u8 if available, else first
            best_url = urls[0]
            for u in urls:
                if "master.m3u8" in u or "index.m3u8" in u:
                    best_url = u
                    break
        
        extinf_line = make_extinf(ch_name)
        output_lines.append(extinf_line)
        output_lines.append(best_url)
        print(f"  OK: {ch_name} ({len(urls)} variants -> 1)")
    
    # Write output
    output = '\n'.join(output_lines) + '\n'
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(output)
    
    print(f"\nWritten: {INPUT_FILE}")
    print(f"Final channels: {len(output_lines) - 1}")  # -1 for header
    print(f"EPG: {EPG_URL}")

if __name__ == '__main__':
    main()
