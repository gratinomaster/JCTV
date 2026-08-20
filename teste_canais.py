#!/usr/bin/env python3
import requests
import re
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

def parse_m3u(filepath):
    """Parse M3U file into list of (extinf_line, url_line) tuples"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f.readlines()]
    
    channels = []
    i = 0
    header = ""
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTM3U'):
            header = line
            i += 1
            continue
        if line.startswith('#EXTINF'):
            extinf = line
            if i + 1 < len(lines):
                url = lines[i + 1]
                if url and not url.startswith('#'):
                    channels.append((extinf, url))
                    i += 2
                    continue
            i += 1
            continue
        i += 1
    return header, channels

def test_url(url, timeout=10):
    """Test if a URL is accessible. Returns True if working."""
    try:
        # For HLS streams, try to fetch the master playlist or a segment
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
        }
        
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        
        if resp.status_code == 200:
            # Read a small chunk to verify content is actually being delivered
            content = resp.content[:512].decode('utf-8', errors='ignore')
            # Check if it looks like valid HLS content
            if '#EXT' in content or '#EXTM3U' in content or 'M3U' in content.upper():
                return True, resp.status_code, "HLS OK"
            # Could still be a redirect or binary content that works
            return True, resp.status_code, "Content OK"
        else:
            return False, resp.status_code, f"HTTP {resp.status_code}"
    except requests.exceptions.Timeout:
        return False, 0, "Timeout"
    except requests.exceptions.ConnectionError as e:
        return False, 0, f"Connection Error: {str(e)[:80]}"
    except requests.exceptions.TooManyRedirects:
        return False, 0, "Too Many Redirects"
    except Exception as e:
        return False, 0, f"Error: {str(e)[:80]}"

def main():
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lista5.m3u')
    
    print("Lendo lista5.m3u...")
    header, channels = parse_m3u(filepath)
    print(f"Total de canais encontrados: {len(channels)}")
    
    # Deduplicate by URL
    seen_urls = set()
    unique_channels = []
    for extinf, url in channels:
        if url not in seen_urls:
            seen_urls.add(url)
            unique_channels.append((extinf, url))
    
    print(f"URLs únicas para testar: {len(unique_channels)}")
    print("-" * 60)
    
    working = []
    failed = []
    
    print(f"Testando {len(unique_channels)} URLs com {min(20, len(unique_channels))} threads...\n")
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_channel = {}
        for extinf, url in unique_channels:
            future = executor.submit(test_url, url)
            future_to_channel[future] = (extinf, url)
        
        for i, future in enumerate(as_completed(future_to_channel), 1):
            extinf, url = future_to_channel[future]
            ok, status, msg = future.result()
            
            # Extract channel name from EXTINF
            name_match = re.search(r',(.+)$', extinf)
            name = name_match.group(1).strip()[:60] if name_match else url[:60]
            
            if ok:
                working.append((extinf, url))
                status_str = f"[OK {status}]"
            else:
                failed.append((extinf, url, msg))
                status_str = f"[FALHOU {status}]"
            
            print(f"  {i:3d}/{len(unique_channels)} {status_str:15s} {name}")
    
    print("\n" + "=" * 60)
    print(f"RESULTADO: {len(working)} funcionando / {len(failed)} falharam / {len(unique_channels)} total")
    
    if failed:
        print(f"\nCanais FALHADOS:")
        for extinf, url, msg in failed:
            name_match = re.search(r',(.+)$', extinf)
            name = name_match.group(1).strip()[:60] if name_match else url[:60]
            print(f"  - {name} | {msg}")
    
    # Write cleaned file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(header + '\n')
        for extinf, url in working:
            f.write(extinf + '\n')
            f.write(url + '\n')
    
    print(f"\nArquivo lista5.m3u sobrescrito com {len(working)} canais funcionando.")

if __name__ == '__main__':
    main()
