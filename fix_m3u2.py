#!/usr/bin/env python3
import re

with open('lista5.m3u', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

lines = content.splitlines()
entries = []
i = 0
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
            if nextline.startswith('http') or nextline.startswith('rtmp') or nextline.startswith('rtsp'):
                urls.append(nextline)
            i += 1
        if urls:
            entries.append({
                'extinf': extinf,
                'urls': urls
            })
    else:
        i += 1

print(f"Found {len(entries)} entries")

epg_sources = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
]

# For each entry, fix it
fixed = []
for entry in entries:
    extinf = entry['extinf']
    urls = entry['urls']
    
    # Extract name
    name = extinf.split(',')[-1].strip()
    
    # Determine tvg-id
    tvg_id = ''
    if 'ABC News' in name and 'Live' in name:
        tvg_id = 'ABCNewsLive.us'
    elif 'ABC News' in name:
        tvg_id = 'ABCNews.us'
    elif 'Fox News' in name and 'Business' not in name:
        tvg_id = 'FoxNews.us'
    elif 'Fox Business' in name:
        tvg_id = 'FoxBusiness.us'
    elif 'CBS News' in name:
        tvg_id = 'CBSNews.us'
    
    # Get group
    group_m = re.search(r'group-title="([^"]+)"', extinf)
    group = group_m.group(1) if group_m else 'NEWS WORLD'
    
    # Handle logos
    logo = ''
    logo_m = re.search(r'tvg-logo="([^"]+)"', extinf)
    if logo_m:
        logo_url = logo_m.group(1)
        if 'imgur.com' not in logo_url:
            if logo_url.lower().endswith(('.jpg', '.jpeg')):
                if logo_url.lower().endswith('.jpeg'):
                    logo_url = logo_url[:-5] + '.jpg'
                logo = logo_url
    
    # Add default logos if missing or was imgur
    if not logo:
        if 'ABC News' in name:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/abc-news-us.jpg'
        elif 'Fox News' in name and 'Business' not in name:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-news-us.jpg'
        elif 'Fox Business' in name:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-business-us.jpg'
        elif 'CBS News' in name:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cbs-news-us.jpg'
    
    # Build new EXTINF - ensure no space before comma
    parts = ['#EXTINF:-1']
    if tvg_id:
        parts.append(f'tvg-id="{tvg_id}"')
    if logo and logo.lower().endswith('.jpg') and 'imgur' not in logo.lower():
        parts.append(f'tvg-logo="{logo}"')
    parts.append(f'group-title="{group}"')
    new_extinf = ' '.join(parts) + f',{name}'
    
    fixed.append({
        'extinf': new_extinf,
        'urls': urls
    })

# Write
new_header = f'#EXTM3U x-tvg-url="{",".join(epg_sources)}"'
output = [new_header]
for entry in fixed:
    output.append(entry['extinf'])
    for url in entry['urls']:
        output.append(url)

with open('lista5.m3u', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output) + '\n')

print(f"Updated lista5.m3u with {len(fixed)} entries")
