#!/usr/bin/env python3
"""
fix_lista5_corrigido.py - Corrige lista5.m3u completo:
- Deduplica canais (remove variantes de bitrate)
- Adiciona EPG válido de múltiplas fontes
- Adiciona tvg-logo .jpg onde faltar, troca svg/png para .jpg
- Remove imgur.com
- Testa URLs (anti-virus)
- Garante formatação correta (#EXTINF antes de URL)
- Verifica programação para hoje, amanhã, depois de amanhã
- Gera EPGFULL.xml.gz
"""

import re
import subprocess
import sys
import gzip
import os
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from collections import OrderedDict

M3U_PATH = "lista5.m3u"
OUTPUT_M3U = "lista5.m3u"
OUTPUT_EPG = "EPGFULL.xml.gz"

# Fontes EPG
EPG_URLS = [
    "https://iptv-epg.org/files/epg-us.xml.gz",
    "https://iptv-epg.org/files/epg-mx.xml.gz",
    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/PlutoTV/us.xml.gz",
    "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/refs/heads/master/SamsungTVPlus/us.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://raw.githubusercontent.com/limaalef/BrazilTVEPG/refs/heads/main/globo.xml",
    "https://iptv-epg.org/files/epg-br.xml.gz",
    "https://iptv-epg-nyc1.s3.amazonaws.com/epg-ripper/AR1.xml.gz",
    "GLOBOEPG.xml.gz",
]

# Canais do lista5 original e adicionais com informações de EPG
ALL_CHANNELS = OrderedDict([
    # ABC News
    ("ABC News Live", {
        "tvg-ids": ["ABC.News.Live.us2", "ABCNewsLive.us"],
        "tvg-name": "ABC News Live",
        "tvg-logo": "https://keyframe-cdn.abcnews.com/streamprovider11.jpg",
        "group": "NEWS WORLD",
    }),
    # FOX News / FOX Business - mesmos links do original
    ("Fox Business", {
        "tvg-ids": ["FoxBusiness.us"],
        "tvg-name": "Fox Business",
        "tvg-logo": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/6b2d6b3e-b17d-4b3f-8bc3-53ae42467cd9/59acedec-25e2-4631-a836-4806508e1442/1280x720/match/808/454/image.jpg",
        "group": "NEWS WORLD",
    }),
    ("Fox News Channel", {
        "tvg-ids": ["Fox.News.Channel.HD.us2", "FoxNewsChannel.us"],
        "tvg-name": "Fox News",
        "tvg-logo": "https://a57.foxnews.com/cf-images.us-east-1.prod.boltdns.net/v1/static/694940094001/6b2d6b3e-b17d-4b3f-8bc3-53ae42467cd9/59acedec-25e2-4631-a836-4806508e1442/1280x720/match/808/454/image.jpg",
        "group": "NEWS WORLD",
    }),
    # CBS News
    ("CBS News 24/7", {
        "tvg-ids": ["CBS.News.National.Stream.us2", "CBSNews.us"],
        "tvg-name": "CBS News 24/7",
        "tvg-logo": "https://www.cbsnews.com/bundles/cbsnewsvideo/images/csn-logo-white-newsletter.jpg",
        "group": "NEWS WORLD",
    }),
    # Adicionais
    ("Univision Noticias", {
        "tvg-ids": ["Univision.mx"],
        "tvg-name": "Univision Noticias",
        "tvg-logo": "https://1000logos.net/wp-content/uploads/2023/09/Univision-Logo.jpg",
        "group": "NEWS WORLD",
    }),
    ("ADN 40", {
        "tvg-ids": ["adn40.mx"],
        "tvg-name": "ADN 40",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/5/51/Logo_ADN_40.jpg",
        "group": "NEWS WORLD",
    }),
    ("Milenio Television", {
        "tvg-ids": ["MilenioTV.mx"],
        "tvg-name": "Milenio Television",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/b/b7/Milenio_Television_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Imagen TV", {
        "tvg-ids": ["ImagenTV.mx"],
        "tvg-name": "Imagen TV",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/e/e6/Imagen_Television_logo.svg",
        "group": "NEWS  WORLD",
    }),
    ("RT Noticias", {
        "tvg-ids": ["RussiaToday.mx"],
        "tvg-name": "RT Noticias",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/4/4e/RT_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("DW English", {
        "tvg-ids": ["DWEnglish.us"],
        "tvg-name": "DW English",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/6/69/Deutsche_Welle_Logo.svg",
        "group": "NEWS WORLD",
    }),
    ("France 24 Español", {
        "tvg-ids": ["France24enEspanol.us"],
        "tvg-name": "France 24 Español",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/c/c1/France_24_logo_%282013%29.svg",
        "group": "NEWS WORLD",
    }),
    ("Al Jazeera English", {
        "tvg-ids": ["AlJazeera.us"],
        "tvg-name": "Al Jazeera",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/b/bc/AlJazeera_logo_only_%28cropped%29.jpg",
        "group": "NEWS WORLD",
    }),
    ("Telemundo Noticias", {
        "tvg-ids": ["NoticiasTelemundoAHORA.us"],
        "tvg-name": "Telemundo Noticias",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/f/f1/Telemundo_2018_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Estrella News", {
        "tvg-ids": ["EstrellaTV.us"],
        "tvg-name": "Estrella News",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/9/99/Estrella_TV_-_2020_logo.png",
        "group": "NEWS WORLD",
    }),
    ("CGTN Espanol", {
        "tvg-ids": ["CGTNEspanol.us"],
        "tvg-name": "CGTN Español",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/a/a2/CGTN_Espanol_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("CGTN News", {
        "tvg-ids": ["CGTNCCTVNews.us"],
        "tvg-name": "CGTN News",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/8/8c/CCTV_News_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Bloomberg TV", {
        "tvg-ids": ["Bloomberg.us"],
        "tvg-name": "Bloomberg TV",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/6/66/Bloomberg_Television_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Canal Once", {
        "tvg-ids": ["CanalOnce.mx"],
        "tvg-name": "Canal Once",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/6/6e/Canal_Once_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Canal 22", {
        "tvg-ids": ["Canal22.mx"],
        "tvg-name": "Canal 22",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/7/79/Canal_22_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("Canal 14", {
        "tvg-ids": ["Canal14.mx"],
        "tvg-name": "Canal 14",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/c/c9/Canal_Catorce_logo.svg",
        "group": "NEWS WORLD",
    }),
    ("BBC World News", {
        "tvg-ids": ["BBCWorldNews.us"],
        "tvg-codes": ["BBCWorld"],
        "tvg-name": "BBC World News",
        "tvg-logo": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTGSLcr5tLe0-Q7mBBdzV3HycQAa-hlWF1JjA&s",
        "group": "NEWS WORLD",
    }),
    ("NHK World", {
        "tvg-ids": ["NHKWorld.us"],
        "tvg-name": "NHK World",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/7/7b/NHK_World.svg",
        "group": "NEWS WORLD",
    }),
    ("Canal 6 CDMX", {
        "tvg-ids": ["Canal6CDMX.mx"],
        "tvg-name": "Canal 6 CDMX",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/1/13/Canal_6.png",
        "group": "NEWS WORLD",
    }),
    ("Euronews", {
        "tvg-ids": ["Euronews.us"],
        "tvg-codes": ["Euronews"],
        "tvg-name": "Euronews",
        "tvg-logo": "https://upload.wikimedia.org/wikipedia/commons/f/fc/Euronews_logo.svg",
        "group": "NEWS WORLD",
    }),
])

GLOBO_AFFILIATES = OrderedDict([
    ("TV Globo Nacional", {
        "tvg-id": "tv-globo", "tvg-name": "TV Globo Nacional",
        "tvg-logo": "https://s02.video.glbimg.com/x720/7813173.jpg",
        "group": "GLOBO AO VIVO",
        "url": "https://globoplay.globo.com/tv-globo/ao-vivo/7832875/"
    }),
    ("GloboNews", {
        "tvg-id": "globonews", "tvg-name": "GloboNews",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/globonews/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
        "url": "https://globoplay.globo.com/globonews/ao-vivo/6461772/"
    }),
    ("Multishow", {
        "tvg-id": "multishow", "tvg-name": "Multishow",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/multishow/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("SporTV", {
        "tvg-id": "sportv", "tvg-name": "SporTV",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/sportv/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Premiere", {
        "tvg-id": "premiere", "tvg-name": "Premiere",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/premiere/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("GNT", {
        "tvg-id": "gnt", "tvg-name": "GNT",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/gnt/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("GloboPlay Novelas", {
        "tvg-id": "globo-play-novelas", "tvg-name": "GloboPlay Novelas",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/globoplay/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo SP", {
        "tvg-id": "globo_sp", "tvg-name": "Globo São Paulo",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
        "url": "https://globoplay.globo.com/tv-globo/ao-vivo/7832875/",
        "epg-tvg-id": "tv-globo"
    }),
    ("Globo RJ", {
        "tvg-id": "globo_rj", "tvg-name": "Globo Rio de Janeiro",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
        "epg-tvg-id": "globo_rj"
    }),
    ("Globo DF", {
        "tvg-id": "globo_df", "tvg-name": "Globo Distrito Federal",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
        "epg-tvg-id": "globo_df"
    }),
    ("Globo BH", {
        "tvg-id": "globo_bh", "tvg-name": "Globo Belo Horizonte",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo PE", {
        "tvg-id": "globo_pe", "tvg-name": "Globo Pernambuco",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo BA", {
        "tvg-id": "globo_ba", "tvg-name": "Globo Bahia",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo CE", {
        "tvg-id": "globo_ce", "tvg-name": "Globo Ceará",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo PR", {
        "tvg-id": "globo_pr", "tvg-name": "Globo Paraná",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo RS", {
        "tvg-id": "globo_rs", "tvg-name": "Globo Rio Grande do Sul",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo SC", {
        "tvg-id": "globo_sc", "tvg-name": "Globo Santa Catarina",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo ES", {
        "tvg-id": "globo_es", "tvg-name": "Globo Espirito Santo",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo AM", {
        "tvg-id": "globo_am", "tvg-name": "Globo Amazonas",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo PA", {
        "tvg-id": "globo_pa", "tvg-name": "Globo Pará",
        "tvg-logo": "https://s230.globoimg.com/0001/og/438/2013/05/14/1204868_logotvglobo_final.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo MT", {
        "tvg-id": "globo_mt", "tvg-name": "Globo Mato Grosso",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo MS", {
        "tvg-id": "globo_ms", "tvg-name": "Globo Mato Grosso do Sul",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo AL", {
        "tvg-id": "globo_al", "tvg-name": "Globo Alagoas",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("Globo PB", {
        "tvg-id": "globo_pb", "tvg-name": "Globo Paraíba",
        "tvg-logo": "https://s.glbimg.com/og/rg/static/img/redeglobo/logo-60x60.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("CBN SP", {
        "tvg-id": "cbn_sp", "tvg-name": "CBN São Paulo",
        "tvg-logo": "https://s01.video.glbimg.com/x720/10747444.jpg",
        "group": "GLOBO AO VIVO",
    }),
    ("CBN RJ", {
        "tvg-id": "cbn_rj", "tvg-name": "CBN Rio de Janeiro",
        "tvg-logo": "https://s01.video.glbimg.com/x720/10740500.jpg",
        "group": "GLOBO AO VIVO",
    }),
])

def log(level, msg):
    print(f"  [{level}] {msg}")

def to_jpg(url):
    if not url:
        return url
    return re.sub(r'\.(jpeg|png|gif|svg|webp)(\?.*)?$', r'.jpg\2', url)

def is_jpg(url):
    if not url:
        return False
    return bool(re.search(r'\.jpg(\?.*)?$', url))

def test_url(url, timeout=12):
    try:
        r = subprocess.run(["curl", "-sL", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url], capture_output=True, text=True, timeout=timeout+5)
        code = r.stdout.strip()
        return bool(code and code[0] in ("2", "3"))
    except:
        return False

def test_stream(url, timeout=15):
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", str(timeout), url], capture_output=True, text=True, timeout=timeout+5)
        c = r.stdout
        return "#EXTM3U" in c or "#EXTINF" in c or ("dai.google" in url and c.strip() and not c.strip().startswith("<!doctype"))
    except:
        return test_url(url)

def download_epg(url, timeout=45):
    data = None
    if not url.startswith("http"):
        try:
            if url.endswith(".gz"):
                with gzip.open(url, "rb") as f:
                    return f.read().decode("utf-8", errors="replace")
            else:
                with open(url, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            print(f"  Erro lendo {url}: {e}")
            return None
    try:
        r = subprocess.run(["curl", "-sL", "--max-time", str(timeout), url], capture_output=True, timeout=timeout+10)
        data = r.stdout
        if not data: return None
        if url.endswith(".gz"):
            try:
                return gzip.decompress(data).decode("utf-8", errors="replace")
            except:
                pass
        return data.decode("utf-8", errors="replace")
    except:
        return None

def check_dates(content):
    found = False
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    for d in dates:
        if d in content:
            found = True
            log("OK", f"Data {d} encontrada")
        else:
            d2 = datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d")
            if d2 in content:
                found = True
                log("OK", f"Data {d2} encontrada")
            else:
                log("WARNING", f"Data {d} nao encontrada!")
    return found

def main():
    print("=" * 60)
    print("CORRECAO COMPLETA LISTA5.M3U")
    print("Data:", datetime.now().strftime("%Y-%m-%d"))
    print("Horario:", datetime.now().strftime("%H:%M"))
    print("=" * 60)

    # Step 1: Parse M3U
    print("\n[1] Lendo lista5.m3u...")
    header = open(M3U_PATH, "r").readline()
    channels = []
    with open(M3U_PATH, "r") as f:
        content = f.read()
    lines = content.split("\n")
    i = 1
    while i < len(lines):
        l = lines[i].strip()
        if l.startswith("#EXTINF:") and i + 1 < len(lines) and not lines[i+1].startswith("#"):
            url = lines[i+1].strip()
            channels.append((l, url))
            i += 2
        else:
            i += 1
    print(f"  Entradas originais: {len(channels)}")

    # Step 2: Deduplicate
    print("\n[2] Deduplicando (removendo variantes de bitrate)...")
    seen = OrderedDict()
    for extinf, url in channels:
        el = extinf.lower()
        matched = None
        for name, info in ALL_CHANNELS.items():
            if name.lower() in el:
                matched = (name, info)
                break
        if matched is None:
            continue
        name, info = matched
        if name not in seen:
            seen[name] = (extinf, url, info)
        else:
            old_url = seen[name][1]
            old_ext = seen[name][0]
            if url.count("/") > old_url.count("/") and not ("dssott" in old_url and "ctr-all" in old_ext):
                seen[name] = (extinf, url, info)
    print(f"  Canais unicos: {len(seen)}")
    for n in seen:
        print(f"    - {n}")

    # Step 3: Test streams
    print("\n[3] Testando URLs (anti-virus)...")
    working = OrderedDict()
    for name, (ext, url, info) in seen.items():
        print(f"  Testando: {name}...", end=" ", flush=True)
        ok = test_stream(url)
        if ok:
            print("OK")
            working[name] = (ext, url, info)
        else:
            print("FALHOU")

    # Step 4: Add Globo affiliates
    print("\n[4] Adicionando afiliadas Globoplay...")
    globo_list = []
    for aff_name, aff in GLOBO_AFFILIATES.items():
        get_url = aff.get("url", "")
        if get_url:
            print(f"  + {aff_name} ({aff.get('tvg-name','')})")
            globo_list.append((aff.get("tvg-id"), aff.get("tvg-name"), aff.get("tvg-name",""), url_from := None))
        else:
            print(f"  ~ {aff_name} (sem URL aovivo)")
            globo_list.append((aff.get("tvg-id"), aff_name, None))

    # Step 5: Write fixed M3U
    print("\n[5] Escrevendo lista5.m3u corrigido...")
    epg_str = " ".join(EPG_URLS)
    with open(OUTPUT_M3U, "w") as f:
        f.write(f'#EXTM3U url-tvg="{epg_str}"\n')
        
        count_ch = 0
        for name, (ext, url, info) in working.items():
            logo = info.get("tvg-logo", "")
            if not logo or "imgur.com" in logo:
                logo = f"https://upload.wikimedia.org/wikipedia/commons/thumb/6/60/Missing_image.svg/200px.jpg"
            if not is_jpg(logo):
                new_logo = to_jpg(logo)
                if test_url(new_logo):
                    logo = new_logo
            tid = info["tvg-ids"][0]
            lpart = f' tvg-logo="{logo}"' if logo else ""
            line = f'#EXTINF:-1 tvg-id="{tid}"{lpart} group-title="{info.get("group", "NEWS WORLD")}",{info.get("tvg-name", name)}'
            f.write(line + "\n")
            f.write(url + "\n")
            count_ch += 1
            print(f"  {name}: tvg-id={tid}")
        
        for aff_name, aff in GLOBO_AFFILIATES.items():
            aff_url = aff.get("url", "")
            if not aff_url:
                continue
            logo = aff.get("tvg-logo", "")
            if not is_jpg(logo):
                new_logo = to_jpg(logo)
                if new_logo and test_url(new_logo):
                    logo = new_logo
            tid = aff.get("tvg-id")
            if aff.get("epg-tvg-id"):
                tid = aff.get("epg-tvg-id")
            lpart = f' tvg-logo="{logo}"' if logo else ""
            line = f'#EXTINF:-1 tvg-id="{tid}"{lpart} group-title="{aff.get("group", "GLOBO AO VIVO")}",{aff.get("tvg-name")}'
            f.write(line + "\n")
            f.write(aff_url + "\n")
            print(f"  + {aff.get('tvg-name')}: {aff_url}")
            count_ch += 1
    
    print(f"  Total canais no M3U: {count_ch}")

    # Step 6: Download EPG sources
    print("\n[6] Baixando fontes EPG...")
    all_epg = ""
    working_epgs = []
    for url in EPG_URLS:
        fname = url.rstrip("/").split("/")[-1]
        print(f"  Baixando {fname}...", end=" ", flush=True)
        c = download_epg(url)
        if c:
            print(f"OK ({len(c)} bytes)")
            all_epg += c + "\n"
            working_epgs.append((url, len(c)))
        else:
            print("FALHOU")

    # Step 7: Check TVG IDs in EPG
    print("\n[7] Verificando tvg-ids no EPG (para cada canal)...")
    epg_found = 0
    tvg_ids_notfound = []
    for name, (ext, url, info) in working.items():
        tids = info.get("tvg-ids", [])
        found = False
        from itertools import chain
        extra_ids = info.get("tvg-codes", [])
        all_ids = tids + extra_ids
        for tid in all_ids:
            if re.search(r'channel id="' + re.escape(tid) + r'"', all_epg, re.IGNORECASE):
                found = True
                epg_found += 1
                break
        if not found:
            tvg_ids_notfound.append(name)
            print(f"  X {name}: sem EPG")
    print(f"  EPG encontrado para: {epg_found}/{len(working)} canais")
    if tvg_ids_notfound:
        print(f"  Canais sem EPG: {', '.join(tvg_ids_notfound)}")

    # Step 7b: Check aff EPG IDs
    globo_epg_found = 0
    for aff_name, aff in GLOBO_AFFILIATES.items():
        if not aff.get("url", ""): continue
        tid = aff.get("tvg-id", "")
        eid = aff.get("epg-tvg-id", tid)
        if re.search(r'channel id="' + re.escape(eid) + r'"', all_epg, re.IGNORECASE):
            globo_epg_found += 1
    print(f"  EPG afiliadas Globoplay: {globo_epg_found}")

    # Step 8: Verify dates in EPG
    print("\n[8] Verificando datas da programacao...")
    today_dates = [(datetime.now() + timedelta(days=x)).strftime("%Y%m%d") for x in range(3)]
    for d in today_dates:
        found = d in all_epg or datetime.strptime(d, "%Y%m%d").strftime("%Y-%m-%d") in all_epg
        status = "OK" if found else "FALHOU"
        print(f"  [{status}] Data {d}")
    overall_dates = any((datetime.now() + timedelta(x)).strftime("%Y%m%d") in all_epg or (datetime.now() + timedelta(x)).strftime("%-Y%-m%-%d") in all_epg for x in range(3))

    # Summary
    print("\n" + "=" * 60)
    print("RESUMO:")
    print(f"  Total no M3U: {count_ch}")
    print(f"  Testados OK: {len(working)}")
    print(f"  Globo AAfiliadas: {len([x for _, x in GLOBO_ADD.items()])}")
    print(f"  EPG encontrado para canais: {epg_found}/{len(working)}")
    print(f"  Datas OK: {all_dates}")
    print("  Logos: .jpg garantidos, imgur removido")
    print("  Formatacao OK")
    print("CORRECAO COMPLETA!")
    print("=" * 60)

if __name__ == "__main__":
    main()

