#!/usr/bin/env python3
"""
Fix lista5.m3u v3 - Works from the 20260901 backup
"""
import re
from datetime import datetime

BACKUP_FILE = "lista5.m3u.bak.20260901_233549"
OUTPUT_FILE = "lista5.m3u"

EPG_URL = "https://iptv-epg.org/files/epg-us.xml.gz"

# EPG IDs for iptv-org
EPG_IDS = {
    "ABC News Live": "ABCNewsLive.us",
    "Fox News": "FoxNewsChannel.us",
    "Fox Business": "FoxBusiness.us",
    "CBS News": "CBSNews.us",
}

# Best logo URLs (clean, no query params, .jpg)
LOGOS = {
    "ABC News Live": "https://keyframe-cdn.abcnews.com/streamprovider10.jpg",
    "Fox News": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/15de0523-3be4-4a9a-8159-7020114e7036/b6ff623a-26d6-4fd9-8bb8-0856adbf38ce/1280x720/match/676/380/image.jpg",
    "Fox Business": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/c9b2e2eb-7b87-435c-9510-eab2650ff944/8b584585-acf2-4c37-aa07-aaf2d077bb20/1280x720/match/676/380/image.jpg",
    "CBS News": "https://assets2.cbsnewsstatic.com/hub/i/r/2024/04/16/0fb75ad2-a909-44bb-87dc-86b9d51cbeb2/thumbnail/1280x720/949f3d3fef16f9c113e3048c6aef229f/247-key-channelthumbnail-1920x1080.jpg",
}

# Best URLs per channel (free/public, tested working)
BEST_URLS = {
    "ABC News Live": "https://abcnews-livestreams.akamaized.net/out/v1/6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/abcn-live-10-index.m3u8",
    "Fox News": "http://247preview.foxnews.com/hls/live/2020027/fncv3preview/primary.m3u8",
    "Fox Business": "https://247preview.foxbusiness.com/hls/live/2020026/fbnv3preview/primary.m3u8",
    "CBS News": "https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8",
}

GROUP = "NEWS WORLD"

SUSPICIOUS = [r"imgur\.com", r"bit\.ly", r"tinyurl\.com", r"t\.co/", r"adfly", r"ouo\.io"]

def identify_channel(url, extinf):
    """Identify channel by URL domain and EXTINF name."""
    u = url.lower()
    n = extinf.lower()
    if "abcnews" in u or "abcn" in u or "abc news" in n or "abcnl" in n:
        return "ABC News Live"
    if "foxbusiness" in u or "fox business" in n:
        return "Fox Business"
    if "foxnews" in u or "fox news" in n:
        return "Fox News"
    if "cbsnews" in u or "dai.google" in u or "cbs news" in n:
        return "CBS News"
    return None

def is_suspicious(url):
    for p in SUSPICIOUS:
        if re.search(p, url, re.IGNORECASE):
            return True
    return False

def parse_m3u(text):
    """Parse M3U into list of (extinf, url) tuples."""
    lines = text.strip().split('\n')
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            extinf = line
            url = None
            i += 1
            while i < len(lines):
                nl = lines[i].strip()
                if nl.startswith('#'):
                    break
                if nl:
                    url = nl
                    i += 1
                    break
                i += 1
            if url:
                entries.append((extinf, url))
        else:
            i += 1
    return entries

def main():
    print(f"Reading backup: {BACKUP_FILE}")
    with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    entries = parse_m3u(content)
    print(f"Total entries: {len(entries)}")
    
    # Classify and deduplicate
    channels = {}
    for extinf, url in entries:
        if is_suspicious(url):
            print(f"  SKIP suspicious: {url[:50]}...")
            continue
        ch = identify_channel(url, extinf)
        if not ch:
            print(f"  SKIP unknown: {url[:60]}...")
            continue
        if ch not in channels:
            channels[ch] = set()
        # Normalize URL for dedup (remove quality-specific parts)
        norm = re.sub(r'/bandwidth/\d+', '', url)
        norm = re.sub(r'\d+_hdri_slide\.m3u8', 'X.m3u8', norm)
        norm = re.sub(r'index_[^/]+\.m3u8', 'index.m3u8', norm)
        norm = re.sub(r'variant/[a-f0-9]+/', 'variant/XXX/', norm)
        channels[ch].add(norm)
    
    for ch, urls in channels.items():
        print(f"  {ch}: {len(urls)} unique URLs")
    
    # Build clean M3U
    output = [f'#EXTM3U x-tvg-url="{EPG_URL}"']
    
    for ch_name in ["ABC News Live", "Fox News", "Fox Business", "CBS News"]:
        if ch_name not in channels:
            print(f"  MISSING: {ch_name}")
            continue
        
        epg_id = EPG_IDS[ch_name]
        logo = LOGOS[ch_name]
        best_url = BEST_URLS[ch_name]
        canonical = ch_name
        
        extinf = f'#EXTINF:-1 tvg-id="{epg_id}" tvg-logo="{logo}" group-title="{GROUP}" {canonical}'
        output.append(extinf)
        output.append(best_url)
        print(f"  ADDED: {ch_name}")
    
    # Write
    result = '\n'.join(output) + '\n'
    
    backup = f"lista5.m3u.bak.pre_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup, 'w') as f:
        f.write(content)
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write(result)
    
    print(f"\nDone! {len(output)-1} channels written to {OUTPUT_FILE}")
    print(f"EPG: {EPG_URL}")

if __name__ == '__main__':
    main()
