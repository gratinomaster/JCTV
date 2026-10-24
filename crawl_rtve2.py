#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url="https://www.rtve.es/play/videos/", config=crawler_config)
        print(f"Status: {result.status_code}")
        
        html = result.html or ''
        # Look for various patterns
        patterns = [
            r'["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'src[:=]\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
            r'videoUrl["\']?\s*[:=]\s*["\']([^"\']+)["\']',
            r'url["\']?\s*[:=]\s*["\']([^"\']+\.mpd[^"\']*)["\']',
        ]
        all_links = set()
        for p in patterns:
            matches = re.findall(p, html, re.I)
            for m in matches:
                if '.m3u8' in m or '.mpd' in m:
                    all_links.add(m)
        print(f"Found {len(all_links)} streams")
        for l in list(all_links)[:10]:
            print(l)
        
        # Also get links to videos
        video_links = re.findall(r'href="([^"]*play/videos/[^"]+)"', html)
        print(f"\nVideo links: {len(video_links)}")
        for vl in video_links[:15]:
            print(vl)

if __name__ == '__main__':
    asyncio.run(main())
