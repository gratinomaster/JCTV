#!/usr/bin/env python3
import subprocess
import re
import sys

M3U = "lista5.m3u"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 12

def test_url(url):
    url = re.sub(r"[\s\x00-\x1f\x7f]", "", url)
    cmd = ["curl", "-sL", "--max-time", str(TIMEOUT), "-A", UA,
           "-r", "0-4096", "-w", "\n@@@%{http_code}", "-o", "/tmp/test.bin", url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT+3)
    except:
        return False
    meta = r.stdout.strip().split("@@@")[-1] if "@@@" in r.stdout else "0"
    try:
        code = int(meta)
    except:
        return False
    if code not in (200,206):
        return False
    try:
        body = open("/tmp/test.bin","rb").read()
    except:
        return False
    if b"#EXTM3U" in body:
        return True
    # Alguns streams retornam dados binários diretamente? raro p/ HLS, mas checamos
    return len(body) > 200

def parse_and_filter(path):
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    out_lines = []
    if lines:
        out_lines.append(lines[0])  # header
    i = 1
    total = 0
    kept = 0
    removed = []
    while i < len(lines):
        line = lines[i]
        s = line.rstrip('\n\r')
        stripped = s.strip()
        i += 1
        if stripped.startswith('#EXTINF'):
            extinf = s
            # procura URL
            # leia adiante até achar URL
            url = None
            j = i
            while j < len(lines):
                sl = lines[j].strip()
                j += 1
                if sl and not sl.startswith('#'):
                    url = sl.rstrip('\n\r')
                    i = j
                    break
                if sl.startswith('#EXTINF'):
                    j -= 1
                    i = j
                    break
            if url:
                total += 1
                name = extinf.split(',')[-1] if ',' in extinf else 'unknown'
                ok = test_url(url)
                if ok:
                    out_lines.append(extinf + '\n')
                    out_lines.append(url + '\n')
                    kept += 1
                    print(f"OK {kept}/{total}: {name[:60]}")
                else:
                    removed.append(name)
                    print(f"REMOVIDO: {name[:60]}")
            # se não achou URL, ignora bloco
            continue
    return out_lines, total, kept, removed

def main():
    print("Testando e filtrando lista5.m3u...")
    try:
        out, total, kept, removed = parse_and_filter(M3U)
        with open(M3U, 'w', encoding='utf-8') as f:
            f.writelines(out)
        print(f"\nConcluído: {kept}/{total} canais mantidos")
        if removed:
            print(f"Removidos: {len(removed)}")
        return 0
    except Exception as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
