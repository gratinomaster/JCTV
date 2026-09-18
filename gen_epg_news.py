#!/usr/bin/env python3
"""Gera o EPGNEWS.xml.gz com os canais presentes no lista5.m3u.

Fonte: epgshare01 (arquivo epg_ripper_US2.xml.gz), que publica a grade
atualizada diariamente (janela de ~5 dias). Os tvg-ids da playlist sao os
mesmos IDs publicados pela fonte, garantindo que o EPG funcione direto:

  ABC.News.Live.us2            (ABC News Live)
  CBS.News.National.Stream.us2 (CBS News 24/7)
  Fox.News.Channel.HD.us2      (FOX News Channel)
  Fox.Business.HD.us2          (Fox Business Network)

Retencao: ontem ate hoje+7 dias. Saida: XMLTV valido, comprimido em gzip,
compativel com TiviMate/Kodi (todo <programme> referencia um <channel>).
"""
import gzip
import re
import sys
import time
import urllib.request
import xml.sax.saxutils as sax

M3U = "lista5.m3u"
OUTPUT = "EPGNEWS.xml.gz"
SOURCE_URL = "https://epgshare01.online/epgshare01/epg_ripper_US2.xml.gz"

# tvg-id da playlist = id da fonte
MAP = {
    "ABC.News.Live.us2": "ABC.News.Live.us2",
    "CBS.News.National.Stream.us2": "CBS.News.National.Stream.us2",
    "Fox.News.Channel.HD.us2": "Fox.News.Channel.HD.us2",
    "Fox.Business.HD.us2": "Fox.Business.HD.us2",
}

LOGOS = {
    "ABC.News.Live.us2": "https://raw.githubusercontent.com/gratinomaster/JCTV/main/abcnews.jpg",
    "CBS.News.National.Stream.us2": "https://raw.githubusercontent.com/gratinomaster/JCTV/main/cbsnews.jpg",
    "Fox.News.Channel.HD.us2": "https://raw.githubusercontent.com/gratinomaster/JCTV/main/foxnews.jpg",
    "Fox.Business.HD.us2": "https://raw.githubusercontent.com/gratinomaster/JCTV/main/foxbusiness.jpg",
}

NAMES = {
    "ABC.News.Live.us2": "ABC News Live",
    "CBS.News.National.Stream.us2": "CBS News 24/7",
    "Fox.News.Channel.HD.us2": "FOX News Channel",
    "Fox.Business.HD.us2": "Fox Business Network",
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


def parse_window(data):
    """Extrai canais e programas alvo como strings XMLTV ja validadas."""
    days_keep = set()
    import datetime
    today = datetime.date.today()
    for off in range(-KEEP_BEFORE_DAYS, KEEP_AFTER_DAYS + 1):
        d = today + datetime.timedelta(days=off)
        days_keep.add(d.strftime("%Y%m%d"))

    channels, programmes = {}, []
    prog_re = re.compile(
        r'<programme channel="([^"]+)" start="(\d{14}) [^"]*" stop="(\d{14}) [^"]*">(.*?)</programme>',
        re.S,
    )
    title_re = re.compile(r"<title[^>]*>(.*?)</title>", re.S)
    desc_re = re.compile(r"<desc[^>]*>(.*?)</desc>", re.S)
    sub_re = re.compile(r"<sub-title[^>]*>(.*?)</sub-title>", re.S)
    cat_re = re.compile(r"<category[^>]*>(.*?)</category>", re.S)

    rev = {v: k for k, v in MAP.items()}
    for m in prog_re.finditer(data):
        src_id, st, sp, inner = m.groups()
        if src_id not in rev or st[:8] not in days_keep:
            continue
        ch = rev[src_id]
        title = title_re.search(inner)
        if not title:
            continue
        t = sax.escape(title.group(1).strip())
        d = desc_re.search(inner)
        s = sub_re.search(inner)
        c = cat_re.search(inner)
        programmes.append(
            '<programme start="{st} +0000" stop="{sp} +0000" channel="{ch}">'
            "<title lang=\"en\">{t}</title>{sub}{desc}{cat}</programme>".format(
                st=st, sp=sp, ch=sax.escape(ch, {'"': "&quot;"}), t=t,
                sub=f'<sub-title lang="en">{sax.escape(s.group(1).strip())}</sub-title>' if s else "",
                desc=f'<desc lang="en">{sax.escape(d.group(1).strip())}</desc>' if d else "",
                cat=f'<category lang="en">{sax.escape(c.group(1).strip())}</category>' if c else "",
            )
        )
        channels[ch] = True
    return channels, programmes


def main():
    print("Baixando", SOURCE_URL)
    data = fetch_source()
    print("Fonte:", len(data) // 1024, "KB")
    channels, programmes = parse_window(data)
    missing = set(MAP) - set(channels)
    if missing:
        print("AVISO: sem dados na fonte para:", ", ".join(sorted(missing)), file=sys.stderr)

    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tv generator-info-name="JCTV EPG Generator" '
           'generator-info-url="https://github.com/gratinomaster/JCTV">']
    for ch in MAP:
        out.append(f'  <channel id="{ch}">')
        out.append(f'    <display-name lang="en">{sax.escape(NAMES[ch])}</display-name>')
        out.append(f'    <icon src="{LOGOS[ch]}" />')
        out.append("  </channel>")
    out.extend(programmes)
    out.append("</tv>")
    xml = "\n".join(out) + "\n"
    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(xml)
    print(f"{OUTPUT}: {len(programmes)} programas, "
          f"{len([c for c in MAP if c in channels])}/{len(MAP)} canais com guia")


if __name__ == "__main__":
    main()
