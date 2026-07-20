#!/usr/bin/env python3
import re, gzip, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from io import BytesIO

M3U_FILE = "NEWSWORLDNOVOS.m3u"
OUTPUT_GZ = "EPGFULL.xml.gz"

EPG_SOURCES = [
    ("epg_RU", "https://epg.pw/xmltv/epg_RU.xml.gz"),
    ("epg_NL", "https://iptv-epg.org/files/epg-nl.xml.gz"),
    ("epg_AU", "https://epg.pw/xmltv/epg_AU.xml.gz"),
    ("epg_JP", "https://epg.pw/xmltv/epg_JP.xml.gz"),
    ("epg_UA", "https://epg.pw/xmltv/epg_UA.xml.gz"),
    ("epg_BY", "https://epg.pw/xmltv/epg_BY.xml.gz"),
    ("epgshare_TH", "https://epgshare01.online/epgshare01/epg_ripper_TH1.xml.gz"),
]

M3U_TO_EPG_MAP = {
    "RTVDrenthe.nl": ["TVDrenthe.nl"],
    "RTVMaastricht.nl": ["L1TV.nl"],
    "RTVNoord.nl": ["TVNoord.nl"],
    "RTVNoordExtra.nl": ["TVNoord.nl"],
    "RTVOost.nl": ["TVOost.nl"],
    "RTVPurmerend.nl": ["AT5.nl", "NHNieuws.nl"],
    "RTVRijnmond.nl": ["TVRijnmond.nl"],
    "RTVRijnstreekTV.nl": ["TVWest.nl"],
    "RTVUtrecht.nl": ["RTVUtrecht.nl"],
    "RTVWesterwolde.nl": ["TVGelderland.nl"],
    "HorseandCountry.au": ["HorseAndCountryTV.nl"],
    "NHKWorld.jp": ["10703"],
    "AlJazeera.qa": ["AljazeeraEnglish.nl", "Aljazeera.nl"],
    "HopeTV.ru": ["412065"],
    "MaturTV.ru": ["7520"],
    "MTVVolgograd.ru": ["6072"],
    "MuzSoyuz.ru": ["7313"],
    "NizhniyNovgorod24.ru": ["6022"],
    "NTM.ru": ["5930"],
    "NTS.ru": ["5739"],
    "FirstMusicChannel.by": ["5975"],
    "Prosveshchenie.ru": ["7055"],
    "LanetTV.ua": ["Lanet.ua", "Lanet.TV.ua", "lanet-tv.ua"],
    "ThaiPBS.th": ["Thai.PBS.th", "thaipbs.th", "ThaiPBS.or.th"],
}

def extract_tvg_ids(m3u_path):
    ids = set()
    with open(m3u_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#EXTINF'):
                m = re.search(r'tvg-id="([^"]+)"', line)
                if m:
                    ids.add(m.group(1))
    return ids

def download(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req, timeout=timeout)
    data = resp.read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return data

def main():
    keep_ids = extract_tvg_ids(M3U_FILE)
    print(f"IDs no M3U ({len(keep_ids)}): {sorted(keep_ids)}")

    all_channels = {}
    all_programs = {}

    for name, src in EPG_SOURCES:
        try:
            data = download(src)
            root = ET.fromstring(data)
            for ch in root.findall('channel'):
                cid = ch.get('id', '')
                if cid not in all_channels:
                    all_channels[cid] = ch
            for prog in root.findall('programme'):
                ch = prog.get('channel', '')
                if ch not in all_programs:
                    all_programs[ch] = []
                all_programs[ch].append(prog)
            print(f"  {name}: {len(root.findall('channel'))} canais, {len(root.findall('programme'))} programas")
        except Exception as e:
            print(f"  Erro {name}: {e}")

    merged = ET.Element('tv')
    merged.set('generator-info-name', 'JCTV EPG Generator')
    matched = set()

    for m3u_id in sorted(keep_ids):
        found = False
        if m3u_id in all_channels:
            merged.append(all_channels[m3u_id])
            for p in all_programs.get(m3u_id, []):
                merged.append(p)
            matched.add(m3u_id)
            found = True

        if not found and m3u_id in M3U_TO_EPG_MAP:
            for alt_id in M3U_TO_EPG_MAP[m3u_id]:
                if alt_id in all_channels:
                    ch_elem = all_channels[alt_id]
                    new_ch = ET.Element('channel', id=m3u_id)
                    for child in ch_elem:
                        new_ch.append(child)
                    merged.append(new_ch)
                    for p in all_programs.get(alt_id, []):
                        attrs = {'channel': m3u_id, 'start': p.get('start', ''), 'stop': p.get('stop', '')}
                        new_p = ET.Element('programme', **attrs)
                        for child in p:
                            new_p.append(child)
                        merged.append(new_p)
                    matched.add(m3u_id)
                    found = True
                    break

    missing = keep_ids - matched
    print(f"\nCanais com EPG: {len(matched)}/{len(keep_ids)}")
    if missing:
        print(f"Sem EPG: {sorted(missing)}")
    for m3u_id in sorted(keep_ids):
        status = "✓" if m3u_id in matched else "✗"
        print(f"  {status} {m3u_id}")

    tree = ET.ElementTree(merged)
    ET.indent(tree, space="  ")
    buf = BytesIO()
    with gzip.open(buf, 'wb') as f:
        tree.write(f, encoding='utf-8', xml_declaration=True)
    with open(OUTPUT_GZ, 'wb') as f:
        f.write(buf.getvalue())

    now = datetime.now(timezone.utc)
    today = now.strftime('%Y%m%d')
    tomorrow = (now + timedelta(days=1)).strftime('%Y%m%d')
    pt = sum(1 for p in merged.findall('programme') if p.get('start','').startswith(today))
    pm = sum(1 for p in merged.findall('programme') if p.get('start','').startswith(tomorrow))
    print(f"\n{OUTPUT_GZ}: {len(buf.getvalue())} bytes")
    print(f"Canais: {len(merged.findall('channel'))}")
    print(f"Programas hoje ({today}): {pt}")
    print(f"Programas amanhã ({tomorrow}): {pm}")

if __name__ == '__main__':
    main()
