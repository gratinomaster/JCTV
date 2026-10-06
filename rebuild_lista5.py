#!/usr/bin/env python3
import re
from collections import defaultdict

M3U_PATH = '/home/runner/work/JCTV/JCTV/lista5_fixed.m3u'
OUT_PATH = '/home/runner/work/JCTV/JCTV/lista5.m3u'

# EPG mapping from EPGNEWS
EPG_MAP = {
    'good morning america first look | watch live news on abcnl': 'ABC.News.Live.us2',
    'video the heat wave hitting the west and the rainy week ahead for florida | watch live news on abcnl': 'ABC.News.Live.us2',
    'watch fox news channel online | stream fox news': 'Fox.News.Channel.HD.us2',
    'fox business go | fox news video': 'Fox.Business.HD.us2',
    'watch cbs news 24/7, our free live news stream': 'CBS.News.National.Stream.us2',
}

# Prefer specific good URLs
PREFER = [
    'master.m3u8',
]

def is_suspicious(url):
    # basic antivirus heuristic - block obvious bad patterns if any
    bad = ['bit.ly', 'shorturl', 'exe', '.zip', 'phishing', 'malware']
    url_l = url.lower()
    # allow http(s) m3u8
    if not (url_l.startswith('http://') or url_l.startswith('https://')):
        return True
    # block if contains bad terms
    for b in bad:
        if b in url_l:
            return True
    return False

def pick_primary(urls):
    # filter out suspicious
    urls = [u for u in urls if not is_suspicious(u)]
    if not urls:
        return None
    # prefer master or higher quality? pick first non-audio small variant? prefer master.m3u8
    for u in urls:
        if 'master.m3u8' in u:
            return u
    # else prefer longer/better
    # sort by length desc maybe
    return urls[0]

def main():
    with open(M3U_PATH, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    groups = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF'):
            extinf = line
            title = extinf.split(',', 1)[1].strip() if ',' in extinf else ''
            j = i + 1
            urls = []
            while j < len(lines):
                l = lines[j]
                if l.startswith('#EXTINF'):
                    break
                ls = l.strip()
                if ls and not ls.startswith('#'):
                    urls.append(ls)
                j += 1
            groups.append((extinf, title, urls))
            i = j
            continue
        i += 1

    bytitle = defaultdict(list)
    for extinf, title, urls in groups:
        key = re.sub(r'\s+', ' ', title).strip().lower()
        bytitle[key].append((extinf, urls))

    # build output
    out = []
    out.append('#EXTM3U x-tvg-url="EPGNEWS.xml.gz"\n')
    # define clean channels in order
    channel_order = [
        'good morning america first look | watch live news on abcnl',
        'watch fox news channel online | stream fox news',
        'fox business go | fox news video',
        'watch cbs news 24/7, our free live news stream',
    ]
    for cname in channel_order:
        key = re.sub(r'\s+', ' ', cname).strip().lower()
        items = bytitle.get(key, [])
        if not items:
            continue
        # merge all urls
        all_urls = []
        for extinf, urls in items:
            all_urls.extend(urls)
        primary = pick_primary(all_urls)
        if not primary:
            continue
        # build extinf with tvg-id
        base_extinf = items[0][0]  # original
        # ensure tvg-logo .jpg
        mlogo = re.search(r'tvg-logo="([^"]+)"', base_extinf)
        if mlogo:
            logo = mlogo.group(1)
            if not logo.lower().endswith(('.jpg', '.jpeg')):
                logo = logo.rsplit('.', 1)[0] + '.jpg' if '.' in logo else logo + '.jpg'
            base_extinf = base_extinf.replace(mlogo.group(0), f'tvg-logo="{logo}"')
        # add tvg-id
        tvgid = EPG_MAP.get(key, '')
        if tvgid and 'tvg-id' not in base_extinf:
            # insert tvg-id after #EXTINF:-1
            base_extinf = base_extinf.replace('#EXTINF:-1', f'#EXTINF:-1 tvg-id="{tvgid}"', 1)
        elif tvgid:
            base_extinf = re.sub(r'tvg-id="[^"]*"', f'tvg-id="{tvgid}"', base_extinf)
        out.append(base_extinf)
        out.append(primary + '\n')

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.writelines(out)

    print(len(out)-1)  # count entries

if __name__ == '__main__':
    main()
