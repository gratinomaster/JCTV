#!/usr/bin/env python3
import requests
import re
import json

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.rtve.es/'
})

# Known RTVE live streams
streams = [
    ("La 1", "https://ztnr.rtve.es/ztnr/res/La1_Nacional.m3u8"),
    ("La 2", "https://ztnr.rtve.es/ztnr/res/La2_Nacional.m3u8"),
    ("24h", "https://ztnr.rtve.es/ztnr/res/24H.m3u8"),
    ("Teledeporte", "https://ztnr.rtve.es/ztnr/res/TDP_TELEDEPORTE.m3u8"),
    ("Clan", "https://ztnr.rtve.es/ztnr/res/CLAN.m3u8"),
    ("La 1 Catalunya", "https://ztnr.rtve.es/ztnr/res/La1_CAT.m3u8"),
]

with open('VOD.m3u', 'w', encoding='utf-8') as f:
    f.write('#EXTM3U\n')
    for name, url in streams:
        f.write(f'#EXTINF:-1 group-title="VOD",{name}\n')
        f.write(f'{url}\n')

print(f'Wrote {len(streams)} entries')
