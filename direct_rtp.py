#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

# Try common RTP sites
URLS = [
    "https://www.rtp.pt/play/",
    "https://www.rtp.pt/",
    "https://www.rtp.pt/play/direto/",
]

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(page_timeout=20000, capture_network_requests=True)
    
    all_entries = []
    seen_streams = set()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for url in URLS:
            try:
                print(f"Visiting {url}")
                page = await crawler.arun(url=url, config=crawler_config)
                html_p = page.html or ''
                
                # Look for m3u8 in network requests
                if page.network_requests:
                    for req in page.network_requests:
                        req_url = req.get('url', '')
                        if isinstance(req_url, str) and '.m3u8' in req_url.lower():
                            if req_url not in seen_streams:
                                seen_streams.add(req_url)
                                all_entries.append((f"RTP - {url}", req_url))
                
                # Look in HTML
                for m in re.findall(r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*', html_p):
                    if m not in seen_streams:
                        seen_streams.add(m)
                        all_entries.append(("RTP", m))
                
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Err {url}: {e}")
                continue
        
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for title, stream_url in all_entries:
                f.write(f'#EXTINF:-1 group-title="RTP",{title}\n')
                f.write(f'{stream_url}\n')
        
        print(f'Wrote {len(all_entries)} entries')

if __name__ == '__main__':
    asyncio.run(main())
