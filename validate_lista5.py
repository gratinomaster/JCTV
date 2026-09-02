#!/usr/bin/env python3
"""Final validation of lista5.m3u - tests EPG and streams."""
import urllib.request
import gzip
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

M3U_FILE = "lista5.m3u"
EPG_URL = "https://iptv-epg.org/files/epg-us.xml.gz"

def check_epg():
    print("=" * 60)
    print("1. TESTE DO EPG")
    print("=" * 60)
    print(f"EPG URL: {EPG_URL}")
    
    req = urllib.request.Request(EPG_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    print(f"  Download OK: {len(data)} bytes")
    
    try:
        data = gzip.decompress(data)
    except:
        pass
    print(f"  Decompressed: {len(data)} bytes")
    
    root = ET.fromstring(data)
    
    channels = ['ABCNewsLive.us', 'FoxNewsChannel.us', 'FoxBusiness.us', 'CBSNews.us']
    today = datetime.now().strftime('%Y%m%d')
    tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y%m%d')
    day_after = (datetime.now() + timedelta(days=2)).strftime('%Y%m%d')
    
    all_ok = True
    for ch in channels:
        counts = {today: 0, tomorrow: 0, day_after: 0}
        found = False
        for ch_el in root.findall('./channel'):
            if ch_el.get('id') == ch:
                found = True
                break
        for prog in root.findall('./programme'):
            if prog.get('channel') == ch:
                d = prog.get('start', '')[:8]
                if d in counts:
                    counts[d] += 1
        status = "OK" if (found and counts[today] > 0 and counts[tomorrow] > 0) else "FALHOU"
        if status == "FALHOU":
            all_ok = False
        print(f"  {ch}: encontrado={found} | hoje={counts[today]} | amanha={counts[tomorrow]} | depois={counts[day_after]} [{status}]")
    
    return all_ok

def check_streams():
    print()
    print("=" * 60)
    print("2. TESTE DOS STREAMS")
    print("=" * 60)
    
    with open(M3U_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse
    lines = content.strip().split('\n')
    all_ok = True
    
    for i in range(len(lines)):
        if lines[i].startswith('#EXTINF:'):
            name = lines[i].rsplit(',', 1)[-1] if ',' in lines[i] else lines[i]
            url = None
            if i + 1 < len(lines) and not lines[i+1].startswith('#'):
                url = lines[i+1].strip()
            
            if url:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        data = resp.read(300)
                        is_hls = b'#EXTM3U' in data or 'mpegURL' in resp.headers.get('Content-Type','') or 'application/vnd.apple' in resp.headers.get('Content-Type','')
                        status = "OK" if is_hls else "OK(tipo:"+resp.headers.get('Content-Type','')+")"
                        if not is_hls:
                            all_ok = False
                        print(f"  [{status}] {name}")
                except Exception as e:
                    all_ok = False
                    print(f"  [FALHOU] {name}: {e}")
    
    return all_ok

def check_format():
    print()
    print("=" * 60)
    print("3. VALIDACAO DO FORMATO")
    print("=" * 60)
    
    with open(M3U_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().strip().split('\n')
    
    ok = True
    
    # Header must have EPG URL
    if not lines[0].startswith('#EXTM3U'):
        print("  [ERRO] Linha 1 deve ser #EXTM3U")
        ok = False
    if 'x-tvg-url=' not in lines[0]:
        print("  [ERRO] Faltando x-tvg-url no header")
        ok = False
    else:
        m = re.search(r'x-tvg-url="([^"]+)"', lines[0])
        if m and 'imgur' in m.group(1):
            print("  [ERRO] Header contem imgur")
            ok = False
    
    # Check every URL has EXTINF above it
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('http'):
            if i == 0 or not lines[i-1].startswith('#EXTINF:'):
                print(f"  [ERRO] URL na linha {i+1} sem #EXTINF acima")
                ok = False
    
    # Check logos are .jpg and no imgur
    for line in lines:
        if 'tvg-logo=' in line:
            m = re.search(r'tvg-logo="([^"]+)"', line)
            if m:
                logo = m.group(1)
                if 'imgur' in logo.lower():
                    print(f"  [ERRO] Logo imgur: {logo[:50]}")
                    ok = False
                base = logo.split('?')[0]
                if not base.lower().endswith('.jpg'):
                    print(f"  [ERRO] Logo nao .jpg: {logo[:60]}")
                    ok = False
    
    # No urls with imgur
    for line in lines:
        if 'imgur' in line.lower():
            print(f"  [ERRO] Referencia a imgur: {line[:60]}")
            ok = False
    
    # Count channels
    n = sum(1 for l in lines if l.startswith('#EXTINF:'))
    print(f"  Canais: {n}")
    print(f"  Header: {lines[0][:80]}")
    print(f"  Formato: {'OK' if ok else 'COM ERROS'}")
    return ok

def check_antivirus():
    print()
    print("=" * 60)
    print("4. VERIFICACAO ANTI-VIRUS / LINKS SUSPEITOS")
    print("=" * 60)
    
    with open(M3U_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    suspicious = ['imgur.com', 'bit.ly', 'tinyurl.com', 't.co/', 'adfly', 'ouo.io', 'shorte.st']
    found = False
    for s in suspicious:
        if s in content.lower():
            print(f"  [ALERTA] Encontrado: {s}")
            found = True
    if not found:
        print("  Nenhum link suspeito encontrado")
    return not found

if __name__ == '__main__':
    ok = True
    if not check_epg():
        ok = False
    if not check_streams():
        ok = False
    if not check_format():
        ok = False
    if not check_antivirus():
        ok = False
    
    print()
    print("=" * 60)
    print(f"RESULTADO FINAL: {'TUDO OK' if ok else 'HA PROBLEMAS'}")
    print("=" * 60)
