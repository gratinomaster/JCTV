import gzip
import re
import sys
from collections import defaultdict

m3u_path = '/home/runner/work/JCTV/JCTV/NEWSWORLDNOVOS.m3u'
epg_in = '/home/runner/work/JCTV/JCTV/EPGFULL.xml.gz'
epg_out = '/home/runner/work/JCTV/JCTV/EPGFULL.xml.gz'

# Extract tvg-id from M3U
tvg_ids = set()
try:
    with open(m3u_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('#EXTINF'):
                continue
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m:
                tvg_ids.add(m.group(1).strip())
            else:
                # try single quotes
                m = re.search(r"tvg-id='([^']+)'", line)
                if m:
                    tvg_ids.add(m.group(1).strip())
except Exception as e:
    print(f'ERROR reading m3u: {e}', file=sys.stderr)
    sys.exit(1)

print(f'M3U tvg-id count: {len(tvg_ids)}')
# Read EPG and filter
# We'll do a streaming parse approach is heavy; simple regex split by <channel> blocks? Or just track channel ids
channels_out = []
programmes_out = []

with gzip.open(epg_in, 'rt', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Extract header before first <channel>
# Find first <channel
idx = content.find('<channel')
header = content[:idx] if idx != -1 else content

# Split by <channel ...> ... </channel>
# Pattern for channel block
channel_pattern = re.compile(r'(<channel[^>]*id="([^"]+)"[^>]*>.*?</channel>)', re.DOTALL)
for m in channel_pattern.finditer(content):
    block = m.group(1)
    cid = m.group(2)
    if cid in tvg_ids:
        channels_out.append(block)

# Now programmes for those channel ids
prog_pattern = re.compile(r'(<programme[^>]*channel="([^"]+)"[^>]*>.*?</programme>)', re.DOTALL)
for m in prog_pattern.finditer(content):
    block = m.group(1)
    cid = m.group(2)
    if cid in tvg_ids:
        programmes_out.append(block)

print(f'Channels kept: {len(channels_out)}')
print(f'Programmes kept: {len(programmes_out)}')

# Build new XML
new_content = header
new_content += '\n' + '\n'.join(channels_out) + '\n'
new_content += '\n' + '\n'.join(programmes_out) + '\n'
new_content += '</tv>\n'

# Write gzipped
with gzip.open(epg_out, 'wt', encoding='utf-8') as f:
    f.write(new_content)

print('Done writing filtered EPG')
