#!/usr/bin/env python3
import os
import re
import sys

M3U_PATH = '/home/runner/work/JCTV/JCTV/lista5.m3u'
OUT_PATH = '/home/runner/work/JCTV/JCTV/lista5_fixed.m3u'

def fix_logo_url(logo):
    if not logo:
        return logo
    # Ensure .jpg - replace common extensions to .jpg if not ending with .jpg/.jpeg? prefer .jpg
    if logo.lower().endswith(('.jpg', '.jpeg')):
        # normalize jpeg to jpg
        if logo.lower().endswith('.jpeg'):
            logo = logo[:-5] + '.jpg'
        return logo
    # if ends with png/webp etc, try to convert to jpg by replacing extension? but better to find jpg version
    # common pattern - just replace last extension
    m = re.search(r'^(.*)\.(png|webp|gif)$', logo, re.I)
    if m:
        return m.group(1) + '.jpg'
    # if imgur and no extension, often .jpg works? but leave as-is and note - but user wants .jpg
    return logo

def main():
    with open(M3U_PATH, encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Extract channel blocks: EXTINF followed by URLs (non-empty, not starting with #)
    lines = content.splitlines(True)
    
    # Rebuild clean structure - keep only primary URL per EXTINF group
    result = []
    i = 0
    result.append('#EXTM3U\n')
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF'):
            extinf = line
            # extract logo
            logo_m = re.search(r'tvg-logo="([^"]+)"', extinf)
            if logo_m:
                new_logo = fix_logo_url(logo_m.group(1))
                if new_logo != logo_m.group(1):
                    extinf = extinf.replace(logo_m.group(0), f'tvg-logo="{new_logo}"')
            # find first URL after
            j = i + 1
            primary_url = None
            while j < len(lines):
                l = lines[j]
                if l.startswith('#EXTINF'):
                    break
                ls = l.strip()
                if ls and not ls.startswith('#'):
                    primary_url = ls
                    j += 1  # move past this URL
                    break  # take first URL as primary
                j += 1
            if primary_url:
                result.append(extinf)
                result.append(primary_url + '\n')
            i = j
            continue
        i += 1
    
    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.writelines(result)
    print('done', len(result))

if __name__ == '__main__':
    main()
