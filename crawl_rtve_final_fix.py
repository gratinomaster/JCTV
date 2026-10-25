#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(page_timeout=15000)
    
    all_m3u8 = []
    seen = set()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url="https://www.rtve.es/", config=crawler_config)
            # Try all possible patterns
            for pattern in [
                r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
                r'["\']([^"\']+\.m3u8[^"\']*)["\']',
                r'src["\']:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            ]:
                for m in re.findall(pattern, result.html or ''):
                    if isinstance(m, tuple):
                        m = m[0] if m else None
                    if m and m not in seen and '.m3u8' in m:
                        seen.add(m)
                        all_m3u8.append((m, "RTVE"))
            
            links_to_visit = set()
            if result.links:
                for k in ['internal', 'external']:
                    for link in result.links.get(k, []):
                        href = link.get('href', '')
                        if href and 'rtve.es' in href and href.startswith('http'):
                            links_to_visit.add(href)
        except Exception as e:
            print(e)
            pass
        
        links_list = list(links_to_visit)
        for link in links_list:
            try:
                page = await crawler.arun(url=link, config=crawler_config)
                for pattern in [
                    r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
                    r'["\']([^"\']+\.m3u8[^"\']*)["\']',
                ]:
                    for m in re.findall(pattern, page.html or ''):
                        if isinstance(m, tuple):
                            m = m[0] if m else None
                        if m and m not in seen and '.m3u8' in m:
                            seen.add(m)
                            title_match = re.search(r'<title>(.*?)</title>', page.html or '', re.I|re.S)
                            title = title_match.group(1).strip() if title_match else "RTVE"
                            title = re.sub(r'<[^>]+>', '', title)
                            title = re.sub(r'\s+', ' ', title)
                            title = title.replace('RTVE.es', '').replace('RTVE', '').replace('  ', ' ').strip(' -|')
                            if not title:
                                title = "RTVE"
                            all_m3u8.append((m, title[:80]))
                await asyncio.sleep(0.2)
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
