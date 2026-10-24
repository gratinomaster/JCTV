#!/usr/bin/env python3
import requests
from bs4 import BeautifulSoup
import json
import re
import time

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

def crawl():
    entries = []
    # Try to get from RTVE Play API or scrape
    try:
        # Try categories
        urls = [
            'https://www.rtve.es/play/',
            'https://www.rtve.es/play/videos/',
            'https://www.rtve.es/play/audios/',
        ]
        for url in urls:
            try:
                resp = session.get(url, timeout=30)
                print(f'{url}: {resp.status_code}')
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Find all links
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if '/videos/' in href or '/audios/' in href:
                        if href.startswith('/'):
                            href = 'https://www.rtve.es' + href
                        if href not in [e[0] for e in entries]:
                            entries.append((href, a.get_text(strip=True)))
            except Exception as e:
                print(e)
    except Exception as e:
        print(e)
    
    print(f'Found {len(entries)} potential links')
    return entries[:100]

def extract_m3u8(url):
    try:
        resp = session.get(url, timeout=30)
        html = resp.text
        # Look for m3u8
        m3u8s = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', html)
        if m3u8s:
            return list(set(m3u8s))
        # Look in JSON
        # Sometimes in script tags
        scripts = re.findall(r'<script[^>]+>(.*?)</script>', html, re.S)
        for s in scripts:
            m3u8s = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', s)
            if m3u8s:
                return list(set(m3u8s))
    except:
        pass
    return []

def main():
    links = crawl()
    all_streams = []
    seen = set()
    for link, title in links:
        try:
            print(f'Checking {link}')
            streams = extract_m3u8(link)
            for s in streams:
                if s in seen:
                    continue
                seen.add(s)
                all_streams.append((s, title or 'RTVE'))
            time.sleep(1)
        except:
            continue
    
    # Write VOD.m3u
    with open('VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for stream, title in all_streams:
            # Clean title
            title = re.sub(r'\s+', ' ', title).strip()
            if not title or len(title) < 2:
                title = 'RTVE'
            f.write(f'#EXTINF:-1 group-title="VOD",{title}\n')
            f.write(f'{stream}\n')
    
    print(f'Wrote {len(all_streams)} entries')

if __name__ == '__main__':
    main()
