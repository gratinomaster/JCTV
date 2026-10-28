#!/usr/bin/env python3
import asyncio
import re
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids&biw=1528&bih=732&tbs=qdr%3Ad&sxsrf=APpeQns5pe_IkcCACzvPHgkdmwaASNtHaA%3A1791776213601&ei=1VXMasufJPqj1sQPgM-S8Qo&ved=2ahUKEwiL3unFxrOXAxX6kZUCHYCnJK4Q4dUDegQIBRAM&uact=5&oq=rtp&gs_lp=EhZnd3Mtd2l6LW1vZGVsZXNzLXZpZGVvIgNydHAyChAAGIAEGIoFGEMyCBAAGIAEGLEDMgoQABiABBiKBRhDMgoQABiABBiKBRhDMgUQABiABDIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIFEAAYgAQyBRAAGIAESNkQUPwIWPIOcAN4AJABAJgBb6ABpgOqAQMwLjS4AQPIAQD4AQGYAgagAsQDqAIAwgINEAAYgAQYigUYQxixA8ICBhAAGAcYHsICCxAAGIAEGLEDGIMBwgIOEAAYgAQYigUYsQMYgwGYAwKIBgGSBwMyLjSgB74SsgcDMC40uAe5A8IHBTAuMi40yAcTgAgB&sclient=gws-wiz-modeless-video"

async def main():
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(page_timeout=20000, capture_network_requests=True)
    
    all_entries = []
    seen_streams = set()
    visited = set()
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Get search results
        try:
            result = await crawler.arun(url=SEARCH_URL, config=crawler_config)
            html = result.html or ''
            
            # Look for video/result links - various patterns
            links_to_visit = set()
            # Google video results often have links in /url?q= or direct links
            for m in re.findall(r'href=["\']([^"\']+)["\']', html):
                href = m
                if href.startswith('/url?q='):
                    # Extract actual URL
                    actual = href.split('/url?q=')[1].split('&')[0]
                    from urllib.parse import unquote
                    actual = unquote(actual)
                    if actual.startswith('http') and 'google.com' not in actual:
                        links_to_visit.add(actual)
                elif href.startswith('http') and 'google.com' not in href and 'youtube.com' not in href and '/search' not in href:
                    links_to_visit.add(href)
                elif 'rtp' in href.lower() and href.startswith('http') and 'google.com' not in href:
                    links_to_visit.add(href)
            
            # Also look in result objects
            if result.links:
                for k in ['internal', 'external']:
                    for link in result.links.get(k, []):
                        href = link.get('href', '')
                        if href and href.startswith('http') and 'google.com' not in href:
                            links_to_visit.add(href)
        except Exception as e:
            print(f"Error fetching search: {e}")
            links_to_visit = set()
        
        # Visit each link
        for link in links_to_visit:
            if link in visited:
                continue
            visited.add(link)
            try:
                page = await crawler.arun(url=link, config=crawler_config)
                html_p = page.html or ''
                
                # Look for m3u8 in network requests
                if page.network_requests:
                    for req in page.network_requests:
                        req_url = req.get('url', '')
                        if isinstance(req_url, str):
                            req_url_lower = req_url.lower()
                            if '.m3u8' in req_url_lower:
                                stream_url = req_url
                                if stream_url not in seen_streams:
                                    seen_streams.add(stream_url)
                                    # Get title
                                    title = "RTP"
                                    title_match = re.search(r'<title>(.*?)</title>', html_p, re.I|re.S)
                                    if title_match:
                                        t = title_match.group(1)
                                        t = re.sub(r'<[^>]+>', '', t)
                                        t = re.sub(r'\s+', ' ', t)
                                        t = t.strip()
                                        if t:
                                            title = t[:100]
                                    all_entries.append((title, stream_url))
                                    continue
                
                # Look for m3u8 in HTML
                for pattern in [
                    r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
                    r'["\']([^"\']+\.m3u8[^"\']*)["\']',
                ]:
                    for m in re.findall(pattern, html_p):
                        if isinstance(m, tuple):
                            m = m[0] if m else None
                        if m and '.m3u8' in m and m not in seen_streams:
                            seen_streams.add(m)
                            title = "RTP"
                            title_match = re.search(r'<title>(.*?)</title>', html_p, re.I|re.S)
                            if title_match:
                                t = title_match.group(1)
                                t = re.sub(r'<[^>]+>', '', t)
                                t = re.sub(r'\s+', ' ', t)
                                t = t.strip()
                                if t:
                                    title = t[:100]
                            all_entries.append((title, m))
                            break
                    else:
                        continue
                    break
                
                await asyncio.sleep(1)
            except Exception as e:
                continue
        
        # Write to VOD.m3u
        with open('VOD.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            for title, stream_url in all_entries:
                # Clean title
                title_clean = title.replace('\n', ' ').replace('\r', ' ')
                f.write(f'#EXTINF:-1 group-title="RTP",{title_clean}\n')
                f.write(f'{stream_url}\n')
        
        print(f'Wrote {len(all_entries)} entries to VOD.m3u')

if __name__ == '__main__':
    asyncio.run(main())
