#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig()
    
    all_m3u8 = []
    seen = set()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Start from RTVE homepage
        print("Crawling homepage...")
        result = await crawler.arun(url="https://www.rtve.es/", config=crawler_config)
        
        # Collect all links from homepage
        links_to_visit = set()
        if result.links:
            for link in result.links.get('internal', []) + result.links.get('external', []):
                href = link.get('href', '')
                if href and 'rtve.es' in href and href.startswith('http'):
                    links_to_visit.add(href)
        
        # Also extract m3u8 from homepage
        m3u8s_home = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', result.html or '')
        for m in m3u8s_home:
            if m not in seen:
                seen.add(m)
                all_m3u8.append((m, "RTVE"))
        
        # Visit each link
        links_list = list(links_to_visit)[:100]  # Visit up to 100 links
        print(f"Visiting {len(links_list)} links...")
        
        for i, link in enumerate(links_list):
            try:
                print(f"[{i+1}/{len(links_list)}] {link}")
                page = await crawler.arun(url=link, config=crawler_config, timeout=60)
                # Extract m3u8
                m3u8s = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', page.html or '')
                if m3u8s:
                    # Get title
                    title_match = re.search(r'<title>(.*?)</title>', page.html or '', re.I|re.S)
                    title = title_match.group(1).strip() if title_match else "RTVE"
                    title = re.sub(r'<[^>]+>', '', title)
                    title = title.replace('RTVE.es', '').replace('RTVE', '').strip()
                    if not title or len(title) < 2:
                        title = "RTVE"
                    for m in set(m3u8s):
                        if m not in seen:
                            seen.add(m)
                            all_m3u8.append((m, title))
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        # Save to VOD.m3u
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for stream, title in all_m3u8:
                f.write(f'#EXTINF:-1 group-title="VOD",{title}\n')
                f.write(f'{stream}\n')
        
        print(f"Wrote {len(all_m3u8)} entries to VOD.m3u")

if __name__ == '__main__':
    asyncio.run(main())
