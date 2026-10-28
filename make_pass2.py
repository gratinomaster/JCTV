#!/usr/bin/env python3
import re

with open('lista5.m3u', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

lines = content.splitlines()
i = 0
entries = []
if lines and lines[0].strip().startswith('#EXTM3U'):
    i = 1
else:
    i = 0

while i < len(lines):
    line = lines[i].strip()
    if not line:
        i += 1
        continue
    if line.startswith('#EXTINF'):
        extinf = line
        i += 1
        urls = []
        while i < len(lines):
            nextline = lines[i].strip()
            if not nextline:
                i += 1
                continue
            if nextline.startswith('#EXTINF') or nextline.startswith('#EXTM3U'):
                break
            if nextline.startswith('http'):
                urls.append(nextline)
            i += 1
        if urls and extinf:
            entries.append({'extinf': extinf, 'urls': urls})
    else:
        i += 1

# Keep only ABC News Live Prime with good logo and good tvg-id
good_entries = []
for entry in entries:
    extinf = entry['extinf']
    urls = entry['urls']
    name = extinf.split(',')[-1].strip()
    name_lower = name.lower()
    if 'abc news live prime' in name_lower:
        # Use original logo that works
        logo = 'https://s.abcnews.com/images/Live/abc_news_live-abc-ml-250210_1739199021469_hpMain_16x9_608.jpg'
        # Try different tvg-ids - maybe ABCNewsLive.us from the public EPGs?
        tvg_id = 'ABCNewsLive.us'
        group = 'NEWS WORLD'
        new_extinf = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}'
        good_entries.append({'extinf': new_extinf, 'urls': [urls[0]]})  # just first URL
        break  # only 1 entry to test

epg_sources = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
]

new_header = f'#EXTM3U url-tvg="{",".join(epg_sources)}"'
output = [new_header]
for entry in good_entries:
    output.append(entry['extinf'])
    for url in entry['urls']:
        output.append(url)

with open('lista5.m3u', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output) + '\n')

print(f"Kept {len(good_entries)}")
