#!/usr/bin/env python3
import re
import requests
from bs4 import BeautifulSoup
import time

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def main():
    all_streams = []
    seen = set()
    
    # Visit homepage
    try:
        resp = session.get('https://www.rtve.es/', timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')
        # Find all links
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'rtve.es' in href or href.startswith('/'):
                if href.startswith('/'):
                    href = 'https://www.rtve.es' + href
                # Look for video/play content
                if any(x in href.lower() for x in ['play', 'video', 'directo', 'serie', 'programa']):
                    links.append((href, a.get_text(strip=True)))
        print(f'Found {len(links)} links')
        links = list(set([(l[0], l[1]) for l in links]))[:80]
        
        for link, title in links:
            try:
                print(f'Checking: {link}')
                r = session.get(link, timeout=20)
                html = r.text
                # Look for m3u8
                m3u8s = re.findall(r'(https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*)', html)
                # Also look in scripts
                for m in m3u8s:
                    if m not in seen and 'rtve' in m.lower():
                        seen.add(m)
                        clean_title = re.sub(r'\s+', ' ', title).strip()
                        if not clean_title or len(clean_title) < 3:
                            clean_title = 'RTVE'
                        all_streams.append((m, clean_title))
                time.sleep(0.5)
            except Exception as e:
                continue
        
        # Write VOD.m3u with group-title VOD
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for stream, title in all_streams:
                # Remove existing group-title if any and ensure our format
                title = re.sub(r'group-title="[^"]*"', '', title)
                f.write(f'#EXTINF:-1 group-title="VOD",{title}\n')
                f.write(f'{stream}\n')
        print(f'Wrote {len(all_streams)} entries')
    except Exception as e:
        print(e)
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')

if __name__ == '__main__':
    main()
