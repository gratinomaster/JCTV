#!/usr/bin/env python3
"""Gera o EPGNEWS.xml.gz com os canais presentes no lista5.m3u.

Fonte: epgshare01 (arquivo epg_ripper_US2.xml.gz), que publica a grade
atualizada diariamente (janela de ~5 dias). Os tvg-ids da playlist sao lidos
direto do lista5.m3u e batem com os IDs publicados pela fonte, garantindo que
o EPG funcione direto (ex.: ABC.News.Live.us2, CNN.HD.us2, MS.NOW.HD.us2).

Retencao: ontem ate hoje+8 dias. Saida: XMLTV valido, comprimido em gzip,
compativel com TiviMate/Kodi (todo <programme> referencia um <channel>).
"""
import datetime
import gzip
import html
import re
import sys
import time
import urllib.request
import xml.sax.saxutils as sax

M3U = "lista5.m3u"
OUTPUT = "EPGNEWS.xml.gz"
SOURCE_URL = "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"

# Nomes/logos usados quando a playlist nao traz tvg-name/tvg-logo.
FALLBACK_NAMES = {
    "ABC.News.Live.us2": "ABC News Live",
    "CBS.News.National.Stream.us2": "CBS News 24/7",
    "Fox.News.Channel.HD.us2": "Fox News Channel",
    "Fox.Business.HD.us2": "Fox Business",
    "MS.NOW.HD.us2": "MS NOW",
    "CNN.HD.us2": "CNN",
    "NBC.East.Stream.us2": "NBC News NOW",
    "Bloomberg.HD.us2": "Bloomberg TV",
    "Newsmax.TV.HD.us2": "Newsmax TV",
    "One.America.News.Network.HD.us2": "OANN",
    "i24.News.English.us2": "i24NEWS English",
}

KEEP_BEFORE_DAYS = 1
KEEP_AFTER_DAYS = 8


def fetch_source():
    req = urllib.request.Request(
        SOURCE_URL + "?nocache=" + str(int(time.time())),
        headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return gzip.decompress(r.read()).decode("utf-8", "replace")


def parse_m3u():
    """Le tvg-id/tvg-name/tvg-logo da playlist (ordem do arquivo, sem repetir)."""
    channels = {}
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
            label = s.split(",")[-1].strip() or FALLBACK_NAMES.get(tid, tid)
            name = (name.group(1).strip() if name else "") or FALLBACK_NAMES.get(tid, "")
            channels.setdefault(
                tid,
                {
                    "name": name or label,
                    "logo": logo.group(1).strip() if logo else "",
                    "label": label,
                },
            )
    if not channels:
        print("ERRO: nenhum tvg-id encontrado em", M3U, file=sys.stderr)
        sys.exit(1)
    return channels


def parse_window(data, wanted):
    """Extrai canais e programas alvo como strings XMLTV ja validadas."""
    days_keep = set()
    today = datetime.date.today()
    for off in range(-KEEP_BEFORE_DAYS, KEEP_AFTER_DAYS + 1):
        d = today + datetime.timedelta(days=off)
        days_keep.add(d.strftime("%Y%m%d"))

    found, programmes = set(), []
    prog_re = re.compile(
        r'<programme channel="([^"]+)" start="(\d{14}) [^"]*" stop="(\d{14}) [^"]*">(.*?)</programme>',
        re.S,
    )
    title_re = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
    desc_re = re.compile(r"<desc[^>]*>(.*?)</desc>", re.S)
    sub_re = re.compile(r"<sub-title[^>]*>(.*?)</sub-title>", re.S)
    cat_re = re.compile(r"<category[^>]*>(.*?)</category>", re.S)

    for m in prog_re.finditer(data):
        src_id, st, sp, inner = m.groups()
        if src_id not in wanted or st[:8] not in days_keep:
            continue
        title = title_re.search(inner)
        if not title:
            continue

        def clean(match):
            return sax.escape(html.unescape(match.group(1).strip()))

        t = clean(title)
        d = desc_re.search(inner)
        s = sub_re.search(inner)
        c = cat_re.search(inner)
        programmes.append(
            '<programme start="{st} +0000" stop="{sp} +0000" channel="{ch}">'
            "<title lang=\"en\">{t}</title>{sub}{desc}{cat}</programme>".format(
                st=st, sp=sp, ch=sax.escape(src_id, {'"': "&quot;"}), t=t,
                sub=f'<sub-title lang="en">{clean(s)}</sub-title>' if s else "",
                desc=f'<desc lang="en">{clean(d)}</desc>' if d else "",
                cat=f'<category lang="en">{clean(c)}</category>' if c else "",
            )
        )
        found.add(src_id)
    return found, programmes


def main():
    channels = parse_m3u()
    print("Canais na playlist:", ", ".join(channels))
    print("Baixando", SOURCE_URL)
    data = fetch_source()
    print("Fonte:", len(data) // 1024, "KB")
    found, programmes = parse_window(data, set(channels))
    missing = set(channels) - found
    if missing:
        print("AVISO: sem dados na fonte para:", ", ".join(sorted(missing)), file=sys.stderr)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tv generator-info-name="JCTV EPG Generator" '
           'generator-info-url="https://github.com/gratinomaster/JCTV">']
    for tid, meta in channels.items():
        out.append(f'  <channel id="{sax.escape(tid, {chr(34): "&quot;"})}">')
        out.append(f'    <display-name lang="en">{sax.escape(meta["name"])}</display-name>')
        if meta["logo"]:
            out.append(f'    <icon src="{sax.escape(meta["logo"], {chr(34): "&quot;"})}" />')
        out.append("  </channel>")
    out.extend(programmes)
    out.append("</tv>")
    xml = "\n".join(out) + "\n"
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(xml)
    print(f"{OUTPUT}: {len(programmes)} programas, "
          f"{len(found)}/{len(channels)} canais com guia")


if __name__ == "__main__":
    main()
