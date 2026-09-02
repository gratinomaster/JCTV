#!/usr/bin/env python3
"""Test if EPG works and if streams are alive."""
import urllib.request
import gzip
import io
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

EPG_URL = "https://iptv-org.github.io/epg/guides/us.xml.gz"
CHANNELS_TO_CHECK = ["ABCNewsLive.us", "FoxNewsChannel.us", "FoxBusiness.us", "CBSNews247.us"]

def fetch_epg(url):
    """Fetch and decompress EPG XML."""
    print(f"Fetching EPG: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        print(f"  Downloaded: {len(data)} bytes")
        # Try gzip decompress
        try:
            data = gzip.decompress(data)
            print(f"  After decompress: {len(data)} bytes")
        except OSError:
            print("  Not gzipped or already decompressed")
        return data
    except Exception as e:
        print(f"  ERROR: {e}")
        return None

def parse_and_check(data):
    """Parse EPG XML and check for today's programs."""
    if not data:
        return
    
    # Try to parse XML
    try:
        root = ET.fromstring(data)
    except Exception as e:
        # Maybe it's HTML or not valid XML
        print(f"  XML parse error: {e}")
        # Try to see if it's a valid response at all
        text = data[:500].decode('utf-8', errors='replace')
        print(f"  First 500 chars: {text[:200]}...")
        return
    
    xml_channels = []
    for ch in root.findall('.//channel'):
        ch_id = ch.get('id', '')
        xml_channels.append(ch_id)
    
    print(f"  Found {len(xml_channels)} channels in EPG")
    
    # Check for our channels
    today = datetime.now().strftime('%Y%m%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y%m%d')
    day_after = (datetime.now() + timedelta(days=2)).strftime('%Y%m%d')
    
    for ch_to_check in CHANNELS_TO_CHECK:
        found = ch_to_check in xml_channels
        ch_ids_matched = [c for c in xml_channels if ch_to_check.split('.')[0].lower() in c.lower()]
        
        print(f"\n  Channel {ch_to_check}: {'FOUND' if found else 'NOT FOUND'}")
        if ch_ids_matched and not found:
            print(f"    Similar IDs: {ch_ids_matched[:5]}")
        
        if found:
            # Check programs for today/tomorrow/day-after
            p_counts = {today: 0, tomorrow: 0, day_after: 0}
            for prog in root.findall('.//programme'):
                if prog.get('channel') == ch_to_check:
                    start = prog.get('start', '')
                    pdate = start[:8]
                    if pdate in p_counts:
                        p_counts[pdate] += 1
            print(f"    Programs today: {p_counts[today]}")
            print(f"    Programs tomorrow: {p_counts[tomorrow]}")
            print(f"    Programs day+2: {p_counts[day_after]}")

def test_streams():
    """Test if stream URLs respond."""
    print("\n=== Testando streams ===")
    urls = {
        "ABC News Live": "https://abcnews-livestreams.akamaized.net/out/v1/6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/abcn-live-10-index.m3u8",
        "Fox News": "https://247.foxnews.com/hls/live/2003586/FNCHLSv3/master.m3u8",
        "Fox Business": "https://247.foxbusiness.com/hls/live/2003756/FBNHLSv3/master.m3u8",
        "CBS News": "https://dai.google.com/linear/hls/pa/event/Sid4xiTQTkCT1SLu6rjUSQ/stream/d7a35bc8-b353-4780-b75f-2c6f5295d278:CBF2/master.m3u8",
    }
    
    for name, url in urls.items():
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                content_type = resp.headers.get('Content-Type', '')
                first = resp.read(200).decode('utf-8', errors='replace')
                # Check if it looks like an HLS manifest
                is_hls = '#EXTM3U' in first or 'application/' in content_type
                print(f"  {name}: HTTP {status} | content-type={content_type} | HLS={'YES' if is_hls else 'MAYBE'}")
        except urllib.error.HTTPError as e:
            print(f"  {name}: HTTP ERROR {e.code}")
        except urllib.error.URLError as e:
            print(f"  {name}: URL ERROR {e.reason}")
        except Exception as e:
            print(f"  {name}: ERROR {e}")

if __name__ == '__main__':
    data = fetch_epg(EPG_URL)
    parse_and_check(data)
    test_streams()
