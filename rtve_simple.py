#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(delay_before_return_html=1.0, wait_for_images=False)
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        res = await crawler.arun(url="https://www.rtve.es/play/", config=run_cfg)
        if res.success and res.html:
            # find m3u8 patterns
            m3u8s = re.findall(r'https?://[^"\']+\.m3u8[^"\']*', res.html)
            print(len(m3u8s))
            for m in m3u8s[:3]:
                print(m)

if __name__ == '__main__':
    asyncio.run(main())
