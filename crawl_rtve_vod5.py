#!/usr/bin/env python3
import asyncio
import html as html_lib
import json
import re
import ssl
import urllib.request
from urllib.parse import urljoin, urlparse

from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

START_URL = "https://www.rtve.es/"
OUT_FILE = "/home/runner/work/JCTV/JCTV/VOD.m3u"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

BASE64_ALPHABET = ('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                   '0123456789+/=')


class Base64Reader:
    def __init__(self, b64):
        self.base64 = b64
        self.position = 0
        self.bits = 0
        self.bitsLength = 0

    def readByte(self):
        if self.bitsLength == 0:
            tailBits = 0
            while self.position < len(self.base64) and self.bitsLength < 24:
                ch = self.base64[self.position]
                self.position += 1
                if ch > ' ':
                    index = BASE64_ALPHABET.find(ch)
                    if index < 0:
                        raise ValueError('Invalid character')
                    if index < 64:
                        if tailBits > 0:
                            raise ValueError('Invalid encoding (padding)')
                        self.bits = (self.bits << 6) | index
                    else:
                        if self.bitsLength < 8:
                            raise ValueError('Invalid encoding (extra)')
                        self.bits <<= 6
                        tailBits += 6
                    self.bitsLength += 6
            if self.position >= len(self.base64):
                if self.bitsLength == 0:
                    return -1
                if self.bitsLength < 24:
                    raise ValueError('Invalid encoding (end)')
            if tailBits == 6:
                tailBits = 8
            elif tailBits == 12:
                tailBits = 16
            self.bits >>= tailBits
            self.bitsLength -= tailBits
        self.bitsLength -= 8
        return (self.bits >> self.bitsLength) & 0xFF

    def read(self, count):
        out = []
        for _ in range(count):
            b = self.readByte()
            if b == -1:
                return out
            out.append(b)
        return out

    def readChars(self, n):
        txt = ''
        for _ in range(n):
            b = self.readByte()
            if b == -1:
                return txt
            txt += chr(b)
        return txt

    def skip(self, n):
        for _ in range(n):
            self.readByte()

    def readInt(self):
        b = self.read(4)
        if len(b) != 4:
            raise ValueError('Out of bounds')
        return (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]


def _read_chunk(reader):
    length = reader.readInt()
    ctype = reader.readChars(4)
    data = reader.read(length)
    reader.skip(4)
    return ctype, data


def _get_alfabet(texto):
    a = ''
    j = 0
    k = 0
    for ch in texto:
        if k == 0:
            a += ch
            j = (j + 1) % 4
            k = j
        else:
            k -= 1
    return a


def _get_url(texto, alfabeto):
    a = ''
    j = 0
    k = 3
    cont = 1
    n = 0
    for ch in texto:
        if j == 0:
            n = int(ch) * 10
            j = 1
        else:
            if k == 0:
                n += int(ch)
                a += alfabeto[n]
                k = (cont + 3) % 4
                j = 0
                cont += 1
            else:
                k -= 1
    return a


def _get_source(item):
    a = item.index('#')
    alfabeto = _get_alfabet(item[:a])
    miurl = item[a + 1:]
    return _get_url(miurl, alfabeto)


def translate(img):
    reader = Base64Reader(img)
    reader.skip(8)
    ctype, data = _read_chunk(reader)
    sources = []
    while ctype != 'IEND':
        if ctype == 'tEXt':
            a = ''.join(chr(x) for x in data if x != 0)
            if '%%' in a:
                a = a.split('#')[0] + '#' + a.split('#')[1].split('%%')[1]
            sources.append(_get_source(a))
        ctype, data = _read_chunk(reader)
    return sources


def resolve_stream(idasset):
    url = ("https://ztnr.rtve.es/ztnr/movil/thumbnail/rtveplayw/videos/"
           f"{idasset}.png?q=v2")
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.rtve.es/",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, context=SSL_CTX, timeout=25) as resp:
        img = resp.read().decode('ascii', errors='ignore')
    sources = translate(img)
    for s in sources:
        if '.m3u8' in s and 'rnevodstream' not in s:
            return s
    return None


def clean_title(raw, fallback):
    if not raw:
        return fallback
    t = re.sub(r'\s*\|\s*RTVE.*$', '', raw)
    t = re.sub(r'\s+', ' ', t).strip()
    return t or fallback


def extract_idasset(page_url, html):
    for m in re.finditer(r'data-config=["\']([^"\']+)["\']', html):
        cfg = html_lib.unescape(m.group(1))
        try:
            d = json.loads(cfg)
        except Exception:
            continue
        if isinstance(d, dict) and d.get('type') == 'video' and d.get('id'):
            return str(d['id'])
    for m in re.finditer(r'data-config=["\']([^"\']+)["\']', html):
        cfg = html_lib.unescape(m.group(1))
        try:
            d = json.loads(cfg)
        except Exception:
            continue
        if isinstance(d, dict) and d.get('idAsset'):
            return str(d['idAsset'])
    m = re.search(r'/play/videos/[^/]+/[^/]+/(\d+)/?(?:[?#].*)?$', page_url)
    if m:
        return m.group(1)
    m = re.search(r'/play/videos/[^/]+/(\d+)/?(?:[?#].*)?$', page_url)
    if m:
        return m.group(1)
    m = re.search(r'/play/videos/[^/]+/[^/]+/[^/]+/(\d+)/?(?:[?#].*)?$',
                  page_url)
    if m:
        return m.group(1)
    if '/play/' in page_url:
        m = re.search(r'/(\d{6,})/?(?:[?#].*)?$', page_url)
        if m:
            return m.group(1)
    return None


def is_video_page(url):
    if any(k in url for k in ('/directo', '/radio', '/play/radio',
                              '/play/directo', '/autor/')):
        return False
    if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|xml|json|pdf|mp4|'
                 r'm3u8|mpd|ico|woff2?|ttf|zip|gz|txt|rss)([?#]|$)',
                 url, re.I):
        return False
    if '/play/videos/' in url:
        return True
    if re.search(r'\.shtml$', url):
        return True
    if '/play/' in url and re.search(r'/\d{6,}/?$', url):
        return True
    if '/noticias/' in url and re.search(r'/\d{6,}/?$', url):
        return True
    return False


def is_page_url(url):
    if any(k in url for k in ('/directo', '/radio', '/play/radio',
                              '/play/directo', '/autor/')):
        return False
    if re.search(r'\.(jpg|jpeg|png|gif|svg|webp|css|js|xml|json|pdf|mp4|'
                 r'm3u8|mpd|ico|woff2?|ttf|zip|gz|txt|rss)([?#]|$)',
                 url, re.I):
        return False
    if '/play/videos/' in url:
        return True
    if '/play/noticias/' in url:
        return True
    if re.search(r'/\d{6,}/?$', url):
        return True
    if re.search(r'/\d{6,}\.shtml$', url):
        return True
    if '/play/' in url:
        return True
    return False


async def main():
    browser_cfg = BrowserConfig(headless=True, verbose=False)
    run_cfg = CrawlerRunConfig(
        delay_before_return_html=1.0,
        wait_for_images=False,
        remove_overlay_elements=True,
        wait_until="domcontentloaded",
        page_timeout=30000,
    )

    links = []
    seen = set()
    home_html = ""

    def harvest(base_url, page_html, video_only=False):
        found = set()
        for m in re.findall(r'href=["\']([^"\']+)["\']', page_html):
            link = m
            if link.startswith('//'):
                link = 'https:' + link
            if not link.startswith('http'):
                link = urljoin(base_url, link)
            p = urlparse(link)
            if 'rtve.es' in p.netloc:
                link = link.split('#')[0]
                if video_only:
                    if is_video_page(link):
                        found.add(link)
                elif is_page_url(link):
                    found.add(link)
        return found

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        res = await crawler.arun(url=START_URL, config=run_cfg)
        if res.success:
            home_html = res.html or ""
            for link in sorted(harvest(START_URL, home_html)):
                if link not in seen:
                    seen.add(link)
                    links.append(link)

    print(f"Links encontrados na home: {len(links)}")

    sem = asyncio.Semaphore(12)
    streams = []
    streams_seen = set()
    id_done = set()

    async def process(crawler, url):
        async with sem:
            try:
                r = await crawler.arun(url=url, config=run_cfg)
            except Exception:
                return set()
            if not r.success or not r.html:
                return set()
            idasset = extract_idasset(url, r.html)
            if idasset and idasset not in id_done:
                id_done.add(idasset)
                tm = re.search(r'<title>([^<]+)</title>', r.html, re.I)
                title = tm.group(1) if tm else None
                try:
                    stream = await asyncio.to_thread(resolve_stream, idasset)
                except Exception:
                    stream = None
                if stream and stream not in streams_seen:
                    streams_seen.add(stream)
                    t = clean_title(title, f"RTVE {idasset}")
                    streams.append((t, stream))
                    print(f"[OK] {t} -> {stream[:90]}")
            return harvest(url, r.html, video_only=True)

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        home_results = await asyncio.gather(
            *(process(crawler, u) for u in links))

        discovered = set()
        for s in home_results:
            discovered |= s
        extra = [u for u in sorted(discovered) if u not in seen]
        extra.sort(key=lambda u: (0 if '/play/videos/' in u else 1, u))
        extra = extra[:400]
        for u in extra:
            seen.add(u)
        print(f"Links descobertos no 2o nivel: {len(extra)}")

        await asyncio.gather(*(process(crawler, u) for u in extra))

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for title, url in streams:
            f.write(f'#EXTINF:-1 group-title="VOD" tvg-logo="",{title}\n')
            f.write(f'{url}\n')

    print(f"Gravados {len(streams)} canais VOD em {OUT_FILE}")


if __name__ == '__main__':
    asyncio.run(main())
