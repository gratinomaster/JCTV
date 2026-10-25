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
        try:
            result = await crawler.arun(url="https://www.rtve.es/", config=crawler_config, timeout=30)
            links_to_visit = set()
            if result.links:
                for link in result.links.get('internal', []) + result.links.get('external', []):
                    href = link.get('href', '')
                    if href and 'rtve.es' in href and href.startswith('http'):
                        links_to_visit.add(href)
            
            m3u8s_home = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', result.html or '')
            for m in m3u8s_home:
                if m not in seen:
                    seen.add(m)
                    all_m3u8.append((m, "RTVE"))
        except Exception as e:
            print(e)
        
        links_list = list(links_to_visit)[:50]
        for i, link in enumerate(links_list):
            try:
                page = await crawler.arun(url=link, config=crawler_config, timeout=20)
                m3u8s = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', page.html or '')
                if m3u8s:
                    title_match = re.search(r'<title>(.*?)</title>', page.html or '', re.I|re.S)
                    title = title_match.group(1).strip() if title_match else "RTVE"
                    title = re.sub(r'<[^>]+>', '', title)
                    title = title.replace('RTVE.es', '').replace('RTVE', '').replace('|', '-').strip()
                    if not title or len(title) < 2:
                        title = "RTVE"
                    for m in set(m3u8s):
                        if m not in seen:
                            seen.add(m)
                            all_m3u8.append((m, title[:60]))
                await asyncio.sleep(0.5)
            except Exception:
                continue
        
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for stream, title in all_m3u8:
                f.write(f'#EXTINF:-1 group-title="VOD",{title}\n')
                f.write(f'{stream}\n')
        
        print(f'Wrote {len(all_m3u8)}')

if __name__ == '__main__':
    asyncio.run(main())
