#!/usr/bin/env python3
import asyncio
import json
import re
from urllib.parse import urljoin, urlparse
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Start from RTVE homepage
        result = await crawler.arun(url="https://www.rtve.es/", config=crawler_config)
        print(f"Status: {result.status_code}")
        
        # Look for links
        links = []
        if result.links:
            for link in result.links.get('internal', []) + result.links.get('external', []):
                href = link.get('href', '')
                if href and 'rtve.es' in href:
                    # Filter for potential video/VOD content
                    if any(x in href.lower() for x in ['video', 'vod', 'programa', 'serie', 'pelicula', 'documental']):
                        links.append(href)
        
        # Also look for m3u8 in the page
        m3u8_links = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', result.html or '')
        print(f"Found {len(m3u8_links)} m3u8 on homepage")
        
        # Deduplicate
        links = list(set(links))[:50]  # Limit to avoid too many requests
        
        all_m3u8 = set(m3u8_links)
        entry_info = []
        
        for link in links[:30]:  # Process up to 30 pages
            try:
                print(f"Crawling: {link}")
                page = await crawler.arun(url=link, config=crawler_config)
                m3u8s = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', page.html or '')
                for m in m3u8s:
                    all_m3u8.add(m)
                    # Try to get title
                    title_match = re.search(r'<title>(.*?)</title>', page.html or '', re.I|re.S)
                    title = title_match.group(1).strip() if title_match else link.split('/')[-1]
                    entry_info.append((m, title))
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Error on {link}: {e}")
                continue
        
        # Write to VOD.m3u
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            seen = set()
            count = 0
            for m3u8, title in entry_info:
                if m3u8 in seen:
                    continue
                seen.add(m3u8)
                # Clean title
                title = re.sub(r'<[^>]+>', '', title)
                title = title.replace('RTVE.es', '').strip()
                if not title:
                    title = f'RTVE {count}'
                f.write(f'#EXTINF:-1 group-title="VOD",{title}\n')
                f.write(f'{m3u8}\n')
                count += 1
        
        print(f"Wrote {count} entries to VOD.m3u")

if __name__ == '__main__':
    asyncio.run(main())
