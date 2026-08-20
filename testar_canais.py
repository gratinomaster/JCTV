#!/usr/bin/env python3
import re
import requests
import sys
from urllib.parse import urlparse

def testar_url(url, timeout=10):
    """Testa se uma URL está acessível e retorna um stream válido"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if response.status_code == 200:
            # Para streams HLS, tentamos ler alguns bytes
            content_type = response.headers.get('content-type', '')
            # Verifica se é um stream válido (m3u8 ou outros formatos de stream)
            if 'mpegurl' in content_type.lower() or 'video' in content_type.lower() or url.endswith('.m3u8'):
                # Tenta ler um pouco do conteúdo para confirmar
                chunk = next(response.iter_content(chunk_size=1024), None)
                if chunk:
                    return True
            # Se não for stream mas retornar 200, ainda consideramos válido
            return True
        return False
    except Exception as e:
        return False

def processar_lista_m3u(arquivo_entrada, arquivo_saida):
    """Processa arquivo m3u, testa canais e salva apenas os funcionais"""
    with open(arquivo_entrada, 'r', encoding='utf-8') as f:
        linhas = f.readlines()
    
    canais = []
    canal_atual = []
    
    # Parse do arquivo m3u
    for linha in linhas:
        linha = linha.strip()
        if linha.startswith('#EXTINF:'):
            if canal_atual:
                canais.append(canal_atual)
            canal_atual = [linha]
        elif canal_atual and not linha.startswith('#'):
            canal_atual.append(linha)
    
    if canal_atual:
        canais.append(canal_atual)
    
    print(f"Total de canais encontrados: {len(canais)}")
    
    canais_funcionais = []
    canais_nao_funcionais = []
    
    for i, canal in enumerate(canais):
        if len(canal) >= 2:
            nome = canal[0].split(',')[-1].strip() if ',' in canal[0] else f"Canal {i+1}"
            url = canal[1]
            print(f"Testando canal {i+1}/{len(canais)}: {nome}")
            if testar_url(url):
                canais_funcionais.append(canal)
                print(f"  ✓ Funcionando")
            else:
                canais_nao_funcionais.append(canal)
                print(f"  ✗ Não funcionando")
    
    # Salvar canais funcionais
    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        f.write('#EXTM3U\n')
        for canal in canais_funcionais:
            for linha in canal:
                f.write(linha + '\n')
    
    print(f"\nResumo:")
    print(f"Canais funcionais: {len(canais_funcionais)}")
    print(f"Canais não funcionais: {len(canais_nao_funcionais)}")
    
    if canais_nao_funcionais:
        print("\nCanais removidos:")
        for canal in canais_nao_funcionais:
            nome = canal[0].split(',')[-1].strip() if ',' in canal[0] else "Desconhecido"
            print(f"  - {nome}")
    
    return canais_funcionais

if __name__ == "__main__":
    arquivo_entrada = "lista5.m3u"
    arquivo_saida = "lista5.m3u"
    
    # Criar backup primeiro
    import shutil
    shutil.copy2(arquivo_entrada, arquivo_entrada + ".backup")
    print(f"Backup criado: {arquivo_entrada}.backup")
    
    # Processar e testar canais
    processar_lista_m3u(arquivo_entrada, arquivo_saida)
    print(f"\nLista atualizada salva em: {arquivo_saida}")