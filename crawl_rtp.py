import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import BrowserLaunchConfig
from bs4 import BeautifulSoup
import os

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids&biw=1528&bih=732&tbs=qdr%3Ad&sxsrf=APpeQns5pe_IkcCACzvPHgkdmwaASNtHaA%3A1791776213601&ei=1VXMasufJPqj1sQPgM-S8Qo&ved=2ahUKEwiL3unFxrOXAxX6kZUCHYCnJK4Q4dUDegQIBRAM&uact=5&oq=rtp&gs_lp=EhZnd3Mtd2l6LW1vZGVsZXNzLXZpZGVvIgNydHAyChAAGIAEGIoFGEMyCBAAGIAEGLEDMgoQABiABBiKBRhDMgoQABiABBiKBRhDMgUQABiABDIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIFEAAYgAQyBRAAGIAESNkQUPwIWPIOcAN4AJABAJgBb6ABpgOqAQMwLjS4AQPIAQD4AQGYAgagAsQDqAIAwgINEAAYgAQYigUYQxixA8ICBhAAGAcYHsICCxAAGIAEGLEDGIMBwgIOEAAYgAQYigUYsQMYgwGYAwKIBgGSBwMyLjSgB74SsgcDMC40uAe5A8IHBTAuMi40yAcTgAgB&sclient=gws-wiz-modeless-video"

async def main():
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
    )
    run_config = CrawlerRunConfig(
        wait_until='domcontentloaded',
        page_timeout=60000,
        delay_before_return_html=2,
    )
    
    result_urls = []
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Crawl initial search page
        print("Crawling Google Videos search page...")
        try:
            result = await crawler.arun(url=SEARCH_URL, config=run_config)
            if result and result.html:
                soup = BeautifulSoup(result.html, 'html.parser')
                # Google Video results usually have links
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    # Skip google internal links
                    if href.startswith('http') and not href.startswith('https://www.google.com'):
                        result_urls.append(href)
                # Deduplicate while preserving order
                seen = set()
                uniq = []
                for u in result_urls:
                    if u not in seen:
                        uniq.append(u)
                        seen.add(u)
                result_urls = uniq
        except Exception as e:
            print(f"Error crawling search page: {e}")
    
    print(f"Found {len(result_urls)} result links")
    
    # Crawl each result link to find video streams
    video_urls = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, url in enumerate(result_urls[:20]):  # Limit to avoid too many requests
            print(f"Crawling {i+1}/{min(len(result_urls), 20)}: {url[:80]}...")
            try:
                res = await crawler.arun(url=url, config=run_config)
                if res and res.html:
                    soup = BeautifulSoup(res.html, 'html.parser')
                    # Look for common video stream patterns
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if any(ext in href for ext in ['.m3u8', '.mp4', '.ts', '.webm', 'manifest', 'playlist']):
                            video_urls.append(href)
                    # Also look for video tags and sources
                    for vid in soup.find_all('video'):
                        for src in vid.find_all('source'):
                            if src.get('src'):
                                video_urls.append(src['src'])
                        if vid.get('src'):
                            video_urls.append(vid['src'])
            except Exception as e:
                print(f"  Error: {e}")
            await asyncio.sleep(1)  # Be polite
    
    # Deduplicate
    seen = set()
    final = []
    for u in video_urls:
        if u not in seen:
            final.append(u)
            seen.add(u)
    
    print(f"Found {len(final)} video/stream URLs")
    
    # Write M3U file
    with open('VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for url in final:
            f.write(f'#EXTINF:-1 group-title="RTP",RTP Stream\n')
            f.write(f'{url}\n')
    
    print(f"Saved to VOD.m3u")

if __name__ == '__main__':
    asyncio.run(main())
