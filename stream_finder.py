import re
import asyncio
import logging
import sys

logging.basicConfig(level=logging.CRITICAL, format="", handlers=[logging.StreamHandler(sys.stdout)])
for logger_name in ["crawl4ai", "playwright", "asyncio"]:
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

SITES = [
    ("https://cbn.globo.com/ao-vivo/video/cbn-sp/", "CBN SP", "https://static.wikia.nocookie.net/logopedia/images/4/49/CBN.png"),
    ("https://g1.globo.com/sp/ribeirao-preto-franca/ao-vivo/eptv1.ghtml", "EPTV1 Ribeirao", "https://static.wikia.nocookie.net/logopedia/images/8/86/EPTV.png"),
    ("https://g1.globo.com/sp/campinas-regiao/ao-vivo/veja-o-eptv-2-campinas-ao-vivo.ghtml", "EPTV2 Campinas", "https://static.wikia.nocookie.net/logopedia/images/8/86/EPTV.png"),
    ("https://g1.globo.com/sp/piracicaba-regiao/ao-vivo/eptv-2-piracicaba-ao-vivo.ghtml", "EPTV2 Piracicaba", "https://static.wikia.nocookie.net/logopedia/images/8/86/EPTV.png"),
    ("https://g1.globo.com/sp/ribeirao-preto-franca/ao-vivo/eptv-2-ribeirao-e-franca-ao-vivo.ghtml", "EPTV2 Ribeirao/Franca", "https://static.wikia.nocookie.net/logopedia/images/8/86/EPTV.png"),
]

async def find_m3u8_stream(url: str) -> str | None:
    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        extra_args=["--disable-gpu", "--no-sandbox"],
    )
    run_config = CrawlerRunConfig(
        delay_before_return_html=10,
        capture_network_requests=True,
    )
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=run_config)
        
        if result and result.network_requests:
            for req in result.network_requests:
                req_url = req.get("url", "")
                req_url_lower = req_url.lower()
                if "playlist.m3u8" in req_url_lower or req_url_lower.endswith(".m3u8"):
                    return req_url
        
        if result and result.html:
            matches = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', result.html)
            if matches:
                return matches[0]
                
            video_ids = re.findall(r'globo\.com/(?:v|ao-vivo)/(\d+)', result.html)
            if video_ids:
                return f"https://globoplay.globo.com/v/{video_ids[0]}/"
                
    return None

async def main():
    playlist = ["#EXTM3U"]
    
    for url, name, logo in SITES:
        print(f"Buscando stream em: {url}")
        m3u8_url = await find_m3u8_stream(url)
        if m3u8_url:
            print(f"  -> Encontrado: {m3u8_url[:80]}...")
            playlist.append(f'#EXTINF:-1 tvg-logo="{logo}" group-title="NEWS WORLD",{name}')
            playlist.append(m3u8_url)
        else:
            print(f"  -> Stream não encontrado")
    
    with open("lista3.m3u", "w", encoding="utf-8") as f:
        f.write("\n".join(playlist))
    
    print("\nArquivo lista3.m3u gerado com sucesso!")

if __name__ == "__main__":
    asyncio.run(main())
