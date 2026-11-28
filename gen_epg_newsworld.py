#!/usr/bin/env python3
"""Gera EPGFULL.xml.gz somente com os canais do NEWSWORLDNOVOS.m3u.

Os dois canais da playlist (US Capitol Cam e Pentagon) sao cameras/lives sem
grade em nenhuma fonte publica de XMLTV (epgshare01, iptv-epg.org, epg.pw).
Para o guia nao ficar vazio no TiviMate/Kodi, o script publica programacao
continua "Live / 24/7" (blocos horarios) para hoje, amanha e os dias seguintes.

Saida: XMLTV valido e gzip, com os tvg-ids exatamente como no M3U, sobrescrevendo
qualquer EPGFULL.xml.gz existente.
"""
import datetime
import gzip
import re
import sys
import xml.sax.saxutils as sax

M3U = "NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"
DAYS = 4  # hoje + amanha + 2 dias
SLOT_MINUTES = 60

FALLBACK = {
    "USCapitol.us": ("US Capitol Cam", "Live from the U.S. Capitol"),
    "464944": ("PENTAGONO USA", "Live from the U.S. Pentagon"),
}


def escape_attr(value):
    return sax.escape(value, {'"': "&quot;"})


def parse_m3u():
    channels = []
    with open(M3U, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s.startswith("#EXTINF"):
                continue
            tid = re.search(r'tvg-id="([^"]+)"', s)
            if not tid or not tid.group(1).strip():
                continue
            tid = tid.group(1).strip()
            name = re.search(r'tvg-name="([^"]*)"', s)
            logo = re.search(r'tvg-logo="([^"]*)"', s)
            label = s.split(",")[-1].strip()
            fallback_name, fallback_desc = FALLBACK.get(tid, (label, "Live"))
            channels.append({
                "id": tid,
                "name": (name.group(1).strip() if name and name.group(1).strip()
                         else fallback_name or label),
                "label": label or fallback_name,
                "logo": logo.group(1).strip() if logo else "",
                "desc": fallback_desc,
            })
    if not channels:
        print("ERRO: nenhum tvg-id encontrado em", M3U, file=sys.stderr)
        sys.exit(1)
    return channels


def build_xml(channels):
    now = datetime.datetime.now(datetime.timezone.utc)
    start = datetime.datetime(now.year, now.month, now.day, tzinfo=datetime.timezone.utc)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tv generator-info-name="JCTV EPG Generator" '
           'generator-info-url="https://github.com/gratinomaster/JCTV">']

    for ch in channels:
        out.append(f'  <channel id="{escape_attr(ch["id"])}">')
        out.append(f'    <display-name lang="en">{sax.escape(ch["name"])}</display-name>')
        if ch["logo"]:
            out.append(f'    <icon src="{escape_attr(ch["logo"])}" />')
        out.append("  </channel>")

    programmes = 0
    for day in range(DAYS):
        day_start = start + datetime.timedelta(days=day)
        for slot in range(24 * 60 // SLOT_MINUTES):
            a = day_start + datetime.timedelta(minutes=slot * SLOT_MINUTES)
            b = a + datetime.timedelta(minutes=SLOT_MINUTES)
            st = a.strftime("%Y%m%d%H%M%S") + " +0000"
            sp = b.strftime("%Y%m%d%H%M%S") + " +0000"
            for ch in channels:
                out.append(
                    f'  <programme start="{st}" stop="{sp}" '
                    f'channel="{escape_attr(ch["id"])}">'
                    f'<title lang="en">{sax.escape(ch["name"])} - Live</title>'
                    f'<desc lang="en">{sax.escape(ch["desc"])}</desc>'
                    f'<category lang="en">Live</category>'
                    f'</programme>'
                )
                programmes += 1
    out.append("</tv>")
    return "\n".join(out) + "\n", programmes


def main():
    channels = parse_m3u()
    print("Canais na playlist:", ", ".join(c["id"] for c in channels))
    xml, programmes = build_xml(channels)
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(xml)
    print(f"{OUTPUT}: {len(channels)} canais, {programmes} programas "
          f"(hoje + {DAYS - 1} dias)")


if __name__ == "__main__":
    main()
