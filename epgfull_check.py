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
  7. Como o aparelho ve: programa no ar agora e grade de hoje/amanha no fuso
     do aparelho (o TiviMate converte cada programa para o fuso do aparelho, e
     nao para o fuso gravado no arquivo).

Uso:  python3 epgfull_check.py [EPGFULL.xml.gz] [NEWSWORLDNOVOS.m3u] [fuso]
"""
import gzip
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EPG = sys.argv[1] if len(sys.argv) > 1 else "EPGFULL.xml.gz"
M3U = sys.argv[2] if len(sys.argv) > 2 else "NEWSWORLDNOVOS.m3u"
DEVICE_TZ = ZoneInfo(sys.argv[3] if len(sys.argv) > 3 else "America/Sao_Paulo")

XMLTV_TIME = re.compile(r"^\d{14} [+-]\d{4}$")

# Ordem dos filhos exigida pelo DTD do XMLTV (https://github.com/XMLTV/xmltv).
# O TiviMate e os add-ons do kodi leem por nome e nao quebram com a ordem
# errada, mas o arquivo e recusado por validador estrito e o guia perde as
# tags que nao existem no XMLTV (ex.: <class>).
XMLTV_CHANNEL_ORDER = ("display-name", "icon", "url")
XMLTV_PROGRAMME_ORDER = (
    "title", "sub-title", "desc", "credits", "date", "category", "keyword",
    "language", "orig-language", "length", "icon", "url", "country",
    "episode-num", "video", "audio", "previously-shown", "premiere",
    "last-chance", "new", "subtitles", "rating", "star-rating", "review",
    "image",
)

problems = []


def fora_do_padrao(elem, order):
    """True se `elem` tem tag fora do DTD ou filho fora da ordem."""
    index = {tag: i for i, tag in enumerate(order)}
    pos = [index[c.tag] for c in elem if c.tag in index]
    return len(pos) != len(elem) or pos != sorted(pos)


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
    day_end_of_tomorrow = now.replace(hour=0, minute=0, second=0,
                                      microsecond=0) + timedelta(days=2)

    print("\n5. Sobreposicao, buracos e fuso (o que o aparelho ve na grade)")
    overlaps = 0
    for cid, items in per_channel.items():
        items.sort()
        for (s1, e1), (s2, _e2) in zip(items, items[1:]):
            if e1 and s2 < e1:
                overlaps += 1
    print(f"   pares de programas sobrepostos: {overlaps}")
    if overlaps:
        problems.append(f"{overlaps} par(es) de programas sobrepostos")

    # Buraco de mais de 1h30 dentro de hoje+amanha e o horario em que o
    # TiviMate mostra "sem informacao". A mistura de fontes precisa encher
    # esses espacos, nao so os dias inteiros que faltavam.
    holes = []
    for cid, items in per_channel.items():
        window = sorted((s, e) for s, e in items
                        if s < day_end_of_tomorrow and e > now.replace(
                            hour=0, minute=0, second=0, microsecond=0))
        for (_s1, e1), (s2, _e2) in zip(window, window[1:]):
            if e1 and s2 - e1 > timedelta(minutes=90):
                holes.append((cid, e1, s2, s2 - e1))
    holes.sort(key=lambda h: -h[3])
    print(f"   buracos > 1h30 entre programas hoje/amanha: {len(holes)}")
    for cid, e1, s2, gap in holes[:5]:
        print(f"     {cid[:30]:<30} {e1:%d/%m %H:%M} -> {s2:%d/%m %H:%M} ({gap})")

    # Um canal com parte da grade num fuso e parte em outro mostra um salto
    # de horas no meio da semana; cada canal deve usar um fuso so.
    mixed = sorted(cid for cid, items in per_channel.items()
                   if len({s.utcoffset() for s, _e in items}) > 1)
    print(f"   canais com mais de um fuso: {len(mixed)}"
          + (f" -> {mixed}" if mixed else ""))

    print("\n6. Padrao XMLTV (ordem das tags, como o DTD exige)")
    bad_channels = [c.get("id") for c in channels
                    if fora_do_padrao(c, XMLTV_CHANNEL_ORDER)]
    bad_programmes = [p for p in programmes
                      if fora_do_padrao(p, XMLTV_PROGRAMME_ORDER)]
    # O DTD e <tv> (channel*, programme*): canal depois de programa quebra a
    # leitura de quem valida o arquivo inteiro.
    tags = [c.tag for c in root]
    channel_after_programme = ("programme" in tags
                               and "channel" in tags[tags.index("programme"):])
    print(f"   canais fora do padrao: {len(bad_channels)}")
    print(f"   programas fora do padrao: {len(bad_programmes)}")
    print(f"   canal depois de programa: {channel_after_programme}")
    if bad_channels:
        problems.append(f"{len(bad_channels)} canal(is) fora do padrao XMLTV: "
                        f"{bad_channels[:5]}")
    if bad_programmes:
        problems.append(f"{len(bad_programmes)} programa(s) fora do padrao XMLTV "
                        f"(primeiro: {ET.tostring(bad_programmes[0], encoding='unicode')[:120].strip()})")
    if channel_after_programme:
        problems.append("existe <channel> depois de <programme> (DTD: channel*, programme*)")

    print("\n7. Amostra do que o aparelho vai exibir")
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

    # O TiviMate converte cada programa para o fuso do aparelho, entao a data
    # que o usuario ve e a data local dele e nao a do atributo do arquivo.
    print(f"\n8. Como o aparelho ve (fuso {DEVICE_TZ})")
    now_local = now.astimezone(DEVICE_TZ)
    base = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    on_now = {}
    for p in programmes:
        s = parse_time(p.get("start", ""))
        e = parse_time(p.get("stop", ""))
        if s is None:
            continue
        if e is None or e <= s:
            e = s + timedelta(hours=1)
        s, e = s.astimezone(DEVICE_TZ), e.astimezone(DEVICE_TZ)
        if s <= now_local < e:
            t = p.find("title")
            on_now.setdefault(p.get("channel"),
                              (s, e, (t.text or "").strip() if t is not None else ""))
    print(f"   agora: {len(on_now)}/{len(defined)} canais com programa no ar")
    if not on_now:
        problems.append("nenhum canal com programa no ar neste instante")

    def day_hours(cid, day_start):
        """Horas do dia local cobertas por programas do canal."""
        end = day_start + timedelta(days=1)
        covered = timedelta()
        items = 0
        for s, e in sorted(per_channel.get(cid, ()), key=lambda it: it[0]):
            if s is None:
                continue
            if e is None or e <= s:
                e = s + timedelta(hours=1)
            s, e = s.astimezone(DEVICE_TZ), e.astimezone(DEVICE_TZ)
            if s >= end or e <= day_start:
                continue
            items += 1
            covered += (min(e, end) - max(s, day_start))
        return covered, items

    for offset in (0, 1):
        day_start = base + timedelta(days=offset)
        label = "hoje   " if offset == 0 else "amanha "
        full = partial = empty = 0
        for cid in defined:
            hours, items = day_hours(cid, day_start)
            if items == 0:
                empty += 1
            elif hours >= timedelta(hours=22):
                full += 1
            else:
                partial += 1
        print(f"   {label} {day_start:%d/%m}: {full} canais com dia cheio, "
              f"{partial} parciais, {empty} sem grade")
    for cid in sorted(on_now)[:10]:
        s, e, name = on_now[cid]
        print(f"   {defined[cid][:22]:<22} {s:%H:%M}-{e:%H:%M}  {name[:44]}")

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
