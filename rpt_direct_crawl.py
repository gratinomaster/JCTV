#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(page_timeout=30000, capture_network_requests=True, delay_before_return_html=5)
    
    all_entries = []
    seen_streams = set()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        urls = [
            "https://www.rtp.pt/play/direto/rtp1",
            "https://www.rtp.pt/play/direto/rtp2",
            "https://www.rtp.pt/play/direto/rtp3",
            "https://www.rtp.pt/play/direto/rtpmemoria",
            "https://www.rtp.pt/play/direto/rtpafrica",
            "https://www.rtp.pt/play/direto/rtpacores",
            "https://www.rtp.pt/play/direto/rtpinternacional",
        ]
        for url in urls:
            try:
                print(f"Visiting {url}")
                page = await crawler.arun(url=url, config=crawler_config)
                html_p = page.html or ''
                
                # Look for m3u8
                if page.network_requests:
                    for req in page.network_requests:
                        req_url = req.get('url', '')
                        if isinstance(req_url, str) and '.m3u8' in req_url.lower():
                            if req_url not in seen_streams and ('rtp' in req_url.lower() or 'live' in req_url.lower()):
                                seen_streams.add(req_url)
                                # Extract channel name from URL
                                ch = url.split('/')[-1].upper()
                                all_entries.append((ch, req_url))
                                break
                    else:
                        pass
                
                # Also search html
                if not any(url.split('/')[-1].upper() in str(x[0]) for x in all_entries):
                    for m in re.findall(r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*', html_p):
                        if m not in seen_streams:
                            seen_streams.add(m)
                            ch = url.split('/')[-1].upper()
                            all_entries.append((ch, m))
                            break
                
                await asyncio.sleep(3)
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
