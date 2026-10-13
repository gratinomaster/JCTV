#!/usr/bin/env python3
import asyncio
import re
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    start_url = "https://www.rtve.es/"
    seen = set()
    vod_links = set()
    
    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(
        delay_before_return_html=2.0,
        wait_for_images=False,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=start_url, config=run_cfg)
        if result.success and result.html:
            # Find play video links
            for m in re.findall(r'href="([^"]+)"', result.html):
                link = m
                if not link.startswith('http'):
                    link = urljoin(start_url, link)
                if 'rtve.es' not in urlparse(link).netloc:
                    continue
                if '/play/' in link and link not in seen:
                    seen.add(link)
                    vod_links.add(link)
                    if len(vod_links) > 40:
                        break
    
    streams = []
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for link in vod_links:
            try:
                res = await crawler.arun(url=link, config=run_cfg)
                if res.success and res.html:
                    m3u8s = re.findall(r'(https?://[^\'" ]+\.m3u8[^\'" ]*)', res.html)
                    if not m3u8s:
                        m3u8s = re.findall(r'(https?://[^\'" ]+\.mp4[^\'" ]*)', res.html)
                    if m3u8s:
                        title = re.search(r'<title>([^<]+)</title>', res.html)
                        t = title.group(1).strip() if title else link
                        t = re.sub(r'\s*\|\s*RTVE.*$', '', t)
                        streams.append((t, m3u8s[0], link))
            except:
                pass
    
    with open('/home/runner/work/JCTV/JCTV/VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for title, url, _ in streams[:20]:
            f.write(f'#EXTINF:-1 group-title="VOD" tvg-logo="",{title}\n')
            f.write(f'{url}\n')
    print(f'Wrote {len(streams[:20])} entries')

if __name__ == '__main__':
    asyncio.run(main())
