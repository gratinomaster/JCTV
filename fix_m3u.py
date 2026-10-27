#!/usr/bin/env python3
import re
import json
from pathlib import Path

# Read the original file
with open('lista5.m3u', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Split into entries (EXTINF + following URL)
lines = content.splitlines()
entries = []
i = 0
if lines and lines[0].strip().startswith('#EXTM3U'):
    header = lines[0].strip()
    i = 1
else:
    header = '#EXTM3U'
    i = 0

# Collect all entries
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

# Common US news EPG sources
epg_sources = [
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_LOCALS1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US_SPORTS1.xml.gz",
]

# Function to extract attributes from EXTINF
def parse_extinf(extinf):
    attrs = {}
    # Extract tvg-logo
    m = re.search(r'tvg-logo="([^"]+)"', extinf)
    if m:
        attrs['logo'] = m.group(1)
    # Extract group-title
    m = re.search(r'group-title="([^"]+)"', extinf)
    if m:
        attrs['group'] = m.group(1)
    # Extract name after comma
    if ',' in extinf:
        attrs['name'] = extinf.split(',')[-1].strip()
    return attrs

# Process each entry
fixed_entries = []
for idx, entry in enumerate(entries):
    extinf = entry['extinf']
    urls = entry['urls']
    attrs = parse_extinf(extinf)
    
    # Skip imgur logos - we need to replace them or ensure they're jpg
    logo = attrs.get('logo', '')
    
    # Check if logo needs fixing
    if logo and 'imgur.com' in logo:
        # Try to find alternative logo or use placeholder
        logo = ''  # Will try to assign better logo
    
    # Ensure logo is .jpg if exists and not already jpg/jpeg
    if logo:
        if not (logo.lower().endswith('.jpg') or logo.lower().endswith('.jpeg')):
            # Try to convert common extensions to jpg or add parameter
            # For now, we'll keep as is but mark for replacement if needed
            pass
    
    # Build new EXTINF
    # Ensure tvg-id exists for EPG
    name_clean = attrs.get('name', '').strip()
    
    # Assign tvg-ids based on channel names
    tvg_id = None
    if 'ABC News' in name_clean:
        tvg_id = 'ABCNewsLive.us'
    elif 'Fox News' in name_clean and 'Business' not in name_clean:
        tvg_id = 'FoxNews.us'
    elif 'Fox Business' in name_clean:
        tvg_id = 'FoxBusiness.us'
    elif 'CBS News' in name_clean:
        tvg_id = 'CBSNews.us'
    
    # Rebuild EXTINF
    new_extinf_parts = ['#EXTINF:-1']
    if tvg_id:
        new_extinf_parts.append(f'tvg-id="{tvg_id}"')
    
    # Add EPG URL to header would be better, but need to add tvg-url
    # For individual channel, can add tvg-shift if needed
    
    if logo and '.jpg' in logo.lower() and 'imgur' not in logo.lower():
        new_extinf_parts.append(f'tvg-logo="{logo}"')
    elif logo and '.jpeg' in logo.lower() and 'imgur' not in logo.lower():
        # Change jpeg to jpg in URL if simple
        logo_fixed = logo.replace('.jpeg', '.jpg').replace('.JPEG', '.JPG')
        new_extinf_parts.append(f'tvg-logo="{logo_fixed}"')
    else:
        # Try to assign default logos based on channel
        if 'ABC News' in name_clean:
            new_extinf_parts.append('tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/abc-news-live-hz-us.jpg"')
        elif 'Fox News' in name_clean and 'Business' not in name_clean:
            new_extinf_parts.append('tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-news-us.jpg"')
        elif 'Fox Business' in name_clean:
            new_extinf_parts.append('tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/fox-business-us.jpg"')
        elif 'CBS News' in name_clean:
            new_extinf_parts.append('tvg-logo="https://raw.githubusercontent.com/tv-logo/tv-logos/main/countries/united-states/cbs-news-us.jpg"')
    
    if attrs.get('group'):
        new_extinf_parts.append(f'group-title="{attrs["group"]}"')
    else:
        new_extinf_parts.append('group-title="NEWS WORLD"')
    
    new_extinf_parts.append(f',{name_clean}')
    new_extinf = ' '.join(new_extinf_parts)
    
    fixed_entries.append({
        'extinf': new_extinf,
        'urls': urls
    })

# Build new header with EPG URLs
new_header = f'#EXTM3U x-tvg-url="{",".join(epg_sources)}"'
# Write the fixed file
output_lines = [new_header]
for entry in fixed_entries:
    output_lines.append(entry['extinf'])
    for url in entry['urls']:
        output_lines.append(url)

with open('lista5_fixed.m3u', 'w', encoding='utf-8') as f:
    f.write('\n'.join(output_lines) + '\n')

print(f"Wrote {len(fixed_entries)} entries to lista5_fixed.m3u")
