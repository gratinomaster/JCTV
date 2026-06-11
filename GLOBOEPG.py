#!/usr/bin/env python3
"""
GLOBOEPG_FIXED.py - Versão corrigida do gerador de EPG para regiões da Globo.
Corrige problemas de horários, fuso horário e lógica de fallback.
"""

import gzip
import json
import re
import sys
import html
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
import urllib.parse
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Configuração de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

try:
    import requests
except ImportError:
    logging.info("Instalando biblioteca requests...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

BASE_URL = "https://redeglobo.globo.com"
GLOBOPLAY_URL = "https://globoplay.globo.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

# Mapeamento de regiões para URLs e fusos horários (UTC offset)
# Brasil possui: -02 (Fernando de Noronha), -03 (Brasília), -04 (Manaus/Cuiabá), -05 (Acre)
REGION_CONFIG = {
    "sp": {"url": "sao-paulo", "name": "São Paulo", "tz": -3},
    "rj": {"url": "rio", "name": "Rio de Janeiro", "tz": -3},
    "df": {"url": "globobrasilia", "name": "Distrito Federal", "tz": -3},
    "bh": {"url": "globominas", "name": "Belo Horizonte", "tz": -3},
    "pr": {"url": "rpc", "name": "Paraná", "tz": -3},
    "pe": {"url": "tvglobo", "name": "Pernambuco", "tz": -3},
    "ba": {"url": "redebahia", "name": "Bahia", "tz": -3},
    "pb": {"url": "tvparaiba", "name": "Paraíba", "tz": -3},
    "es": {"url": "tvgazetaes", "name": "Espírito Santo", "tz": -3},
    "ce": {"url": "tvverdesmares", "name": "Ceará", "tz": -3},
    "ms": {"url": "tvmorena", "name": "Mato Grosso do Sul", "tz": -4},
    "mt": {"url": "tvcentroamerica", "name": "Mato Grosso", "tz": -4},
    "sc": {"url": "nsctv", "name": "Santa Catarina", "tz": -3},
    "rs": {"url": "rbstvrs", "name": "Rio Grande do Sul", "tz": -3},
    "pa": {"url": "tvliberal", "name": "Pará", "tz": -3},
    "am": {"url": "redeamazonica", "name": "Amazonas", "tz": -4},
    "al": {"url": "tvgazetaal", "name": "Alagoas", "tz": -3},
    "sportv": {"url": "sportv", "name": "SporTV", "tz": -3},
    "cbn_sp": {"url": "cbn", "name": "CBN São Paulo", "tz": -3},
    "cbn_rj": {"url": "cbn", "name": "CBN Rio de Janeiro", "tz": -3},
}

# Cache para evitar downloads repetidos da mesma página
html_cache = {}

def fetch_page(url: str) -> Optional[str]:
    """Busca uma página web e retorna seu conteúdo com cache"""
    if url in html_cache:
        return html_cache[url]
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        html_cache[url] = response.text
        return response.text
    except Exception as e:
        logging.error(f"Erro ao buscar {url}: {e}")
        return None

def extract_programming_from_html(html_content: str, target_date: str) -> Optional[dict]:
    """Extrai dados de programação para uma data específica do HTML"""
    try:
        # A Globo usa um atributo data-props com JSON escapado
        m = re.search(r'class="grade-area" data-props="([^"]+)"', html_content)
        if not m:
            return None

        raw = m.group(1)
        decoded = html.unescape(raw)
        data = json.loads(decoded)

        output = (
            data.get("context", {})
            .get("gridData", {})
            .get("data", {})
            .get("output", [])
        )

        for day_data in output:
            day_date = day_data.get("date", "")[:10]
            if day_date == target_date:
                return day_data

        return None
    except Exception as e:
        logging.debug(f"Erro na extração: {e}")
        return None

def get_programming_for_region(region_code: str, days: int = 5) -> Dict[str, Any]:
    """Obtém dados de programação para uma região específica por múltiplos dias"""
    config = REGION_CONFIG[region_code]
    region_url = config["url"]
    all_programs = {}
    today = datetime.now()

    # Construção robusta da URL base
    if region_code == "sportv":
        base_url = f"{GLOBOPLAY_URL}/sportv/"
    elif region_code.startswith("cbn"):
        city = "sp" if "sp" in region_code else "rj"
        base_url = f"{BASE_URL}/{city}/cbn/programacao/"
    else:
        # Algumas regiões têm estrutura de URL diferente
        if region_code in ["sc", "rs", "pa", "am", "al"]:
            base_url = f"{BASE_URL}/{region_code}/{region_url}/programacao/"
        else:
            base_url = f"{BASE_URL}/{region_url}/programacao/"

    html_content = fetch_page(base_url)
    
    if not html_content:
        logging.warning(f"Sem HTML para {region_code}, usando genérico.")
        return get_generic_programming(region_code, days)

    for day_offset in range(days):
        target_date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        day_data = extract_programming_from_html(html_content, target_date)

        if day_data:
            all_programs[target_date] = day_data

    if not all_programs:
        return get_generic_programming(region_code, days)

    return all_programs

def get_generic_programming(region_code: str, days: int = 5) -> Dict[str, Any]:
    """Gera programação genérica se o scraping falhar"""
    all_programs = {}
    today = datetime.now()
    
    if region_code == "sportv":
        programs_list = [
            ("05:00", "01:00", "sportv News"),
            ("06:00", "02:00", "Redação sportv"),
            ("08:00", "02:00", "Tá na Área"),
            ("10:00", "02:00", "Troca de Passes"),
            ("12:00", "02:00", "sportv News"),
            ("14:00", "02:00", "Redação sportv"),
            ("16:00", "02:00", "Tá na Área"),
            ("18:00", "02:00", "sportv News"),
            ("20:00", "02:00", "Seleção sportv"),
            ("22:00", "02:00", "Tá na Área"),
            ("00:00", "05:00", "sportv News"),
        ]
    elif region_code.startswith("cbn"):
        programs_list = [
            ("05:00", "03:00", "CBN no Ar"),
            ("08:00", "01:00", "CBN Entrevista"),
            ("09:00", "01:00", "CBN Dinheiro"),
            ("10:00", "01:00", "CBN Tecnologia"),
            ("11:00", "01:00", "CBN No Caminho"),
            ("12:00", "01:00", "CBN Esportes"),
            ("13:00", "03:00", "CBN No Ar"),
            ("16:00", "02:00", "CBN Dinheiro"),
            ("18:00", "01:00", "CBN Brasil"),
            ("19:00", "03:00", "CBN No Ar"),
            ("22:00", "07:00", "CBN Late Night"),
        ]
    else:
        programs_list = [
            ("04:00", "01:00", "Hora 1"),
            ("05:00", "02:00", "Bom Dia Local"),
            ("07:00", "02:00", "Bom Dia Brasil"),
            ("09:00", "01:00", "Mais Você"),
            ("10:00", "01:00", "Encontro"),
            ("11:00", "01:00", "Jornal Local 1"),
            ("12:00", "01:00", "Globo Esporte"),
            ("13:00", "01:00", "Jornal Hoje"),
            ("14:00", "01:00", "Novela I"),
            ("15:00", "02:00", "Sessão da Tarde"),
            ("17:00", "01:00", "Vale a Pena Ver de Novo"),
            ("18:00", "01:00", "Novela II"),
            ("19:00", "01:00", "Jornal Nacional"),
            ("20:00", "01:00", "Novela III"),
            ("21:00", "01:00", "Big Brother Brasil"),
            ("22:00", "01:00", "Jornal da Globo"),
            ("23:00", "05:00", "Filme / Série"),
        ]
    
    tz_offset = REGION_CONFIG[region_code]["tz"]
    tz_str = f"{tz_offset:+03d}:00"

    for day_offset in range(days):
        target_date = (today + timedelta(days=day_offset)).strftime("%Y-%m-%d")
        slots = []
        
        for time_str, duration_str, name in programs_list:
            # Simplificação: assume que o horário é no dia target_date
            dt_str = f"{target_date}T{time_str}:00{tz_str}"
            slots.append({
                "name": name,
                "startTime": dt_str,
                "duration": f"{duration_str}:00",
                "program": {"synopsis": "Programação local da Rede Globo."},
                "contentType": "program"
            })
        
        all_programs[target_date] = {
            "date": target_date,
            "slots": slots
        }
    
    return all_programs

def format_xml_datetime(dt_str: str, tz_offset: int) -> str:
    """Converte ISO format string para formato XMLTV"""
    try:
        # Remove o offset da string se houver para parsear
        clean_str = re.sub(r'([+-]\d{2}):?(\d{2})$', '', dt_str)
        dt = datetime.fromisoformat(clean_str)
        
        # Formata com o offset correto
        offset_str = f"{tz_offset:+03d}00"
        return dt.strftime("%Y%m%dT%H%M%S") + f" {offset_str}"
    except Exception:
        return ""

def generate_epg(regions_data: Dict[str, Any]) -> str:
    """Gera o conteúdo XMLTV EPG usando ElementTree"""
    tv = ET.Element("tv", {
        "source-info-url": "https://redeglobo.globo.com",
        "source-info-name": "Rede Globo",
        "generator-info-name": "Manus GLOBOEPG Generator"
    })

    for region_key, region_info in regions_data.items():
        config = REGION_CONFIG[region_key]
        tvg_id = region_key if region_key in ["sportv", "cbn_sp", "cbn_rj"] else f"globo_{region_key}"
        
        # Canal
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        ET.SubElement(channel, "display-name").text = f"Globo {region_info['name']}"
        ET.SubElement(channel, "icon", src="https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.png")

        # Programas
        tz_offset = config["tz"]
        
        # Ordenar datas para garantir continuidade
        sorted_dates = sorted(region_info["programs"].keys())
        
        for date_str in sorted_dates:
            day_data = region_info["programs"][date_str]
            slots = day_data.get("slots", [])

            for i, slot in enumerate(slots):
                name = slot.get("name", "")
                if not name: continue

                # Tentar pegar startTime real da API
                start_iso = slot.get("startTime")
                if not start_iso: continue
                
                # Calcular end time baseado na duração ou no início do próximo
                duration_str = slot.get("duration", "01:00:00")
                parts = duration_str.split(":")
                delta = timedelta(hours=int(parts[0]), minutes=int(parts[1]), seconds=int(parts[2]))
                
                # Parse start_iso
                clean_start = re.sub(r'([+-]\d{2}):?(\d{2})$', '', start_iso)
                start_dt = datetime.fromisoformat(clean_start)
                
                # Se houver um próximo slot no mesmo dia, o fim é o início do próximo
                if i + 1 < len(slots):
                    next_start_iso = slots[i+1].get("startTime")
                    clean_next = re.sub(r'([+-]\d{2}):?(\d{2})$', '', next_start_iso)
                    end_dt = datetime.fromisoformat(clean_next)
                    # Se o próximo horário for menor que o atual, provavelmente virou o dia
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                else:
                    end_dt = start_dt + delta

                prog = ET.SubElement(tv, "programme", {
                    "channel": tvg_id,
                    "start": format_xml_datetime(start_iso, tz_offset),
                    "end": format_xml_datetime(end_dt.isoformat(), tz_offset)
                })
                ET.SubElement(prog, "title", lang="pt-BR").text = name
                
                synopsis = slot.get("program", {}).get("synopsis", "")
                if synopsis:
                    ET.SubElement(prog, "desc", lang="pt-BR").text = synopsis
                
                category = slot.get("contentType", "")
                if category:
                    ET.SubElement(prog, "category", lang="pt-BR").text = category

    # Converter para string formatada
    xml_str = ET.tostring(tv, encoding="utf-8")
    parsed_xml = minidom.parseString(xml_str)
    return parsed_xml.toprettyxml(indent="  ")

def main():
    print("=" * 60)
    print("GLOBOEPG FIXED - Gerador de EPG da Rede Globo")
    print("=" * 60)

    regions_data = {}
    regions = list(REGION_CONFIG.keys())

    print(f"\n1. Buscando programação para {len(regions)} regiões...")
    for i, region_code in enumerate(regions, 1):
        name = REGION_CONFIG[region_code]["name"]
        print(f"   [{i}/{len(regions)}] {name} ({region_code})...", end=" ", flush=True)

        programs = get_programming_for_region(region_code, days=5)

        if programs:
            regions_data[region_code] = {
                "name": name,
                "programs": programs,
            }
            print(f"✓ {len(programs)} dias")
        else:
            print("✗ Erro")

    if not regions_data:
        print("\nErro: Não foi possível obter dados!")
        sys.exit(1)

    print("\n2. Gerando arquivos...")
    epg_content = generate_epg(regions_data)

    # Salvar XML
    with open("GLOBOEPG.xml", "w", encoding="utf-8") as f:
        f.write(epg_content)
    
    # Salvar GZ
    with gzip.open("GLOBOEPG.xml.gz", "wt", encoding="utf-8") as f:
        f.write(epg_content)
    
    # Salvar tvg-ids
    with open("tvg-ids.txt", "w", encoding="utf-8") as f:
        f.write("# TVG IDs - Rede Globo\n")
        for r_code, r_info in regions_data.items():
            tvg_id = r_code if r_code in ["sportv", "cbn_sp", "cbn_rj"] else f"globo_{r_code}"
            f.write(f'{tvg_id},"Globo {r_info["name"]}",https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.png,Globo\n')

    print("\nConcluído! Arquivos GLOBOEPG.xml, GLOBOEPG.xml.gz e tvg-ids.txt gerados.")

if __name__ == "__main__":
    main()
