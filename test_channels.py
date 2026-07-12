#!/usr/bin/env python3
import subprocess
import sys

M3U_FILE = "lista5.m3u"
TIMEOUT = 15

def test_url(url):
    try:
        result = subprocess.run(
            ["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", 
             "--max-time", str(TIMEOUT), "-A", "Mozilla/5.0", url],
            capture_output=True, text=True, timeout=TIMEOUT+5
        )
        code = result.stdout.strip()
        return code and code[0] in ("2", "3")
    except:
        return False

def main():
    with open(M3U_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U\n"
    channels = []
    i = 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            if i + 1 < len(lines) and not lines[i+1].startswith("#"):
                url = lines[i+1].strip()
                channels.append((line, url))
                i += 2
                continue
        i += 1

    print(f"Total de canais: {len(channels)}")
    working = []
    for idx, (extinf, url) in enumerate(channels, 1):
        name = extinf.split(",")[-1].strip() if "," in extinf else f"Canal {idx}"
        print(f"[{idx}/{len(channels)}] Testando: {name}...", end=" ", flush=True)
        if test_url(url):
            print("OK")
            working.append((extinf, url))
        else:
            print("FALHOU")

    with open(M3U_FILE, "w", encoding="utf-8") as f:
        f.write(header)
        for extinf, url in working:
            f.write(extinf + "\n")
            f.write(url + "\n")

    print(f"\nResultado: {len(working)}/{len(channels)} canais funcionando")
    print(f"Arquivo {M3U_FILE} atualizado!")

if __name__ == "__main__":
    main()
