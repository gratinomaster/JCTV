#!/usr/bin/env python3
import subprocess
import re
import sys

INPUT_FILE = "lista5.m3u"
OUTPUT_FILE = "lista5.m3u"

def parse_m3u(filepath):
    channels = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.rstrip('\n') for l in f.readlines()]
    
    i = 0
    if lines and lines[0].startswith('#EXTM3U'):
        header = lines[0]
        i = 1
    else:
        header = None
    
    while i < len(lines):
        if lines[i].startswith('#EXTINF:'):
            extinf = lines[i]
            i += 1
            if i < len(lines) and lines[i].strip() and not lines[i].startswith('#'):
                url = lines[i].strip()
                channels.append((extinf, url))
            i += 1
        else:
            i += 1
    
    return header, channels

def test_url(url, timeout=15):
    try:
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
             '--max-time', str(timeout), '-L', url],
            capture_output=True, text=True, timeout=timeout + 5
        )
        code = result.stdout.strip()
        return code
    except Exception:
        return "000"

def extract_channel_name(extinf):
    match = re.search(r',(.+)$', extinf)
    if match:
        return match.group(1).strip()
    return "Unknown"

def main():
    header, channels = parse_m3u(INPUT_FILE)
    
    seen = set()
    unique = []
    for extinf, url in channels:
        key = (extract_channel_name(extinf), url)
        if key not in seen:
            seen.add(key)
            unique.append((extinf, url))
    
    print(f"Total de canais unicos: {len(unique)}")
    print(f"Removidas {len(channels) - len(unique)} entradas duplicadas")
    print()
    
    working = []
    failed = []
    
    for idx, (extinf, url) in enumerate(unique, 1):
        name = extract_channel_name(extinf)
        sys.stdout.write(f"[{idx}/{len(unique)}] Testando: {name}... ")
        sys.stdout.flush()
        
        code = test_url(url)
        
        if code in ('200', '201', '301', '302', '303', '307', '308'):
            print(f"OK (HTTP {code})")
            working.append((extinf, url))
        else:
            print(f"FALHOU (HTTP {code})")
            failed.append((name, code, url))
    
    print()
    print("=" * 60)
    print(f"RESULTADO: {len(working)} funcionando / {len(failed)} falharam de {len(unique)} total")
    print("=" * 60)
    
    if failed:
        print("\nCanais que falharam:")
        for name, code, url in failed:
            print(f"  - {name} (HTTP {code})")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        if header:
            f.write(header + '\n')
        for extinf, url in working:
            f.write(extinf + '\n')
            f.write(url + '\n')
    
    print(f"\nArquivo {OUTPUT_FILE} salvo com {len(working)} canais funcionando.")

if __name__ == '__main__':
    main()
