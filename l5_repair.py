#!/usr/bin/env python3
"""Repara o lista5.m3u: EPG valido/atualizado, logos .jpg, anti-virus e streams vivos.

Uso:
    python3 l5_repair.py --check          # so diagnostico, nao escreve
    python3 l5_repair.py                   # repara e reescreve o lista5.m3u
    python3 l5_repair.py --epg-cache /caminho/epg-us.xml.gz

O script:
  * classifica cada entrada (DRM, audio-only, VOD/ENDLIST, duplicata, orfa);
  * roda triagem anti-virus nos payloads (manifest, variante e segmento);
  * testa manifesto -> variante -> segmento com retry;
  * exige tvg-logo .jpg, viva e fora do imgur;
  * exige tvg-id coberto por pelo menos um url-tvg, com guia em D0/D+1/D+2;
  * grava #EXTM3U url-tvg="..." e um #EXTINF acima de cada URL.
"""

import argparse
import gzip
import os
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

import requests

LISTA = "lista5.m3u"
RELATORIO = "lista5.m3u.removidos.txt"
EPG_CACHE = "epg-us.xml.gz"

# Fontes de EPG verificadas. Precisam cobrir today, amanha e depois de amanha.
EPG_URLS = ["https://iptv-epg.org/files/epg-us.xml.gz"]

# Canais do lista5 (grupo NEWS WORLD). stream = manifesto unico por canal.
CHANNELS = [
    {
        "name": "ABC News Live",
        "tvg_id": "ABCNewsLive.us",
        "tvg_logo": ("https://s.abcnews.com/images/Live/"
                     "abc_news_live-abc-ml-250210_1739199021469_hpMain_16x9_608.jpg"),
        "group": "NEWS WORLD",
        "url": ("https://abcnews-livestreams.akamaized.net/out/v1/"
                "6a597119dbd5428a82dc11a2f514a1a2/abcn-live-10-cmaf-manifest/"
                "abcn-live-10-index.m3u8"),
    },
    {
        "name": "CBS News 24/7",
        "tvg_id": "CBSNews.us",
        "tvg_logo": ("https://assets2.cbsnewsstatic.com/hub/i/r/2024/04/16/"
                     "0fb75ad2-a909-44bb-87dc-86b9d51cbeb2/thumbnail/1280x720/"
                     "949f3d3fef16f9c113e3048c6aef229f/"
                     "247-key-channelthumbnail-1920x1080.jpg"),
        "group": "NEWS WORLD",
        "url": ("https://cbsn-us.cbsnstream.cbsnews.com/out/v1/"
                "55a8648e8f134e82a470f83d562deeca/master.m3u8"),
    },
]

# Trocas de URL feitas na triagem (canal, justificativa).
SUBSTITUTIONS = [
    ("CBS News 24/7",
     "dai.google.com/linear/hls/pa/event/<sessao>/variant/... -> "
     "cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8. "
     "O caminho antigo fixava as variantes de uma sessao DAI que expira; "
     "a origem nova e o master HLS permanente da propria CBS News."),
    ("ABC News Live",
     "linear-abcnews-.../dvt2=exp=.../cmaf-cenc/... -> "
     "abcnews-livestreams.akamaized.net/out/v1/.../abcn-live-10-index.m3u8. "
     "O caminho antigo era Disney+ com DRM cmaf-cenc (Widevine) e token exp=1791225014 "
     "(2026-10-05 18:30 UTC); o novo e o master clear oficial da ABC News."),
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT = 15
RETRIES = 3
WORKERS = 6

DANGEROUS_EXT = (".exe", ".scr", ".bat", ".cmd", ".com", ".js", ".jar", ".msi",
                 ".vbs", ".ps1", ".hta", ".apk", ".dll", ".sh", ".pif", ".apk")
MAGIC = {
    b"MZ": "PE/executavel Windows",
    b"\x7fELF": "ELF/executavel Linux",
    b"#!": "script executavel",
    b"PK\x03\x04": "pacote ZIP",
    b"\xd0\xcf\x11\xe0": "OLE2 (doc/macro)",
    b"\xca\xfe\xba\xbe": "classe Java",
    b"Rar!": "arquivo RAR",
    b"7z\xbc\xaf\x27\x1c": "arquivo 7z",
}
BAD_LOGO_HOSTS = ("imgur.com", "i.imgur.com", "imgur.io")

sess = requests.Session()
sess.headers.update({"User-Agent": UA, "Accept": "*/*"})


# --------------------------------------------------------------------------- #
# triagem anti-virus
# --------------------------------------------------------------------------- #
def screen(content, ctype, url):
    """(True, motivo) se o payload parece malicioso / nao-midia."""
    low = urlparse(url).path.lower()
    for ext in DANGEROUS_EXT:
        if low.endswith(ext):
            return True, "extensao suspeita %s" % ext
    for magic, why in MAGIC.items():
        if content[:len(magic)] == magic:
            return True, "binario executavel (%s)" % why
    head = content[:2048].lower()
    if b"<html" in head or b"<!doctype html" in head:
        return True, "pagina HTML injetada"
    if "mpegurl" not in ctype:
        if b"<?php" in head:
            return True, "payload PHP"
        if b"powershell" in head or b"cmd.exe" in head:
            return True, "payload de shell"
        if b"<script" in head:
            return True, "HTML com script embutido"
    return False, ""


def is_media(resp):
    """Valida MPEG-TS (sync 0x47 a cada 188 B) ou fragmento fMP4 / MP3."""
    ctype = resp.headers.get("Content-Type", "").lower()
    b = resp.content
    if b"<html" in b[:512].lower() or b"<!doctype" in b[:512].lower():
        return False
    if len(b) < 200:
        return False
    if b[0] == 0x47:                       # MPEG-TS
        off, good = 0, 0
        while off < len(b) and good < 6:
            if b[off] != 0x47:
                break
            off += 188
            good += 1
        if good >= 3 or len(b) < 188 * 8:
            return True
    if b"ftyp" in b[:64] or b"moof" in b[:64] or b"styp" in b[:64]:
        return True
    if len(b) > 1 and b[0] == 0xFF and (b[1] & 0xF0) == 0xF0:
        return True
    if b"ID3" in b[:32]:
        return True
    return "mp2t" in ctype


def is_playlist(resp):
    ctype = resp.headers.get("Content-Type", "").lower()
    if "mpegurl" in ctype or "x-mpegurl" in ctype:
        return True
    return resp.content.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U")


def uris_of(text):
    return [l.strip() for l in text.splitlines()
            if l.strip() and not l.strip().startswith("#")]


def variants_of(text):
    """(bandwidth, uri) de cada #EXT-X-STREAM-INF."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        bw = 0
        for tok in line.split(":", 1)[-1].split(","):
            if "BANDWIDTH=" in tok:
                try:
                    bw = int(tok.split("=")[1])
                except ValueError:
                    bw = 0
        for nxt in lines[i + 1:]:
            nxt = nxt.strip()
            if nxt and not nxt.startswith("#"):
                out.append((bw, nxt))
                break
    return out


def probe(url, depth=0):
    """Segue manifesto -> variante -> segmento. (ok, motivo)."""
    if depth > 4:
        return False, "playlist muito aninhada"
    resp = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
    if resp.status_code >= 400:
        return False, "HTTP %d" % resp.status_code

    bad, why = screen(resp.content, resp.headers.get("Content-Type", "").lower(), url)
    if bad:
        return False, "ANTIVIRUS: %s" % why

    if not is_playlist(resp):
        return (True, "midia direta") if is_media(resp) else (False, "conteudo nao-playlist")

    text = resp.content.decode("utf-8", "replace")
    if "#EXT-X-STREAM-INF" in text:
        cands = sorted(variants_of(text))
        if not cands:
            return False, "manifesto sem variantes"
        reasons = []
        for bw, variant in cands:
            ok, reason = probe(urljoin(url, variant), depth + 1)
            if ok:
                return True, "manifesto ok (%d variantes)" % len(cands)
            reasons.append(reason)
        return False, "variantes falharam: %s" % reasons[0]

    segs = uris_of(text)
    if not segs:
        return False, "playlist sem segmentos"
    for ref in reversed(segs[-3:]):
        full = urljoin(url, ref)
        try:
            s = sess.get(full, timeout=TIMEOUT)
        except requests.RequestException:
            continue
        if s.status_code >= 400:
            continue
        bad, why = screen(s.content, s.headers.get("Content-Type", "").lower(), full)
        if bad:
            return False, "ANTIVIRUS: %s" % why
        if is_media(s):
            return True, "playlist ok"
    return False, "nenhum segmento valido"


def verify(url):
    last = "desconhecido"
    for attempt in range(RETRIES):
        try:
            return probe(url)
        except requests.HTTPError as e:
            last = "HTTP %d" % e.response.status_code if e.response is not None else "HTTP"
        except requests.RequestException as e:
            last = type(e).__name__
        except Exception as e:                      # noqa: BLE001
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(1 + attempt)
    return False, last


# --------------------------------------------------------------------------- #
# auditoria do arquivo atual
# --------------------------------------------------------------------------- #
def parse(path):
    """-> (header, [(attrs, url, linhas_extras)]). Garante #EXTINF acima de cada URL."""
    header, entries, cur = [], [], None
    for raw in open(path, encoding="utf-8", errors="replace").read().splitlines():
        line = raw.rstrip()
        if line.startswith("#EXTINF"):
            if cur and cur[1] is None:
                cur[1] = ""                       # #EXTINF sem URL -> orfa
                entries.append(cur)
            cur = [line, None, []]
        elif not line.strip():
            continue
        elif line.startswith("#"):
            if cur is None:
                header.append(line)
            else:
                cur[2].append(line)
        else:
            if cur is None:
                cur = ["(sem #EXTINF)", line, []]
                entries.append(cur)
            else:
                if cur[1] is None:
                    cur[1] = line
                else:
                    cur[2].append(line)            # URL extra sob o mesmo EXTINF
            entries.append(cur)
            cur = None
    if cur and cur[1] is None:
        entries.append(cur)
    return header, entries


def attr(line, name):
    m = re.search(r'%s="([^"]*)"' % re.escape(name), line)
    return m.group(1) if m else ""


def audit(entries):
    """Classifica cada entrada. -> lista de dicts."""
    seen = Counter()
    rows = []
    for extinf, url, extras in entries:
        name = extinf.rsplit(",", 1)[-1].strip()
        if url:
            seen[url] += 1
        path = urlparse(url).path.lower() if url else ""
        reason = None

        if not url:
            reason = "#EXTINF sem URL"
        elif url.startswith("#"):
            reason = "URL comentario solta"
        elif re.match(r"^https?://", url) is None:
            reason = "esquema de URL invalido"
        elif url.count("/") < 3 or "." not in urlparse(url).netloc:
            reason = "URL sem host valido"
        elif "cmaf-cenc" in url or "widevine" in url or "license" in path:
            reason = "DRM (cmaf-cenc/Widevine) - exige licenca, nao toca em IPTV"
        elif re.search(r"/audio[-_]", path) or "audio-aac" in url:
            reason = "somente audio (sem video)"
        elif path.endswith("_complete.m3u8") or "complete-" in url:
            reason = "VOD/ENDLIST (arquivo arquivado, nao e ao vivo)"
        elif url.startswith("https://dai.google.com/linear/hls/pa/"):
            reason = "token de sessao DAI 'pa' com variante fixa (expira)"
        elif "dvt2=exp=" in url:
            reason = "token Disney+ com expiracao embutida"
        elif seen[url] > 1:
            reason = "URL duplicada"

        rows.append({"extinf": extinf, "url": url or "", "extras": extras,
                     "name": name, "logo": attr(extinf, "tvg-logo"),
                     "tvg_id": attr(extinf, "tvg-id"),
                     "group": attr(extinf, "group-title"), "reason": reason})
    return rows


# --------------------------------------------------------------------------- #
# EPG
# --------------------------------------------------------------------------- #
def fetch_epg(url, cache):
    if os.path.exists(cache) and os.path.getsize(cache) > 1024:
        return cache
    print("baixando EPG %s ..." % url)
    with sess.get(url, timeout=300, stream=True) as r:
        r.raise_for_status()
        with open(cache, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return cache


def open_epg(path):
    opener = gzip.open if path.endswith(".gz") else open
    return opener(path, "rt", encoding="utf-8", errors="replace")


def epg_index(paths, wanted):
    """-> {tvg_id: {YYYYMMDD: n_programas}}"""
    days = {tvg_id: {} for tvg_id in wanted}
    for path in paths:
        for line in open_epg(path):
            if "<programme " not in line or 'channel="' not in line:
                continue
            ch = re.search(r'channel="([^"]+)"', line)
            start = re.search(r'start="(\d{8})', line)
            if not ch or not start:
                continue
            cid = ch.group(1)
            if cid in days:
                days[cid][start.group(1)] = days[cid].get(start.group(1), 0) + 1
    return days


def epg_titles(paths, tvg_id, date8, limit=6):
    """Titulos do canal em um dia. O <programme> abre numa linha e o <title> vem na seguinte."""
    out = []
    for path in paths:
        pending = None
        for line in open_epg(path):
            if "<programme " in line:
                pending = None
                if 'channel="%s"' % tvg_id in line:
                    start = re.search(r'start="(\d{12})', line)
                    if start and start.group(1).startswith(date8):
                        pending = start.group(1)[8:12]
                continue
            if pending is None:
                continue
            title = re.search(r"<title[^>]*>([^<]*)</title>", line)
            if title:
                out.append((pending, title.group(1)))
                pending = None
                if len(out) >= limit:
                    return out
    return out


# --------------------------------------------------------------------------- #
# logo
# --------------------------------------------------------------------------- #
def check_logo(url):
    """-> (ok, motivo). Exige .jpg, host saudavel e resposta de imagem."""
    if not url:
        return False, "sem tvg-logo"
    if any(h in url.lower() for h in BAD_LOGO_HOSTS):
        return False, "host imgur.com bloqueado"
    if not urlparse(url).path.lower().endswith(".jpg"):
        return False, "extensao diferente de .jpg"
    try:
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True, stream=True)
    except requests.RequestException as e:
        return False, type(e).__name__
    if r.status_code >= 400:
        return False, "HTTP %d" % r.status_code
    ctype = r.headers.get("Content-Type", "").lower()
    if "jpeg" not in ctype and "jpg" not in ctype:
        return False, "content-type %s (nao e jpeg)" % ctype
    chunk = next(r.iter_content(64), b"")
    r.close()
    if chunk[:2] != b"\xff\xd8":
        return False, "bytes nao sao JPEG"
    return True, "jpg ok"


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="so diagnostico")
    ap.add_argument("--epg-cache", default=EPG_CACHE)
    ap.add_argument("--lista", default=LISTA)
    ap.add_argument("--skip-epg", action="store_true")
    args = ap.parse_args()

    header, entries = parse(args.lista)
    rows = audit(entries)
    urls_total = len([r for r in rows if r["url"]])
    sem_extinf = [r for r in rows if r["extinf"] == "(sem #EXTINF)"]
    print("=" * 72)
    print("canais lidos: %d entradas / %d URLs / %d sem #EXTINF"
          % (len(rows), urls_total, len(sem_extinf)))

    # ---- triagem -----------------------------------------------------------
    keep_urls, drop = [], []
    for r in rows:
        (drop if r["reason"] else keep_urls).append(r)
    print("-" * 72)
    print("descartados na triagem: %d" % len(drop))
    by_reason = Counter(r["reason"] for r in drop)
    for reason, n in by_reason.most_common():
        print("   %2d x %s" % (n, reason))

    # ---- streams das entradas comecadas ------------------------------------
    print("-" * 72)
    print("testando streams das %d entradas aprovadas na triagem ..." % len(keep_urls))
    vivos, mortos = [], []
    targets = sorted({r["url"] for r in keep_urls})
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        status = dict(zip(targets, ex.map(verify, targets)))
    for r in keep_urls:
        ok, reason = status[r["url"]]
        (vivos if ok else mortos).append((r, reason))
        print("   %s  %-26s %s" % ("OK  " if ok else "FAIL", reason, r["url"][-70:]))

    # ---- canais finais -----------------------------------------------------
    print("-" * 72)
    print("validando canais finais (stream + logo + EPG) ...")
    final = []
    for ch in CHANNELS:
        problems = []
        ok, reason = verify(ch["url"])
        if not ok:
            problems.append("stream: %s" % reason)
        lok, lreason = check_logo(ch["tvg_logo"])
        if not lok:
            problems.append("logo: %s" % lreason)
        final.append({**ch, "stream_ok": ok, "stream_reason": reason,
                      "logo_ok": lok, "logo_reason": lreason,
                      "problems": problems})
        print("   %-18s stream=%-5s %-22s logo=%-5s %s"
              % (ch["name"], "OK" if ok else "FAIL", reason,
                 "OK" if lok else "FAIL", lreason))

    # ---- EPG ----------------------------------------------------------------
    wanted = [c["tvg_id"] for c in final]
    epg_report = {}
    if not args.skip_epg:
        paths = []
        for url in EPG_URLS:
            cache = args.epg_cache if len(EPG_URLS) == 1 else \
                os.path.splitext(args.epg_cache)[0] + "-" + re.sub(r"\W+", "_", url)[-24:] + ".gz"
            paths.append(fetch_epg(url, cache))
        idx = epg_index(paths, wanted)
        today = datetime.now(timezone.utc).date()
        wanted_days = [(today + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
        print("-" * 72)
        print("EPG: verificando %s / %s / %s"
              % (wanted_days[0], wanted_days[1], wanted_days[2]))
        for c in final:
            per_day = idx.get(c["tvg_id"], {})
            got = {d: per_day.get(d, 0) for d in wanted_days}
            good = all(got[d] > 0 for d in wanted_days)
            epg_report[c["tvg_id"]] = got
            if not good:
                c["problems"].append("EPG sem guia em: %s"
                                     % ", ".join(d for d in wanted_days if not got[d]))
            print("   %-18s tvg-id=%-18s %s %s"
                  % (c["name"], c["tvg_id"],
                     " ".join("%s=%d" % (d[4:], got[d]) for d in wanted_days),
                     "OK" if good else "FALTA"))
            for hhmm, title in epg_titles(paths, c["tvg_id"], wanted_days[0], limit=5):
                print("        %s  %s" % (hhmm, title))

    # ---- resultado ---------------------------------------------------------
    print("=" * 72)
    good = [c for c in final if not c["problems"]]
    for c in final:
        if c["problems"]:
            print("REMOVIDO %-18s %s" % (c["name"], "; ".join(c["problems"])))
    print("canais aprovados: %d de %d" % (len(good), len(final)))

    if args.check:
        return 0 if good else 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(args.lista, "lista5.m3u.backup_%s_pre_repair" % stamp)
    print("backup: lista5.m3u.backup_%s_pre_repair" % stamp)

    header_url = " ".join('url-tvg="%s"' % u for u in EPG_URLS)
    out = ["#EXTM3U " + header_url, "#PLAYLIST:%s" % args.lista]
    for chno, c in enumerate(good, start=1):
        out.append(
            '#EXTINF:-1 tvg-chno="%d" tvg-id="%s" tvg-logo="%s" group-title="%s" '
            'radio="false",%s'
            % (chno, c["tvg_id"], c["tvg_logo"], c["group"], c["name"]))
        out.append(c["url"])
    with open(args.lista, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    with open(RELATORIO, "w", encoding="utf-8") as fh:
        fh.write("# remocoes de %s em %s\n" % (args.lista, stamp))
        fh.write("\n## triagem de entradas (%d)\n" % len(drop))
        for r in drop:
            fh.write("[%s] %s\n%s\n" % (r["reason"], r["name"][:80], r["url"]))
        fh.write("\n## streams reprovados no teste anti-virus/vivo (%d)\n" % len(mortos))
        for r, reason in mortos:
            fh.write("[%s] %s\n%s\n" % (reason, r["name"][:80], r["url"]))
        fh.write("\n## canais reprovados na validacao final (%d)\n" % (len(final) - len(good)))
        for c in final:
            if c["problems"]:
                fh.write("[%s] %s\n%s\n"
                         % ("; ".join(c["problems"]), c["name"], c["url"]))
        if SUBSTITUTIONS:
            fh.write("\n## URLs substituidas\n")
            for channel, why in SUBSTITUTIONS:
                fh.write("- %s: %s\n" % (channel, why))
        if epg_report:
            fh.write("\n## cobertura de EPG (programas por dia)\n")
            for tvg_id, per_day in epg_report.items():
                fh.write("- %s: %s\n"
                         % (tvg_id, ", ".join("%s=%d" % (d[4:], n)
                                              for d, n in sorted(per_day.items()))))
        fh.write("\n## fontes de EPG usadas\n")
        for u in EPG_URLS:
            fh.write("- %s\n" % u)
    print("escrito: %s (%d canais) | relatorio: %s" % (args.lista, len(good), RELATORIO))
    return 0


if __name__ == "__main__":
    sys.exit(main())