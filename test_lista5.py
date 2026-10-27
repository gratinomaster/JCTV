#!/usr/bin/env python3
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

def check_url(url, timeout=15):
    try:
        req = Request(url, headers={
            'User-Agent': 'VLC/3.0.18 LibVLC/3.0.18',
            'Accept': '*/*'
        })
        with urlopen(req, timeout=timeout) as resp:
            # read small chunk
            data = resp.read(2048)
            if resp.status >= 200 and resp.status < 400:
                return True
            return False
    except HTTPError as e:
        if e.code < 400:
            return True
        return False
    except Exception as e:
        return False

def main():
    path = '/home/runner/work/JCTV/JCTV/lista5.m3u'
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f'Erro ao ler {path}: {e}', flush=True)
        sys.exit(1)
    
    lines = content.splitlines()
    out = []
    i = 0
    kept = 0
    total = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith('#EXTM3U'):
            out.append(line)
            i += 1
            continue
        if stripped.startswith('#EXTINF'):
            extinf = line
            i += 1
            if i >= len(lines):
                break
            url_line = lines[i]
            url = url_line.strip()
            i += 1
            if not url or url.startswith('#'):
                # try to skip invalid
                continue
            total += 1
            print(f'Testando {total}: {url[:70]}...', flush=True)
            if check_url(url):
                out.append(extinf)
                out.append(url_line if url_line.strip() == url else url)
                kept += 1
                print('  OK', flush=True)
            else:
                print('  FALHA - removendo', flush=True)
            continue
        i += 1
    
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
            if out:
                f.write('\n')
    except Exception as e:
        print(f'Erro ao escrever {path}: {e}', flush=True)
        sys.exit(1)
    
    print(f'\nConcluído: {kept}/{total} canais mantidos em {path}', flush=True)

if __name__ == '__main__':
    main()
