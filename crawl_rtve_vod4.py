#!/usr/bin/env python3
import asyncio
import re
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    targets = [
        "https://www.rtve.es/play/",
        "https://www.rtve.es/noticias/",
        "https://www.rtve.es/television/",
    ]
    vod_links = set()
    
    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(
        delay_before_return_html=2.0,
        wait_for_images=False,
        remove_overlay_elements=True,
    )
    
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for start in targets:
            try:
                res = await crawler.arun(url=start, config=run_cfg)
                if res.success and res.html:
                    for m in re.findall(r'href=["\']([^"\']+)["\']', res.html):
                        link = m
                        if link.startswith('//'): link = 'https:' + link
                        if not link.startswith('http'): link = urljoin(start, link)
                        if 'rtve.es' not in urlparse(link).netloc: continue
                        if '/play/videos/' in link or '/play/' in link and 'videos' in link:
                            vod_links.add(link)
                        elif '/noticias/' in link and '/video' in link:
                            vod_links.add(link)
                        if len(vod_links) > 60: break
            except Exception as e:
                pass
    
    streams = []
    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        for link in list(vod_links)[:30]:
            try:
                r = await crawler.arun(url=link, config=run_cfg)
                if not r.success: continue
                html = r.html or ''
                # look for m3u8 in html or embedded
                m3u8s = re.findall(r'(https?://[^\'" ]+\.m3u8[^\'" ]*)', html)
                if not m3u8s:
                    m3u8s = re.findall(r'src=["\']([^"\']+\.m3u8[^"\']*)["\']', html)
                if m3u8s:
                    title = re.search(r'<title>([^<]+)</title>', html, re.I)
                    t = title.group(1) if title else link
                    t = re.sub(r'\s*\|\s*RTVE.*$', '', t)
                    t = t.strip().replace('\n',' ').replace('\r',' ')
                    streams.append((t, m3u8s[0]))
            except:
                pass
    
    # dedup
    seen = set()
    out = []
    for t,u in streams:
        if u not in seen:
            seen.add(u)
            out.append((t,u))
    
    with open('/home/runner/work/JCTV/JCTV/VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for title, url in out:
            f.write(f'#EXTINF:-1 group-title="VOD" tvg-logo="",{title}\n')
            f.write(f'{url}\n')
    print(f'Wrote {len(out)} entries')

if __name__ == '__main__':
    asyncio.run(main())
