#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids"

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(page_timeout=20000)
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=SEARCH_URL, config=crawler_config)
        html = result.html or ''
        # Save for inspection
        with open('google_search.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Len: {len(html)}')
        # Look for links
        links = re.findall(r'href="([^"]+)"', html)
        for l in links[:40]:
            if 'rtp' in l.lower() or 'video' in l.lower() or l.startswith('/url'):
                print(l[:120])
        
if __name__ == '__main__':
    asyncio.run(main())
