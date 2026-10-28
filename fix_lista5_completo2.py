#!/usr/bin/env python3
import re
import os
import sys

with open('lista5.m3u', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

lines = content.splitlines()
if lines and lines[0].strip().startswith('#EXTM3U'):
    i = 1
else:
    i = 0

entries = []
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
            if nextline.startswith('http') or nextline.startswith('rtmp') or nextline.startswith('rtsp'):
                urls.append(nextline)
            i += 1
        if urls and extinf:
            entries.append({'extinf': extinf, 'urls': urls})
    else:
        i += 1

print(f"Found {len(entries)} entries")

# Use local EPG files if available
epg_sources = [
    "file:///home/runner/work/JCTV/JCTV/EPGFULL.xml.gz",
    "file:///home/runner/work/JCTV/JCTV/EPGNEWS.xml",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
]

fixed_entries = []
for entry in entries:
    extinf = entry['extinf']
    urls = entry['urls']
    
    name = extinf.split(',')[-1].strip()
    group_m = re.search(r'group-title="([^"]+)"', extinf)
    group = group_m.group(1) if group_m else 'NEWS WORLD'
    
    name_lower = name.lower()
    tvg_id = ''
    if 'abc news' in name_lower and 'live' in name_lower:
        tvg_id = 'ABCNewsLive.us'
    elif 'abc news' in name_lower:
        tvg_id = 'ABC.News.Live.us2'  # try local EPG id
    elif 'fox news' in name_lower and 'business' not in name_lower:
        tvg_id = 'Fox.News.Channel.HD.us2'
    elif 'fox business' in name_lower:
        tvg_id = 'Fox.Business.HD.us2'
    elif 'cbs news' in name_lower:
        tvg_id = 'CBS.News.National.Stream.us2'
    
    # logo
    logo = ''
    logo_m = re.search(r'tvg-logo="([^"]+)"', extinf)
    if logo_m:
        logo_url = logo_m.group(1)
        if 'imgur.com' not in logo_url.lower():
            if logo_url.lower().endswith('.jpeg'):
                logo_url = logo_url[:-5] + '.jpg'
            elif not logo_url.lower().endswith('.jpg'):
                if logo_url.lower().endswith('.png') or logo_url.lower().endswith('.gif') or logo_url.lower().endswith('.webp'):
                    logo_url = logo_url.rsplit('.', 1)[0] + '.jpg'
                elif '?' in logo_url:
                    parts = logo_url.split('?')
                    logo_url = parts[0] + '.jpg?' + parts[1]
                else:
                    logo_url = logo_url + '.jpg'
            logo = logo_url
    
    if not logo or 'imgur' in str(logo).lower() or not str(logo).lower().endswith('.jpg'):
        if 'abc news' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/abc-news-us.jpg'
        elif 'fox news' in name_lower and 'business' not in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-news-us.jpg'
        elif 'fox business' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-business-us.jpg'
        elif 'cbs news' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cbs-news-us.jpg'
    
    parts = ['#EXTINF:-1']
    if tvg_id:
        parts.append(f'tvg-id="{tvg_id}"')
    if logo and str(logo).lower().endswith('.jpg') and 'imgur' not in str(logo).lower():
        parts.append(f'tvg-logo="{logo}"')
    parts.append(f'group-title="{group}"')
    new_extinf = ' '.join(parts) + f',{name}'
    
    fixed_entries.append({
        'extinf': new_extinf,
        'urls': urls
    })

new_header = f'#EXTM3U url-tvg="{",".join(epg_sources)}"'
output = [new_header]
for entry in fixed_entries:
    output.append(entry['extinf'])
    for url in entry['urls']:
        output.append(url)

with open('lista5.m3u', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output) + '\n')

print(f"Updated")
