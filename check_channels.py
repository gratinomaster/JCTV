#!/usr/bin/env python3
import subprocess
import sys
import re
import os

M3U_FILE = "/home/runner/work/JCTV/JCTV/lista5.m3u"
TIMEOUT = 10  # seconds per URL

def parse_m3u(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip('\n')
        if line.startswith('#EXTINF:'):
            extinf = line
            if i + 1 < len(lines):
                url = lines[i + 1].rstrip('\n')
                entries.append((extinf, url))
                i += 2
            else:
                i += 1
        else:
            i += 1
    
    return lines, entries

def test_url(url):
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '--max-time', str(TIMEOUT), '-L', url],
            capture_output=True, text=True, timeout=TIMEOUT + 5
        )
        http_code = result.stdout.strip()
        
        if http_code == '200':
            # For m3u8 URLs, also verify content is a valid playlist
            if '.m3u8' in url:
                result2 = subprocess.run(
                    ['curl', '-s', '--max-time', str(TIMEOUT), '-L', url],
                    capture_output=True, text=True, timeout=TIMEOUT + 5
                )
                content = result2.stdout
                if content.startswith('#EXTM3U') or content.startswith('#EXT-X-TARGETDURATION') or 'EXTINF' in content:
                    return True, '200 (valid HLS)'
                elif len(content) > 100:
                    return True, '200 (has content)'
                else:
                    return False, f'200 but empty/short content ({len(content)} bytes)'
            return True, '200'
        elif http_code == '403':
            # Some streams return 403 but still work (token-protected)
            return True, '403 (possibly working)'
        elif http_code in ('301', '302', '307', '308'):
            return True, http_code
        else:
            return False, http_code
    except subprocess.TimeoutExpired:
        return False, 'TIMEOUT'
    except Exception as e:
        return False, str(e)

def main():
    print(f"Parsing {M3U_FILE}...")
    lines, entries = parse_m3u(M3U_FILE)
    print(f"Found {len(entries)} channel entries\n")
    
    working = []
    failed = []
    
    for i, (extinf, url) in enumerate(entries, 1):
        channel_name = extinf.split(',')[-1] if ',' in extinf else 'unknown'
        print(f"[{i}/{len(entries)}] Testing: {channel_name[:60]}...")
        
        ok, status = test_url(url)
        if ok:
            print(f"  OK ({status})")
            working.append((extinf, url))
        else:
            print(f"  FAILED ({status})")
            failed.append((extinf, url))
    
    print(f"\n=== Results ===")
    print(f"Working: {len(working)}")
    print(f"Failed: {len(failed)}")
    
    for extinf, url in failed:
        name = extinf.split(',')[-1]
        print(f"  REMOVED: {name[:60]}")
    
    # Build new file content - preserve existing #EXTM3U header with attributes
    header_line = lines[0] if lines and lines[0].startswith('#EXTM3U') else '#EXTM3U\n'
    new_lines = [header_line]
    for extinf, url in working:
        new_lines.append(extinf + '\n')
        new_lines.append(url + '\n')
    
    # Backup original
    os.rename(M3U_FILE, M3U_FILE + '.bak')
    print(f"\nBackup saved to {M3U_FILE}.bak")
    
    # Write new file
    with open(M3U_FILE, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Updated {M3U_FILE} with {len(working)} working channels")

if __name__ == '__main__':
    main()
