import asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from bs4 import BeautifulSoup
import os

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids&biw=1528&bih=732&tbs=qdr%3Ad&sxsrf=APpeQns5pe_IkcCACzvPHgkdmwaASNtHaA%3A1791776213601&ei=1VXMasufJPqj1sQPgM-S8Qo&ved=2ahUKEwiL3unFxrOXAxX6kZUCHYCnJK4Q4dUDegQIBRAM&uact=5&oq=rtp&gs_lp=EhZnd3Mtd2l6LW1vZGVsZXNzLXZpZGVvIgNydHAyChAAGIAEGIoFGEMyCBAAGIAEGLEDMgoQABiABBiKBRhDMgoQABiABBiKBRhDMgUQABiABDIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIFEAAYgAQyBRAAGIAESNkQUPwIWPIOcAN4AJABAJgBb6ABpgOqAQMwLjS4AQPIAQD4AQGYAgagAsQDqAIAwgINEAAYgAQYigUYQxixA8ICBhAAGAcYHsICCxAAGIAEGLEDGIMBwgIOEAAYgAQYigUYsQMYgwGYAwKIBgGSBwMyLjSgB74SsgcDMC40uAe5A8IHBTAuMi40yAcTgAgB&sclient=gws-wiz-modeless-video"

async def main():
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(wait_until='domcontentloaded', page_timeout=60000, delay_before_return_html=2)
    
    result_urls = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=SEARCH_URL, config=run_config)
            if result and result.html:
                soup = BeautifulSoup(result.html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('http') and not href.startswith('https://www.google.com') and not href.startswith('https://www.youtube.com'):
                        result_urls.append(href)
                # dedup
                seen = set(); uniq = []
                for u in result_urls:
                    if u not in seen:
                        uniq.append(u); seen.add(u)
                result_urls = uniq
            print(f"Found {len(result_urls)} candidate links")
        except Exception as e:
            print(e)
    
    video_urls = []
    async with AsyncWebCrawler(config=browser_config) as crawler:
        for i, url in enumerate(result_urls[:10]):
            try:
                res = await crawler.arun(url=url, config=run_config)
                if res and res.html:
                    soup = BeautifulSoup(res.html, 'html.parser')
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if any(k in href for k in ['.m3u8', 'm3u8', 'mp4', 'manifest']):
                            video_urls.append(href)
                    for v in soup.find_all('video'):
                        if v.get('src'): video_urls.append(v['src'])
                        for s in v.find_all('source'): 
                            if s.get('src'): video_urls.append(s['src'])
            except Exception:
                pass
            await asyncio.sleep(0.5)
    
    # dedup
    seen=set(); final=[]
    for u in video_urls:
        if u not in seen:
            final.append(u); seen.add(u)
    
    with open('VOD.m3u', 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for url in final:
            f.write(f'#EXTINF:-1 group-title="RTP",RTP\n{url}\n')
    print(f"Wrote {len(final)} entries to VOD.m3u")
if __name__=='__main__':
    asyncio.run(main())
