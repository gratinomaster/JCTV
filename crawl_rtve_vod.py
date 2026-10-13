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
        wait_for_css=False,
        exclude_external_links=False,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        # Crawl homepage
        result = await crawler.arun(url=start_url, config=run_cfg)
        if result.success and result.markdown:
            # Extract all links
            links = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', result.markdown)
            for text, link in links:
                if not link.startswith('http'):
                    link = urljoin(start_url, link)
                parsed = urlparse(link)
                if 'rtve.es' in parsed.netloc:
                    if any(k in link for k in ['/play/videos/', '/videos/', '/a-la-carta/']) and link not in seen:
                        vod_links.add(link)
                        seen.add(link)
    
    # Now fetch each video page and extract streams
    streams = []
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for link in list(vod_links)[:30]:  # limit to avoid too many
            try:
                res = await crawler.arun(url=link, config=run_cfg)
                if res.success and res.html:
                    # Look for m3u8
                    m3u8s = re.findall(r'(https?://[^\s\'"]+\.m3u8[^\s\'"]*)', res.html)
                    if not m3u8s:
                        # look for mpd or direct mp4? less common
                        m3u8s = re.findall(r'(https?://[^\'"]+\.mp4[^\'"]*)', res.html)
                    if m3u8s:
                        title = re.search(r'<title>([^<]+)</title>', res.html)
                        t = title.group(1).strip() if title else link.split('/')[-1]
                        # clean title
                        t = re.sub(r'\s*\|\s*RTVE\.es.*$', '', t)
                        for m in m3u8s[:1]:  # take first
                            streams.append((t, m))
            except Exception as e:
                pass
    
    # Write M3U
    with open('/home/runner/work/JCTV/JCTV/VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for title, url in streams:
            f.write(f'#EXTINF:-1 group-title="VOD" tvg-logo="",{title}\n')
            f.write(f'{url}\n')
    
    print(f'Wrote {len(streams)} entries')

if __name__ == '__main__':
    asyncio.run(main())
