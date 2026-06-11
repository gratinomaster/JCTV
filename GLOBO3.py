#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para extrair links de canais ao vivo do Globoplay
(extraindo o nome do canal pela URL ou pelo texto visível, preservando acentos)
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import json
import time
from datetime import datetime


def extrair_links_globoplay(url="https://globoplay.globo.com/agora-na-tv/"):
    """
    Extrai links de canais ao vivo do Globoplay usando Selenium
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Iniciando extração...")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Acessando: {url}")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aguardando carregamento...")
        time.sleep(5)

        script = """
        const results = [];
        const elements = document.querySelectorAll('a[href*="/ao-vivo/"]');

        elements.forEach(el => {
            const href = el.getAttribute('href');
            const texto = el.innerText.trim();  // texto visível do link
            if (!href) return;

            const partes = href.split('/').filter(Boolean);
            const canal = partes[0]; // ex: sportv, gnt, tv-globo

            results.push({
                canal: canal,
                url: href,
                titulo: texto || null
            });
        });

        const unique = [];
        const seen = new Set();

        results.forEach(item => {
            if (!seen.has(item.url)) {
                seen.add(item.url);
                unique.push(item);
            }
        });

        return unique;
        """

        links = driver.execute_script(script)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Links encontrados: {len(links)}")
        return links

    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Erro: {e}")
        return []

    finally:
        driver.quit()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Driver fechado")


def normalizar_nome_canal(canal):
    """
    Ajusta nomes para apresentação de canais especiais
    """
    mapa = {
        "sportv": "SporTV",
        "globonews": "GloboNews",
        "tv-globo": "TV Globo",
        "gnt": "GNT",
        "multishow": "Multishow",
        "premiere": "Premiere",
        "premiere-2": "Premiere 2",
        "premiere-3": "Premiere 3",
        "premiere-4": "Premiere 4",
        "cbn-sp": "CBN SP",
        "cbn-rj": "CBN RJ",
    }
    return mapa.get(canal, canal.replace('-', ' ').title())


def processar_links(links):
    """
    Processa e normaliza os links
    """
    processados = []

    for link in links:
        url = link['url']
        if url.startswith('/'):
            url = 'https://globoplay.globo.com' + url

        # Usa o texto visível do site se existir; senão, normaliza pelo slug
        if link.get('titulo'):
            titulo = link['titulo']
        else:
            titulo = normalizar_nome_canal(link['canal'])

        processados.append({
            'titulo': titulo,
            'url': url
        })

    return processados


def salvar_arquivo(links, nome_arquivo="canais_ao_vivo.txt"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Salvando {nome_arquivo}...")
    with open(nome_arquivo, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("CANAIS AO VIVO - GLOBOPLAY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Data de extração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
        f.write(f"Total de canais: {len(links)}\n")
        f.write("=" * 80 + "\n\n")

        for i, link in enumerate(links, 1):
            f.write(f"{i}. {link['titulo']}\n")
            f.write(f"   URL: {link['url']}\n\n")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] TXT salvo com sucesso")


def salvar_json(links, nome_arquivo="canais_ao_vivo.json"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Salvando {nome_arquivo}...")
    with open(nome_arquivo, 'w', encoding='utf-8') as f:
        json.dump(links, f, ensure_ascii=False, indent=2)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] JSON salvo com sucesso")


def main():
    print("\n" + "=" * 80)
    print("EXTRATOR DE CANAIS AO VIVO - GLOBOPLAY")
    print("=" * 80 + "\n")

    links_brutos = extrair_links_globoplay()

    if not links_brutos:
        print("Nenhum link encontrado.")
        return

    links_processados = processar_links(links_brutos)

    salvar_arquivo(links_processados)
    salvar_json(links_processados)

    print("\n" + "=" * 80)
    print(f"Extração concluída! Total: {len(links_processados)} canais")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
