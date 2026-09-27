#!/usr/bin/env python3
"""Valida o EPGFULL.xml.gz gerado: XMLTV valido e compativel com TiviMate
e com o add-on do kodi que mistura varios EPGs (slyguy).

Regras checadas (as mesmas que o TiviMate aplica ao ler a URL do EPG):

  1. .gz integro e XML bem formado, com raiz <tv>.
  2. Nenhum <programme> apontando para um canal inexistente (o TiviMate
     descarta esses programas; o slyguy tambem, mas enche a memoria).
  3. Nenhum <channel> fora da playlist: e o que faz o guia "ficar maior do
     que o necessario".
  4. Todo canal da playlist (tvg-id) presente no guia, com <display-name>
     e com <programme> no dia de hoje e no dia de amanha.
  5. start < stop em todos os programas, com o formato
     AAAAMMDDHHMMSS +HHMM que o TiviMate le.
  6. Relatorio de quantos canais tem guia hoje/amanha, para ver a cobertura.

Uso:  python3 epgfull_check.py [EPGFULL.xml.gz] [NEWSWORLDNOVOS.m3u]
"""
import gzip
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

EPG = sys.argv[1] if len(sys.argv) > 1 else "EPGFULL.xml.gz"
M3U = sys.argv[2] if len(sys.argv) > 2 else "NEWSWORLDNOVOS.m3u"

XMLTV_TIME = re.compile(r"^\d{14} [+-]\d{4}$")
problems = []


def parse_time(s):
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")
    except Exception:
        return None


def m3u_ids(path):
    ids = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("#EXTINF"):
                m = re.search(r'tvg-id="([^"]*)"', line)
                if m and m.group(1):
                    ids.append(m.group(1))
    return ids


def main():
    print("=" * 72)
    print(f"1. Lendo {EPG}")
    with gzip.open(EPG, "rb") as f:
        raw = f.read()
    print(f"   gz OK, {len(raw):,} bytes descomprimidos")
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"   FALHA: XML invalido: {e}")
        return 1
    if root.tag != "tv":
        problems.append(f"raiz <{root.tag}> em vez de <tv>")
    print(f"   XML bem formado, raiz <{root.tag}>")

    channels = root.findall("channel")
    programmes = root.findall("programme")
    defined = {}
    for c in channels:
        cid = c.get("id")
        if cid in defined:
            problems.append(f"channel id duplicado: {cid}")
        names = c.findall("display-name")
        if not names or not (names[0].text or "").strip():
            problems.append(f"canal sem display-name: {cid}")
        defined[cid] = (names[0].text if names else "") or ""
    print(f"   canais: {len(channels)}  |  programas: {len(programmes)}")

    print("\n2. Cruzando com a playlist")
    ids = m3u_ids(M3U)
    want = list(dict.fromkeys(ids))
    extra = [c for c in defined if c not in set(want)]
    missing = [c for c in want if c not in defined]
    print(f"   tvg-ids unicos na playlist: {len(want)}")
    print(f"   canais no guia fora da playlist: {len(extra)}")
    print(f"   canais da playlist sem <channel> no guia: {len(missing)}")
    if extra:
        problems.append(f"{len(extra)} canal(is) no guia fora da playlist: {extra[:5]}")
    if missing:
        problems.append(f"{len(missing)} canal(is) da playlist fora do guia: {missing[:5]}")

    print("\n3. Programa -> canal e formatos de horario")
    orphan = 0
    no_title = 0
    bad_time = 0
    bad_range = 0
    per_channel = defaultdict(list)
    for p in programmes:
        cid = p.get("channel")
        start, stop = p.get("start", ""), p.get("stop", "")
        if not XMLTV_TIME.match(start) or not XMLTV_TIME.match(stop):
            bad_time += 1
        s, e = parse_time(start), parse_time(stop)
        if s and e and e <= s:
            bad_range += 1
        if cid not in defined:
            orphan += 1
            continue
        if p.find("title") is None:
            no_title += 1
        if s:
            per_channel[cid].append((s, e))
    print(f"   programas sem canal correspondente: {orphan}")
    print(f"   programas sem <title>: {no_title}")
    print(f"   horarios fora do formato XMLTV: {bad_time}")
    print(f"   programas com stop <= start: {bad_range}")
    for label, n in (("orfaos", orphan), ("sem title", no_title),
                     ("horario invalido", bad_time), ("stop<=start", bad_range)):
        if n:
            problems.append(f"{n} programa(s) {label}")

    print("\n4. Cobertura de hoje e amanha")
    now = datetime.now(timezone.utc)
    day = Counter()
    days_with = defaultdict(set)
    for cid, items in per_channel.items():
        for s, _e in items:
            day[s.date()] += 1
            days_with[s.date()].add(cid)
    today = now.date()
    for offset in range(0, 4):
        d = today + timedelta(days=offset)
        chans = len(days_with.get(d, ()))
        print(f"   {d} ({'hoje    ' if offset == 0 else 'amanha   ' if offset == 1 else 'depois   '})"
              f" {day.get(d, 0):>5} programas em {chans:>3} canais")
    for label, d in (("hoje", today), ("amanha", today + timedelta(days=1))):
        if not day.get(d):
            problems.append(f"nenhum programa em {label} ({d})")
    with_today = set(days_with.get(today, ())) & set(defined)
    with_both = {c for c in with_today
                 if any(s.date() == today + timedelta(days=1) for s, _ in per_channel[c])}
    print(f"   canais com guia hoje: {len(with_today)}/{len(defined)}")
    print(f"   canais com guia hoje E amanha: {len(with_both)}/{len(defined)}")

    print("\n5. Sobreposicao (o TiviMate mostra o primeiro que encontra)")
    overlaps = 0
    for cid, items in per_channel.items():
        items.sort()
        for (s1, e1), (s2, _e2) in zip(items, items[1:]):
            if e1 and s2 < e1:
                overlaps += 1
    print(f"   pares de programas sobrepostos: {overlaps}")
    if overlaps:
        problems.append(f"{overlaps} par(es) de programas sobrepostos")

    print("\n6. Amostra do que o aparelho vai exibir")
    sample = sorted(with_both)[:8]
    for cid in sample:
        today_items = sorted((s, e) for s, e in per_channel[cid] if s.date() == today)
        now_prog = next(((s, e) for s, e in today_items if s <= now <= (e or s)), None)
        t = root.find(f'.//programme[@channel="{cid}"]')
        title = t.find("title").text if t is not None and t.find("title") is not None else "-"
        if now_prog:
            s, e = now_prog
            prog = next((p for p in programmes if p.get("channel") == cid
                         and parse_time(p.get("start", "")) == s), None)
            name = prog.find("title").text if prog is not None else "-"
            print(f"   {defined[cid][:24]:<24} agora: {s:%H:%M}-{e:%H:%M}  {name[:40]}")
        else:
            print(f"   {defined[cid][:24]:<24} sem programa neste instante")

    print("\n" + "=" * 72)
    if problems:
        print("FALHAS:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("TUDO OK: XMLTV valido, compativel com TiviMate/slyguy, "
          "so com os canais da playlist, com programa para hoje e amanha.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
