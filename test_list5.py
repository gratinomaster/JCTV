import subprocess
import sys

def testar_url(url):
    try:
        resultado = subprocess.run(
            ["curl", "-Is", "--max-time", "10", url],
            capture_output=True,
            text=True,
            timeout=15
        )
        if resultado.returncode == 0 and "200" in resultado.stdout:
            return True
    except Exception as e:
        pass
    return False

def main():
    arquivo = "lista5.m3u"
    with open(arquivo, "r", encoding="utf-8") as f:
        linhas = f.readlines()
    
    saida = []
    if linhas and linhas[0].startswith("#EXTM3U"):
        saida.append("#EXTM3U\n")
    
    i = 0
    total = 0
    keep = 0
    while i < len(linhas):
        linha = linhas[i]
        if linha.strip().startswith("#EXTINF"):
            total += 1
            info = linha
            if i + 1 < len(linhas):
                url = linhas[i + 1].strip()
                print(f"Testando ({total}): {url[:60]}...")
                if testar_url(url):
                    print("  OK\n")
                    saida.append(info)
                    saida.append(linhas[i + 1] if linhas[i + 1].endswith('\n') else linhas[i + 1] + '\n')
                    keep += 1
                else:
                    print("  OFFLINE\n")
                i += 2
                continue
        i += 1
    
    with open(arquivo, "w", encoding="utf-8") as f:
        f.writelines(saida)
    print(f"Concluído: {keep}/{total} canais mantidos")

if __name__ == "__main__":
    main()
