#!/usr/bin/env python3
import asyncio
import re
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    start_url = "https://www.rtve.es/"
    vod_links = set()
    
    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(
        delay_before_return_html=2.0,
        wait_for_images=False,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        res = await crawler.arun(url=start_url, config=run_cfg)
        if res.success and res.html:
            # Look for play/ links in html
            for m in re.findall(r'href=["\']([^"\']+)["\']', res.html):
                link = m
                if link.startswith('//'):
                    link = 'https:' + link
                if not link.startswith('http'):
                    link = urljoin(start_url, link)
                p = urlparse(link)
                if 'rtve.es' not in p.netloc:
                    continue
                if '/play/' in link or '/videos/' in link:
                    # avoid live etc
                    if 'directo' in link or 'radio' in link and 'videos' not in link:
                        continue
                    vod_links.add(link)
    
    streams = []
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for link in list(vod_links)[:15]:
            try:
                r = await crawler.arun(url=link, config=run_cfg)
                if r.success and (r.html or r.markdown):
                    html = r.html or r.markdown
                    m3u8s = re.findall(r'https?://[^\s\'"<>]+\.m3u8(?:[^\s\'"<>]*)', html)
                    if m3u8s:
                        title = re.search(r'<title>([^<]+)</title>', html, re.I)
                        t = title.group(1) if title else link
                        t = re.sub(r'\s*\|\s*RTVE.*$', '', t).strip()
                        streams.append((t, m3u8s[0]))
            except:
                pass
    
    with open('/home/runner/work/JCTV/JCTV/VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for title, url in streams:
            f.write(f'#EXTINF:-1 group-title="VOD" tvg-logo="",{title}\n')
            f.write(f'{url}\n')
    print(f'Wrote {len(streams)} entries')

if __name__ == '__main__':
    asyncio.run(main())
