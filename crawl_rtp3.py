import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from bs4 import BeautifulSoup
import os
import re

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids&biw=1528&bih=732&tbs=qdr%3Ad&sxsrf=APpeQns5pe_IkcCACzvPHgkdmwaASNtHaA%3A1791776213601&ei=1VXMasufJPqj1sQPgM-S8Qo&ved=2ahUKEwiL3unFxrOXAxX6kZUCHYCnJK4Q4dUDegQIBRAM&uact=5&oq=rtp&gs_lp=EhZnd3Mtd2l6LW1vZGVsZXNzLXZpZGVvIgNydHAyChAAGIAEGIoFGEMyCBAAGIAEGLEDMgoQABiABBiKBRhDMgoQABiABBiKBRhDMgUQABiABDIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIFEAAYgAQyBRAAGIAESNkQUPwIWPIOcAN4AJABAJgBb6ABpgOqAQMwLjS4AQPIAQD4AQGYAgagAsQDqAIAwgINEAAYgAQYigUYQxixA8ICBhAAGAcYHsICCxAAGIAEGLEDGIMBwgIOEAAYgAQYigUYsQMYgwGYAwKIBgGSBwMyLjSgB74SsgcDMC40uAe5A8IHBTAuMi40yAcTgAgB&sclient=gws-wiz-modeless-video"

async def main():
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(wait_until='domcontentloaded', page_timeout=120000, delay_before_return_html=3)
    
    result_urls = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=SEARCH_URL, config=run_config)
            if result and result.html:
                soup = BeautifulSoup(result.html, 'html.parser')
                # Look for all links including google redirects
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    # Handle google redirect /url?q=
                    if '/url?q=' in href:
                        m = re.search(r'/url\?q=([^&]+)', href)
                        if m:
                            href = m.group(1)
                    # Collect http(s) excluding common google domains
                    if href.startswith('http') and not any(href.startswith(d) for d in [
                        'https://www.google.com', 'https://google.com', 'https://accounts.google.com',
                        'https://www.youtube.com'
                    ]):
                        result_urls.append(href)
                # Also look for data-url
                for el in soup.find_all(attrs={'data-url': True}):
                    result_urls.append(el['data-url'])
                # dedup
                seen = set(); uniq = []
                for u in result_urls:
                    if u not in seen:
                        uniq.append(u); seen.add(u)
                result_urls = uniq
            print(f"Found {len(result_urls)} candidates")
            for u in result_urls[:5]: print('  ', u[:100])
        except Exception as e:
            print('ERR', e)
            return
    
    video_urls = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, url in enumerate(result_urls[:15]):
            try:
                res = await crawler.arun(url=url, config=run_config)
                if res and res.html:
                    html = res.html
                    # Look for m3u8/mp4 directly in HTML
                    for m in re.findall(r'(https?://[^\s"\'<>\)]+?\.(?:m3u8|mp4|ts|m3u|webm|mpd|manifest)[^\s"\'<>\)]*)', html):
                        video_urls.append(m)
                    # Look for iframe srcs
                    soup = BeautifulSoup(html, 'html.parser')
                    for ifr in soup.find_all('iframe', src=True):
                        video_urls.append(ifr['src'])
            except Exception:
                pass
            await asyncio.sleep(0.8)
    
    seen=set(); final=[]
    for u in video_urls:
        if u not in seen:
            final.append(u); seen.add(u)
    
    with open('VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for url in final:
            f.write(f'#EXTINF:-1 group-title="RTP",RTP\n{url}\n')
    print(f'Wrote {len(final)} entries to VOD.m3u')
if __name__=='__main__':
    asyncio.run(main())
