#!/usr/bin/env python3
import subprocess
import sys
import re
import urllib.parse
import os

M3U = "lista5.m3u"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15

def curl_head(url, timeout=TIMEOUT):
    url = re.sub(r"[\s\x00-\x1f\x7f]", "", url)
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
           "-w", "\n@@@%{http_code}", "-I", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
    except subprocess.TimeoutExpired:
        return False
    meta = r.stdout.strip().split("@@@")[-1] if "@@@" in r.stdout else "0"
    try:
        code = int(meta)
        return code in (200, 206)
    except:
        return False

def curl_get_small(url, timeout=TIMEOUT):
    url = re.sub(r"[\s\x00-\x1f\x7f]", "", url)
    # Tenta pegar apenas o manifesto ou primeiros bytes
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
           "-r", "0-4096", "-w", "\n@@@%{http_code}", "-o", "/tmp/_test.bin", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout+5)
    except subprocess.TimeoutExpired:
        return False
    meta = r.stdout.strip().split("@@@")[-1] if "@@@" in r.stdout else "0"
    try:
        code = int(meta)
    except:
        return False
    try:
        body = open("/tmp/_test.bin", "rb").read()
    except:
        body = b""
    if code not in (200, 206):
        return False
    # É manifesto HLS?
    if b"#EXTM3U" in body:
        return True
    # Talvez seja um segmento - mas melhor verificar se retorna dados válidos
    # Para streams HLS, manifesto é o que precisamos
    return len(body) > 50

def test_stream(url):
    # Primeiro tenta HEAD ou GET pequeno
    if curl_get_small(url):
        return True
    # Tenta com range maior
    url_clean = re.sub(r"[\s\x00-\x1f\x7f]", "", url)
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
           "-r", "0-8192", "-w", "\n@@@%{http_code}", "-o", "/tmp/_test2.bin", url_clean]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT+5)
    except:
        return False
    meta = r.stdout.strip().split("@@@")[-1] if "@@@" in r.stdout else "0"
    try:
        if int(meta) not in (200,206): return False
    except:
        return False
    try:
        body = open("/tmp/_test2.bin","rb").read()
    except:
        return False
    return b"#EXTM3U" in body or len(body) > 100

def parse_m3u(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    result = []
    i = 0
    header = lines[0] if lines else '#EXTM3U\n'
    i = 1
    while i < len(lines):
        line = lines[i]
        i += 1
        s = line.strip()
        if not s or s.startswith('#EXTM3U'):
            continue
        if s.startswith('#EXTINF'):
            # Próxima linha deve ser URL
            extinf = s
            # Pega URL na próxima linha não vazia
            while i < len(lines):
                l2 = lines[i].strip()
                i += 1
                if l2 and not l2.startswith('#'):
                    url = l2
                    result.append((extinf, url))
                    break
                elif l2.startswith('#EXTINF'):
                    # Voltou - não tinha URL
                    i -= 1
                    break
            continue
        # linha normal que não é comentário - pode ser URL
        if s.startswith('http'):
            # procura extinf anterior
            pass
    return header, result

# Versão mais robusta
def parse_m3u2(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    header = ''
    entries = [] # (extinf, url)
    for j, l in enumerate(lines):
        if j == 0:
            header = l
            continue
        s = l.strip()
        if not s: continue
    # melhor parser
    return None

