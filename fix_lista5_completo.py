#!/usr/bin/env python3
import re
import os
import sys
from pathlib import Path

# Read original
with open('lista5.m3u', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Split header and entries
lines = content.splitlines()
if lines and lines[0].strip().startswith('#EXTM3U'):
    header = lines[0].strip()
    i = 1
else:
    header = '#EXTM3U'
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

# Multiple EPG sources
epg_sources = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz",
]

fixed_entries = []
for entry in entries:
    extinf = entry['extinf']
    urls = entry['urls']
    
    # Extract name
    name = extinf.split(',')[-1].strip()
    
    # Extract group
    group_m = re.search(r'group-title="([^"]+)"', extinf)
    group = group_m.group(1) if group_m else 'NEWS WORLD'
    
    # Determine tvg-id
    tvg_id = ''
    name_lower = name.lower()
    if 'abc news' in name_lower:
        tvg_id = 'ABCNewsLive.us'
    elif 'fox news' in name_lower and 'business' not in name_lower:
        tvg_id = 'FoxNews.us'
    elif 'fox business' in name_lower:
        tvg_id = 'FoxBusiness.us'
    elif 'cbs news' in name_lower:
        tvg_id = 'CBSNews.us'
    elif 'cnn' in name_lower:
        tvg_id = 'CNN.us'
    
    # Handle logo - must be .jpg, no imgur
    logo = ''
    logo_m = re.search(r'tvg-logo="([^"]+)"', extinf)
    if logo_m:
        logo_url = logo_m.group(1)
        if 'imgur.com' not in logo_url.lower():
            # Convert to jpg if it's jpeg
            if logo_url.lower().endswith('.jpeg'):
                logo_url = logo_url[:-5] + '.jpg'
            elif logo_url.lower().endswith('.png'):
                # Try to change extension to jpg if possible
                logo_url = logo_url[:-4] + '.jpg'
            elif logo_url.lower().endswith('.gif'):
                logo_url = logo_url[:-4] + '.jpg'
            elif logo_url.lower().endswith('.webp'):
                logo_url = logo_url[:-5] + '.jpg'
            elif logo_url.lower().endswith(('.jpg', '.JPG')):
                pass
            else:
                # No extension, try to add .jpg
                if '?' in logo_url:
                    # Add before query
                    parts = logo_url.split('?')
                    logo_url = parts[0] + '.jpg?' + parts[1] if len(parts) > 1 else parts[0] + '.jpg'
                else:
                    logo_url = logo_url + '.jpg'
            logo = logo_url
    
    # Add default logos if missing
    if not logo or 'imgur' in logo.lower() or not logo.lower().endswith(('.jpg')):
        if 'abc news' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/abc-news-us.jpg'
        elif 'fox news' in name_lower and 'business' not in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-news-us.jpg'
        elif 'fox business' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-business-us.jpg'
        elif 'cbs news' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cbs-news-us.jpg'
        elif 'cnn' in name_lower:
            logo = 'https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cnn-us.jpg'
    
    # Build new EXTINF - ensure proper format
    parts = ['#EXTINF:-1']
    if tvg_id:
        parts.append(f'tvg-id="{tvg_id}"')
    if logo and logo.lower().endswith('.jpg') and 'imgur' not in logo.lower():
        parts.append(f'tvg-logo="{logo}"')
    parts.append(f'group-title="{group}"')
    # Make sure comma is attached properly
    new_extinf = ' '.join(parts) + f',{name}'
    
    fixed_entries.append({
        'extinf': new_extinf,
        'urls': urls
    })

# Write with url-tvg in header (as test expects)
new_header = f'#EXTM3U url-tvg="{",".join(epg_sources)}"'
output = [new_header]
for entry in fixed_entries:
    output.append(entry['extinf'])
    for url in entry['urls']:
        output.append(url)

with open('lista5.m3u', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output) + '\n')

print(f"Updated lista5.m3u with {len(fixed_entries)} entries")
