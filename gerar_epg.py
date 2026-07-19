#!/usr/bin/env python3
import gzip
import re
import unicodedata
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from collections import OrderedDict
from io import StringIO
import os
import urllib.request

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
M3U_PATH = "NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"

EPG_URLS = [
    "https://epgshare01.online/epgshare01/epg_ripper_AR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_BR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_MX1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_ES1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_PT1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_CO1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_FR1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_DE1.xml.gz",
    "https://epgshare01.online/epgshare01/epg_ripper_VE1.xml.gz",
]

# Manual mapping: M3U display name -> list of EPG channel IDs (priority order)
CHANNEL_MAP = {
    # === Argentine broadcast ===
    "TYC SPORTS": ["Canal.TyC.Sports.ar"],
    "Telefe Buenos Aires": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Jujuy": ["Canal.Telefe.(Argentina).ar"],
    "Telefe Neuquén": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Misiones": ["Canal.Telefé.(Argentina).ar"],
    "Telefe Santiago del Estero": ["Canal.Telefé.(Argentina).ar"],
    "Telefe San Luis": ["Canal.Telefé.(Argentina).ar"],
    "El Trece": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "América TV": ["Canal.America.TV.(Argentina).ar"],
    "TN - Todo Noticias": ["Canal.Cablenoticias.ar"],
    "A24": ["Canal.Cablenoticias.ar"],
    "C5N": ["Canal.Cablenoticias.ar"],
    "Crónica TV": ["Canal.Cablenoticias.ar"],
    "CRÓNICA TV": ["Canal.Cablenoticias.ar"],
    "Canal 26 HD": ["Canal.Cablenoticias.ar"],
    "TN": ["Canal.Cablenoticias.ar"],
    "NET TV 27.2 - TDA 27.2": ["Canal.Televisión.Pública.(Argentina).ar"],
    "NET TV HD": ["Canal.Televisión.Pública.(Argentina).ar"],
    "LN+": ["Canal.Cablenoticias.ar"],
    "ENCUENTRO": ["Canal.Pakapaka.ar"],
    "PAKAPAKA": ["Canal.Pakapaka.ar"],
    "CINE.AR": ["Canal.Film.&.Arts.ar"],
    "EL DESTAPE TV": ["Canal.Cablenoticias.ar"],
    "FRANCE 24 ESPAÑOL": ["Canal.CNN.en.Español.ar"],
    "CANAL ORBE 21": ["Canal.Cablenoticias.ar"],
    "CANAL E": ["Canal.Cablenoticias.ar"],
    "Canal E": ["Canal.Cablenoticias.ar"],
    "VOLVER": ["Canal.Cablenoticias.ar"],
    "CANAL LUZ": ["Canal.Cablenoticias.ar"],
    "CANAL DE LA MÚSICA": ["Canal.Cablenoticias.ar"],
    "Canal de la Música": ["Canal.Cablenoticias.ar"],
    "TELSUR": ["Canal.Cablenoticias.ar"],
    "Telesur": ["Canal.Cablenoticias.ar"],
    "RT EN ESPAÑOL": ["Canal.CNN.en.Español.ar"],
    "CARAS TV": ["Canal.Cablenoticias.ar"],
    "ECO TV": ["Canal.Cablenoticias.ar"],
    "INCAA TV": ["Canal.Pakapaka.ar"],
    "CANAL RURAL": ["Canal.Cablenoticias.ar"],
    "Canal Rural": ["Canal.Cablenoticias.ar"],
    "QUIERO MÚSICA TV": ["Canal.Cablenoticias.ar"],
    "ARGENTINA 12": ["Canal.Cablenoticias.ar"],
    "CN23": ["Canal.Cablenoticias.ar"],
    "BRAVO TV": ["Canal.Cablenoticias.ar"],
    "Bravo TV": ["Canal.Cablenoticias.ar"],
    "CONSTRUIR TV": ["Canal.Cablenoticias.ar"],
    "Canal de la Ciudad": ["Canal.Cablenoticias.ar"],
    "CANAL DE LA CIUDAD": ["Canal.Cablenoticias.ar"],
    "Canal 21 TV": ["Canal.Cablenoticias.ar"],
    "Norte | Bahía Blanca | Argentina": ["Canal.Cablenoticias.ar"],
    "VTV": ["Canal.Cablenoticias.ar"],
    "5TV Corrientes": ["Canal.Cablenoticias.ar"],
    "Argentinísima Satelital": ["Canal.Cablenoticias.ar"],
    "Canal 10 Cordoba": ["Canal.Telefé.(Argentina).ar"],
    "TV Universidad": ["Canal.Cablenoticias.ar"],
    "Canal 9 Litoral": ["Canal.Cablenoticias.ar"],
    "Canal 13 Jujuy TV": ["Canal.13.de.Argentina.(El.Trece).ar"],
    "América Canal 4 Posadas | AR": ["Canal.America.TV.(Argentina).ar"],
    "Aire de Santa Fe": ["Canal.Cablenoticias.ar"],
    "Telemax": ["Canal.Cablenoticias.ar"],
    "GARAGE TV": ["Canal.Cablenoticias.ar"],
    "MusicTop": ["Canal.Cablenoticias.ar"],
    "Canal 8 SAN JUAN": ["Canal.Cablenoticias.ar"],
    "Canal 5 ROSARIO": ["Canal.Cablenoticias.ar"],
    "Canal 6 DIGITAL": ["Canal.Cablenoticias.ar"],
    "Canal 79 MAR DEL PLATA": ["Canal.Cablenoticias.ar"],
    "CANAL 22": ["Canal.Cablenoticias.ar"],
    "CANAL 4 JUJUY": ["Canal.Cablenoticias.ar"],
    "CANAL 3 LA PAMPA": ["Canal.Cablenoticias.ar"],
    "CANAL 3 LAS HERAS": ["Canal.Cablenoticias.ar"],
    "CANAL 2 GUALEGUAY": ["Canal.Cablenoticias.ar"],
    "CANAL 10 MAR DEL PLATA": ["Canal.Cablenoticias.ar"],
    "CANAL 9 TELEVIDA": ["Canal.Cablenoticias.ar"],
    "CANAL LUZ": ["Canal.Cablenoticias.ar"],
    "CANAL DE LA MÚSICA": ["Canal.Cablenoticias.ar"],
    "CADENA 103": ["Canal.Cablenoticias.ar"],
    "LITUS TV": ["Canal.Cablenoticias.ar"],
    "ALTERNA TV": ["Canal.Cablenoticias.ar"],
    "CATAMARCA TV": ["Canal.Cablenoticias.ar"],
    "AUNAR": ["Canal.Cablenoticias.ar"],
    "Radio Sublime Gracia TV": ["Canal.Cablenoticias.ar"],
    "Radio UP": ["Canal.Cablenoticias.ar"],
    "América Sports": ["Canal.Cablenoticias.ar"],
    "IP Noticias": ["Canal.Cablenoticias.ar"],
    "Quiero Musica en mi Idioma (1080p)": ["Canal.Cablenoticias.ar"],
    "Radio Maria TV (1080p)": ["Canal.Cablenoticias.ar"],
    "Telemundo Internacional (1080p) AR": ["Canal.Telemundo.(México).mx"],
    "Unife TV": ["Canal.Cablenoticias.ar"],
    "UNIFE 25.1 - TDA 25.1": ["Canal.Cablenoticias.ar"],
    "TV MANÁ ARGENTINA": ["Canal.Cablenoticias.ar"],
    "SAN PEDRO TV": ["Canal.Cablenoticias.ar"],
    "TV SOLIDARIA": ["Canal.Cablenoticias.ar"],
    "Camaras de Villa Gesell (Av. 3 y 104)": ["Canal.Cablenoticias.ar"],

    # === Argentine cable/paid ===
    "Disney Channel Latin America": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America (1080p) RAW": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Center (1080p)": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Panregional HD (1080p)": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Channel Latin America Panregional HD (1080p) RAW": ["Canal.Disney.Channel.(Argentina).ar"],
    "Disney Jr. Latin America": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America North HD (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America North HD (1080p) RAW": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South HD (1080p)": ["Canal.Disney.Junior.(Argentina).ar"],
    "Disney Jr. Latin America South HD (1080p) RAW": ["Canal.Disney.Junior.(Argentina).ar"],
    "Sony Channel (1080p)": ["Canal.Sony.(Argentina).ar"],
    "AMC Latin America (1080p) AR": ["Canal.AMC.(México).mx"],
    "MTV Latin America (1080p) AR": ["Canal.MTV.(Argentina).ar"],
    "Comedy Central Latin America (1080p) AR": ["Comedy.Central.co"],
    "E! Latin America (1080p) AR": ["Canal.E!.Entertainment.Television.(México).mx"],
    "El Gourmet (1080p)": ["Canal.Elgourmet.ar", "Canal.Elgourmet.mx"],
    "DSports (1080p) AR": ["DIRECTV.Sports.5(DTS6).co"],

    # === Mexico ===
    "Azteca Uno (-1h)": ["Canal.Azteca.Uno.mx"],
    "Azteca Uno - 1H": ["Canal.Azteca.Uno.mx"],
    "ADN 40 (1080p)": ["Canal.ADN.40.mx"],
    "Imagen TV+ (720p)": ["Canal.Excelsior.TV.mx"],
    "Canal 5 TV Cozumel (1080p)": ["Canal.5.de.México.(XHGC).mx"],
    "Milenio Televisión (720p)": ["Milenio.Tv.co"],
    "Canal 14 (1080p)": ["Canal.14.de.México.mx"],
    "TV UNAM (1080p)": ["Canal.TVUNAM.mx"],
    "Canal 22 (1080p)": ["Canal.22.de.México.mx"],
    "Canal del Congreso": ["CANAL.CONGRESO.co"],
    "Justicia TV": ["Canal.Excelsior.TV.mx"],
    "Mexiquense TV (720p)": ["Canal.Mexiquense.TV.mx"],
    "TV Cuatro 4.1": ["Canal.Excelsior.TV.mx"],
    "TV Cuatro 4.2": ["Canal.Excelsior.TV.mx"],
    "CANAL 44 Chihuahua": ["Canal.Excelsior.TV.mx"],
    "Canal 44 Ciudad Juárez (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "Jalisco TV (720p)": ["Canal.Excelsior.TV.mx"],
    "SQCS Canal 4 (1080p)": ["Canal.Excelsior.TV.mx"],
    "TeleFórmula (1080p)": ["Canal.Telefórmula.mx"],
    "Cine Sony": ["Canal.Sony.(México).mx"],
    "TELEVISA NOVELAS": ["Canal.TLNovelas.(México).mx"],
    "De Película Latin America": ["Canal.De.Película.mx"],
    "Telemundo": ["Canal.Telemundo.(México).mx"],
    "UNIVISION NOTICIAS VX": ["Univision.Network.HD.us2"],
    "Estrella TV (1080p)": ["Estrella.TV.us2"],
    "Estrella Games (1080p)": ["Estrella.TV.us2"],
    "Estrella News (1080p)": ["Estrella.TV.us2"],
    "MX EWTN": ["Canal.EWTN.en.Español.mx"],
    "RT Noticias (1080p)": ["Canal.CNN.en.Español.ar"],
    "Canal 33 Tijuana (720p)": ["Canal.5.de.México.(XHGC).mx"],
    "Azteca Internacional (1080p)": ["Canal.Azteca.Uno.mx"],
    "Telemundo Noticias Ahora": ["Canal.Telemundo.(México).mx"],

    # === USA ===
    "ABC News Live - ABC News": ["ABC.News.Live.us2"],
    "Watch Fox News Channel Online | Stream Fox News": ["Fox.News.Channel.HD.us2"],
    "Fox Business Go | Fox News Video": ["Fox.News.Channel.HD.us2"],
    "Watch CBS News 24/7, our free live news stream": ["CBS.Streaming.SD.East.feed.us2"],
    "DW Español": ["Canal.DW.(Latinoamérica).ar"],

    "El Nueve": ["Canal.9.de.Argentina.ar"],
    "24/7 Canal de Noticias": ["Canal.Cablenoticias.ar"],
    "Ciudad Magazine": ["Canal.Cablenoticias.ar"],
    "CANAL 8 SAN JUAN": ["Canal.Cablenoticias.ar"],
    "CANAL 5 ROSARIO": ["Canal.Cablenoticias.ar"],
    "CANAL 6 DIGITAL": ["Canal.Cablenoticias.ar"],
    "CANAL 79 MAR DEL PLATA": ["Canal.Cablenoticias.ar"],
    "UNIFE TV": ["Canal.Cablenoticias.ar"],

    # === Mexico additional ===
    "TVMÁS Veracruz (1080p)": ["Canal.Excelsior.TV.mx"],
    "Presumiendo México (720p)": ["Canal.Excelsior.TV.mx"],
    "8NTV (1080p)": ["Canal.Excelsior.TV.mx"],
    "Expresa TV (720p)": ["Canal.Excelsior.TV.mx"],
    "TVP Culiacán (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TVP Los Mochis (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TVP Mazatlán (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TVP Obregón (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TV Mar La Paz (1080p)": ["Canal.Excelsior.TV.mx"],
    "TV Mar Los Cabos (1080p)": ["Canal.Excelsior.TV.mx"],
    "TV Mar Puerto Vallarta (1080p)": ["Canal.Excelsior.TV.mx"],
    "SET Televisión Canal 26.1 (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "SET Televisión Canal 26.2 (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "RCG TV (1080p)": ["Canal.Excelsior.TV.mx"],
    "Tele Saltillo": ["Canal.Excelsior.TV.mx"],
    "Nueve TV San Luís Potosí (720p)": ["Canal.Excelsior.TV.mx"],
    "SIZART Canal 24 (XHZHZ-TDT) (720p)": ["Canal.Excelsior.TV.mx"],
    "Nayarit Comunica (1080p)": ["Canal.Excelsior.TV.mx"],
    "IERTBCS Canal 8 La Paz (1080p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "IERTBCS Canal 8.2 La Paz (1080p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TV UG (1080p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "VB Media TV (1080p)": ["Canal.Excelsior.TV.mx"],
    "Conecta TV (720p)": ["Canal.Excelsior.TV.mx"],
    "CreaLaTV (1080p)": ["Canal.Excelsior.TV.mx"],
    "Lobo TV (720p)": ["Canal.Excelsior.TV.mx"],
    "Raly TV (720p)": ["Canal.Excelsior.TV.mx"],
    "ICRTV Colima (1080p)": ["Canal.Excelsior.TV.mx"],
    "RTQ Querétaro (1080p)": ["Canal.Excelsior.TV.mx"],
    "ITV Deportes": ["Canal.Excelsior.TV.mx"],
    "PSN": ["Canal.Excelsior.TV.mx"],
    "AMX Noticias (720p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "Super Channel 12": ["Canal.Excelsior.TV.mx"],
    "Antena TV": ["Canal.Excelsior.TV.mx"],
    "B15 Fresnillo (1080p)": ["Canal.Excelsior.TV.mx"],
    "QOO: SIPSE": ["Canal.Excelsior.TV.mx"],
    "YUC: SIPSE": ["Canal.Excelsior.TV.mx"],
    "TAB TV UJAT": ["Canal.Excelsior.TV.mx"],
    "CAM TRC": ["Canal.Excelsior.TV.mx"],
    "CHIAP CANAL 10": ["Canal.Excelsior.TV.mx"],
    "AGS CANAL 26": ["Canal.Excelsior.TV.mx"],
    "Tele Yucatán (1080p)": ["Canal.Excelsior.TV.mx"],
    "Canal 28 Nuevo León (720p)": ["Canal.Excelsior.TV.mx"],
    "María Visión (360p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "Sistema Michoacano de TV (1080p)": ["Canal.Excelsior.TV.mx"],
    "Telemax (XEWH-TDT) (1080p)": ["Canal.Excelsior.TV.mx"],
    "Tlaxcala Televisión (360p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "TRC Televisión (720p)": ["Canal.Excelsior.TV.mx"],
    "TV Lobo Durango (720p)": ["Canal.Excelsior.TV.mx"],
    "Canal 10 Durango (1080p)": ["Canal.Excelsior.TV.mx"],
    "Capital 21 (1080p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "Ingenio TV (720p)": ["Canal.Excelsior.TV.mx"],
    "Multimedios Monterrey (720p)": ["Canal.Excelsior.TV.mx"],
    "Multimedios CDMX (720p)": ["Canal.Excelsior.TV.mx"],
    "Milenio Televisión (MDX)": ["Canal.Excelsior.TV.mx"],
    "TV BUAP (1080p)": ["Canal.Excelsior.TV.mx"],
    "Unison TV (1080p) [Not 24/7]": ["Canal.Excelsior.TV.mx"],
    "Canal ViX (1080p)": ["Canal.Excelsior.TV.mx"],
    "TV Migrante (720p)": ["Canal.Excelsior.TV.mx"],
    "MyTime Movie Network México": ["Canal.Excelsior.TV.mx"],
    "Teleritmo (720p)": ["Canal.Excelsior.TV.mx"],
    "WeatherSpy (720p)": ["Canal.Excelsior.TV.mx"],
    "The Pet Collective (720p)": ["Canal.Excelsior.TV.mx"],

    # === Venezuela ===
    "Venevision": ["Venevision.Venezuela.ve"],
    "VTV Venezolana de Television": ["Venezolana.de.Television.(VTV).ve"],
    "TVes": ["TVes.ve"],
    "Televen": ["Televen.ve"],
    "Globovision": ["Globovision.ve"],
    "Vale TV": ["Vale.TV.ve"],
    "Telesur": ["Telesur.ve"],
    "Meridiano TV": ["Meridiano.TV.ve"],
    "Canal I": ["Canal.I.ve"],
    "La Tele Tuya": ["La.Tele.Tuya.(TLT).ve"],
    "ANTV Asamblea Nacional": ["ANTV.ve"],
    "Venevision Internacional": ["Venevision.Venezuela.ve"],
    "Latina TV": ["Venevision.Venezuela.ve"],
    "Promar TV": ["Venevision.Venezuela.ve"],
    "TeleAragua": ["Venevision.Venezuela.ve"],
    "Inter TV": ["Venevision.Venezuela.ve"],
    "Avila TV": ["Avila.TV.ve"],
    "TV FANB": ["TV.FANB.ve"],
    "ConCiencia TV": ["ConCiencia.TV.ve"],
    "Ve Plus": ["Ve.Plus.ve"],
    "Colombeia": ["Venevision.Venezuela.ve"],
    "Corazon Llanero": ["Venevision.Venezuela.ve"],
    "Canal Orbe 21": ["Canal.Orbe.21.ve"],
    "Buena TV": ["Buena.TV.ve"],
    "Vive TV": ["Vive.TV.ve"],

    # === Brazil - Globo ===
    "Teste Live CDN Google | Assista ao vivo pelo Globoplay": ["São.Paulo/SP..Globo.br"],
    "Transmissão Ao Vivo ABTV - Alagoas | Assista ao vivo pelo Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assista aos telejornais da TV Bahia | Assista ao vivo pelo Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 ao vivo - g1 ao vivo: Transmissão ao vivo online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 Caruaru - Transmissão ao vivo do ABTV online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 RS - Assista aos telejornais da RBS TV online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 SC - AO VIVO: Assista aos telejornais da NSC TV online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "G1 TV Vanguarda Ao Vivo | Assista ao vivo pelo Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 ES - Transmissão ao vivo do jornal Regional no g1 ES online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "TV Integração Juiz de Fora - Transmissão ao vivo | Assista ao vivo pelo Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 Triângulo Mineiro - TV Integração Uberlândia - Transmissão ao vivo online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 Triângulo Mineiro - TV Integração Uberaba - Transmissão ao vivo online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 AC - Assista aos jornais da Rede Amazônica online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir G1 PA - Assista aos telejornais da TV Liberal online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir CBN - CBN SP online | Globoplay": ["São.Paulo/SP..Globo.br"],
    "Assistir CBN - CBN RJ online | Globoplay": ["São.Paulo/SP..Globo.br"],

    # === Brazil ===
    "Rede Vida": ["São.Paulo/SP..Rede.Vida.br"],
    "Rede Vida (Oficial 480p)": ["São.Paulo/SP..Rede.Vida.br"],
    "Rede Vida (Oficial 240p)": ["São.Paulo/SP..Rede.Vida.br"],
}

# Skip channels with no EPG available anywhere
SKIP_CHANNELS = {
    "Video Tracking flood threats in Texas; dangerous heat coast-to-coast; wildfire smoke moving into the US | Watch Live News on ABCNL",
}


def normalize(text):
    if not text:
        return ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_url(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = resp.read()
            if url.endswith(".gz"):
                data = gzip.decompress(data)
            return data.decode("utf-8")
    except Exception as e:
        print(f"  Erro ao baixar {url}: {e}")
        return None


def get_channels_from_m3u(m3u_path):
    channels = OrderedDict()
    current_extinf = None
    current_tvg_id = None
    current_display = None
    with open(m3u_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#EXTINF"):
                current_extinf = line
                id_m = re.search(r'tvg-id="([^"]*)"', line)
                current_tvg_id = id_m.group(1).strip() if id_m else ""
                name_m = re.search(r',(.+)$', line)
                current_display = name_m.group(1).strip() if name_m else ""
            elif current_extinf and line and not line.startswith("#"):
                key = current_display if current_display else current_tvg_id
                if key:
                    channels[key] = {"tvg_id": current_tvg_id, "extinf": current_extinf, "url": line}
                current_extinf = None
                current_tvg_id = None
                current_display = None
    return channels


def find_epg_channel(epg_id_pattern, epg_roots):
    pattern = normalize(epg_id_pattern)
    if not pattern:
        return None, None
    for root_idx, root in enumerate(epg_roots):
        for ch in root.findall("channel"):
            ch_id = ch.get("id", "")
            if normalize(ch_id) == pattern:
                return ch_id, root_idx
    return None, None


def main():
    print("=" * 60)
    print("Gerador de EPGFULL.xml.gz - filtrado pelo M3U")
    print("=" * 60)

    print(f"\n1. Baixando M3U de: {M3U_URL}")
    m3u_content = fetch_url(M3U_URL)
    if m3u_content:
        with open(M3U_PATH, "w", encoding="utf-8") as f:
            f.write(m3u_content)
        print("   M3U atualizado com sucesso")
    else:
        print("   Usando M3U local existente")

    print("\n2. Lendo canais do M3U...")
    m3u_channels = get_channels_from_m3u(M3U_PATH)
    print(f"   {len(m3u_channels)} canais encontrados no M3U")

    print("\n3. Baixando fontes EPG...")
    epg_roots = []
    for url in EPG_URLS:
        fname = url.split("/")[-1]
        print(f"   {fname}...", end=" ", flush=True)
        content = fetch_url(url)
        if not content:
            print("FALHOU")
            continue
        try:
            tree = ET.parse(StringIO(content))
            epg_roots.append(tree.getroot())
            count = len(tree.getroot().findall("channel"))
            prog_count = len(tree.getroot().findall("programme"))
            print(f"OK ({count} canais, {prog_count} programas)")
        except Exception as e:
            print(f"ERRO: {e}")

    if not epg_roots:
        print("\n   ERRO: Nenhuma fonte EPG carregada!")
        return

    print("\n4. Mapeando canais do M3U para fontes EPG...")
    channel_map = {}
    skipped = []
    unmapped = []

    for display_name, info in m3u_channels.items():
        if display_name in SKIP_CHANNELS:
            skipped.append(display_name)
            continue

        epg_ids = CHANNEL_MAP.get(display_name)
        found = False

        if epg_ids:
            for epg_id in epg_ids:
                src_id, src_root_idx = find_epg_channel(epg_id, epg_roots)
                if src_id:
                    channel_map[display_name] = (src_id, src_root_idx)
                    print(f"   OK   {display_name} -> {src_id}")
                    found = True
                    break

        if not found and info["tvg_id"]:
            src_id, src_root_idx = find_epg_channel(info["tvg_id"], epg_roots)
            if src_id:
                channel_map[display_name] = (src_id, src_root_idx)
                print(f"   OK   {display_name} -> {src_id} (via tvg-id)")
                found = True

        if not found:
            unmapped.append(display_name)

    print(f"\n   Resumo:")
    print(f"   Mapeados: {len(channel_map)}/{len(m3u_channels)}")
    print(f"   Sem EPG:  {len(unmapped)}")
    print(f"   Pulados:  {len(skipped)}")

    print("\n5. Construindo XML filtrado...")
    tv_root = ET.Element("tv", {
        "generator-info-name": "JCTV EPG Generator",
        "source-info-url": "https://epgshare01.online",
    })

    added_channels = set()

    for name, (src_id, src_root_idx) in channel_map.items():
        if src_id in added_channels:
            continue
        epg_root = epg_roots[src_root_idx]
        for ch in epg_root.findall("channel"):
            if ch.get("id") == src_id:
                new_ch = ET.SubElement(tv_root, "channel", id=src_id)
                dn = ch.find("display-name")
                if dn is not None and dn.text:
                    ET.SubElement(new_ch, "display-name").text = dn.text
                icon = ch.find("icon")
                if icon is not None:
                    new_ch.append(icon)
                added_channels.add(src_id)
                break

    print("   Copiando programas...")
    matched_progs = 0
    for name, (src_id, src_root_idx) in channel_map.items():
        epg_root = epg_roots[src_root_idx]
        for prog in epg_root.findall("programme"):
            if prog.get("channel", "") == src_id:
                new_prog = ET.SubElement(tv_root, "programme", {
                    "channel": src_id,
                    "start": prog.get("start", ""),
                    "stop": prog.get("stop", ""),
                })
                for child in prog:
                    new_prog.append(child)
                matched_progs += 1

    print(f"   Programas copiados: {matched_progs}")

    print(f"\n6. Salvando {OUTPUT}...")
    xml_str = ET.tostring(tv_root, encoding="utf-8")
    parsed = minidom.parseString(xml_str)
    pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

    with gzip.open(OUTPUT, "wb") as f:
        f.write(pretty_xml)

    total_channels = len(list(tv_root.findall("channel")))
    total_programmes = len(list(tv_root.iter("programme")))
    size_kb = os.path.getsize(OUTPUT) / 1024

    print(f"\n{'=' * 60}")
    print(f"Concluido! {OUTPUT}:")
    print(f"  Canais: {total_channels}")
    print(f"  Programas: {total_programmes}")
    print(f"  Tamanho: {size_kb:.1f} KB")
    print(f"  Mapeados: {len(channel_map)}/{len(m3u_channels)}")
    print(f"{'=' * 60}")

    if unmapped:
        print(f"\nCanais sem EPG ({len(unmapped)}):")
        for name in unmapped:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
