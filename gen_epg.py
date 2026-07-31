#!/usr/bin/env python3
"""Gera EPGFULL.xml.gz com APENAS os canais que existem no NEWSWORLDNOVOS.m3u.

Fonte principal de programacao: KORYO.TV (https://koryo.tv/schedule) que publica
a agenda real da Korean Central Television (KCTV). Como as emissoras da Coreia
do Norte (Ryongnamsan, Mansudae, KCS) nao publicam grade eletronica, os canais
sao incluidos na definicao do guia para o TiviMate reconhece-los, e os
programas entram conforme a fonte disponibiliza.

Se o arquivo EPGFULL.xml.gz ja existir, ele e sobrescrito.
"""
import gzip
import json
import os
import re
import urllib.request
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax
from datetime import datetime, timedelta, timezone

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"
KORYO_EPG_URL = "https://koryo.tv/api/epg/b2ad0bb59619601b6dd7069a.dat"
KORYO_INDEX = "https://koryo.tv/assets/index-CFdq27ZA.js"
KORYO_HEADER = {
    "X-Koryo-Epg": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://koryo.tv/schedule",
}
GLOBO_EPG = "GLOBOEPG.xml.gz"
PYONGYANG = timezone(timedelta(hours=9))

KORYO_TO_TVG = {"kctv": "KCTV"}


def http_get(url, headers=None, timeout=90):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_m3u(data):
    channels = {}
    for line in data.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        tvg_id = re.search(r'tvg-id="([^"]*)"', line)
        tvg_name = re.search(r'tvg-name="([^"]*)"', line)
        tvg_logo = re.search(r'tvg-logo="([^"]*)"', line)
        cid = tvg_id.group(1) if tvg_id else ""
        if cid and cid not in channels:
            channels[cid] = {
                "name": tvg_name.group(1) if tvg_name else cid,
                "logo": tvg_logo.group(1) if tvg_logo else "",
            }
    return channels


def fetch_koryo():
    url = KORYO_EPG_URL
    try:
        raw = http_get(url, headers=KORYO_HEADER)
    except Exception as e:
        print(f"    ERRO no endpoint koryo ({e}); tentando descobrir a URL nova...")
        raw = None
        try:
            js = http_get(KORYO_INDEX, timeout=30).decode("utf-8", errors="ignore")
            m = re.search(r"/api/epg/[a-f0-9]+\.dat", js)
            if m:
                raw = http_get("https://koryo.tv" + m.group(0), headers=KORYO_HEADER)
        except Exception as e2:
            print(f"    ERRO ao descobrir endpoint novo: {e2}")
    if not raw:
        raise RuntimeError("Nao foi possivel baixar o EPG do KORYO.TV")
    data = gzip.decompress(raw).decode("utf-8", errors="ignore")
    return json.loads(data).get("events", [])


def iso_to_xmltv(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(PYONGYANG)
    return dt.strftime("%Y%m%d%H%M%S") + " +0900"


def build_programme(ev, tvg_id):
    title = ev.get("titleEn") or ev.get("title") or "Sem titulo"
    lang = "en" if ev.get("titleEn") else "ko"
    parts = [f'  <programme start="{iso_to_xmltv(ev["startUtc"])}" '
             f'stop="{iso_to_xmltv(ev["endUtc"])}" channel="{tvg_id}">']
    parts.append(f'    <title lang="{lang}">{sax.escape(title)}</title>')
    if ev.get("category"):
        parts.append(f'    <category lang="en">{sax.escape(ev["category"])}</category>')
    if ev.get("title") and ev.get("titleEn"):
        parts.append(f'    <sub-title lang="ko">{sax.escape(ev["title"])}</sub-title>')
    parts.append("  </programme>")
    return "\n".join(parts)


def main():
    now = datetime.now(timezone.utc)

    print("=== ETAPA 1: Baixar M3U ===")
    m3u_data = http_get(M3U_URL).decode("utf-8", errors="ignore")
    channels = parse_m3u(m3u_data)
    wanted_ids = list(channels.keys())
    print(f"  Canais na playlist: {len(wanted_ids)}")
    for cid in wanted_ids:
        print(f"    - {cid} ({channels[cid]['name']})")

    print("\n=== ETAPA 2: Baixar EPGs ===")
    all_programmes = {}

    print(f"  Baixando KORYO.TV (KCTV): {KORYO_EPG_URL}")
    try:
        events = fetch_koryo()
        print(f"    Eventos recebidos: {len(events)}")
        for ev in events:
            tvg_id = KORYO_TO_TVG.get(ev.get("channel"))
            if not tvg_id or tvg_id not in channels:
                continue
            all_programmes.setdefault(tvg_id, []).append(build_programme(ev, tvg_id))
    except Exception as e:
        print(f"    ERRO: {e}")

    if os.path.exists(GLOBO_EPG):
        try:
            print(f"  Lendo EPG local: {GLOBO_EPG}")
            with gzip.open(GLOBO_EPG, "rt", encoding="utf-8") as f:
                globo = f.read()
            for cid in wanted_ids:
                pat = re.compile(
                    rf'<programme\s+[^>]*channel="{re.escape(cid)}"[^>]*>.*?</programme>',
                    re.DOTALL,
                )
                found = pat.findall(globo)
                if found:
                    all_programmes.setdefault(cid, []).extend(found)
                    print(f"    {cid}: {len(found)} programas (Globo)")
        except Exception as e:
            print(f"    ERRO: {e}")

    print("\n=== ETAPA 3: Montar EPGFULL.xml.gz ===")
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<tv generator-info-name="JCTV EPG Generator" '
                 'generator-info-url="https://github.com/gratinomaster/JCTV">']
    for cid in wanted_ids:
        info = channels[cid]
        chan = [f'  <channel id="{sax.escape(cid)}">']
        chan.append(f'    <display-name>{sax.escape(info["name"])}</display-name>')
        if info["logo"]:
            chan.append(f'    <icon src="{sax.escape(info["logo"])}"/>')
        chan.append("  </channel>")
        xml_parts.append("\n".join(chan))
        for prog in all_programmes.get(cid, []):
            xml_parts.append(prog)
    xml_parts.append("</tv>")
    full_xml = "\n".join(xml_parts) + "\n"

    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(full_xml)
    print(f"  Arquivo gravado: {OUTPUT} ({os.path.getsize(OUTPUT):,} bytes)")

    print("\n=== ETAPA 4: Validar ===")
    with gzip.open(OUTPUT, "rt", encoding="utf-8") as f:
        content = f.read()

    root = ET.fromstring(content)
    ch_count = len(root.findall("channel"))
    prog_count = len(root.findall("programme"))
    print(f"  XML valido (ElementTree OK)")
    print(f"  Canais: {ch_count}")
    print(f"  Programas: {prog_count}")

    pyongyang_now = now.astimezone(PYONGYANG)
    today = pyongyang_now.date()
    tomorrow = today + timedelta(days=1)
    today_s = today.strftime("%Y%m%d")
    tomorrow_s = tomorrow.strftime("%Y%m%d")
    today_progs = 0
    tomorrow_progs = 0
    for prog in root.findall("programme"):
        start = prog.get("start", "")
        if start.startswith(today_s):
            today_progs += 1
        if start.startswith(tomorrow_s):
            tomorrow_progs += 1

    for cid in wanted_ids:
        ch_found = root.find(f'channel[@id="{cid}"]') is not None
        c_progs = sum(1 for p in root.findall(f'programme[@channel="{cid}"]'))
        print(f"    {cid}: {'OK' if ch_found else 'FALTA'} ({c_progs} programas)")

    print(f"  Programas de HOJE   ({today_s}, Pyongyang): {today_progs}")
    print(f"  Programas de AMANHA ({tomorrow_s}, Pyongyang): {tomorrow_progs}")
    if today_progs:
        print("  Teste hoje: OK")
    else:
        print("  Teste hoje: FALHOU")
    if tomorrow_progs:
        print("  Teste amanha: OK")
    else:
        print("  Teste amanha: dados ainda nao publicados pela fonte (saem no fim da transmissao de hoje)")

    print("\n=== CONCLUIDO ===")


if __name__ == "__main__":
    main()
