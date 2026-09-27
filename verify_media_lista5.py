#!/usr/bin/env python3
"""Verifica cada canal do lista5.m3u baixando midia de verdade.

A diferenca para os outros verificadores do repo e que nao basta o manifesto
responder 200: o script resolve master -> variant -> segmento e so considera o
canal funcionando se o segmento baixar com conteudo de video valido.

Uso:
    python3 verify_media_lista5.py --dry-run
    python3 verify_media_lista5.py
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

M3U_FILE = "lista5.m3u"
REPORT_FILE = "verify_media_lista5.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Referer": "https://www.google.com/",
}

ATTEMPTS = 3
TIMEOUT = 15
PAUSE = 0.4
MIN_SEGMENT_BYTES = 12_000
REPORT_MIN_BYTES = 0


def get(url, timeout=TIMEOUT):
    """Retorna (status, bytes) ou (None, motivo) em caso de falha."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout,
                         allow_redirects=True, stream=True)
    except requests.exceptions.Timeout:
        return None, "timeout"
    except requests.exceptions.ConnectionError:
        return None, "connection error"
    except Exception as e:
        return None, "err %s" % type(e).__name__
    if r.status_code != 200:
        r.close()
        return None, "HTTP %d" % r.status_code
    try:
        return 200, r.content
    except Exception as e:
        return None, "leitura %s" % type(e).__name__
    finally:
        try:
            r.close()
        except Exception:
            pass


def resolve(uri, base):
    """Resolve segmento/variant preservando o token de query do CDN (ex.: hdnea).

    Alguns CDNs (Akamai/Brightcove) devolvem variantes e segmentos como URL
    absoluta SEM o token, e sem ele a resposta é 403. Sempre que o base tem
    query de auth e o alvo é do mesmo host sem query, ela é repassada.
    """
    if uri.startswith("http://") or uri.startswith("https://"):
        url = uri
    else:
        url = urljoin(base, uri)

    _, sep, query = base.partition("?")
    if not sep or not query or "?" in url:
        return url
    if urlparse(url).netloc != urlparse(base).netloc:
        return url
    return url + "?" + query


def looks_like_media(data):
    """True se o corpo tem assinatura de midia real (mp4/cmaf/mpeg-ts/aac)."""
    if len(data) < MIN_SEGMENT_BYTES:
        return False

    # Respostas de erro em HTML/XML disfarçadas não contam como mídia.
    probe = data[:512].lstrip().lower()
    if probe.startswith((b"<!doctype", b"<html", b"<?xml", b"<error", b"<mpd")):
        return False

    head = data[:64]
    for box in (b"ftyp", b"styp", b"sidx", b"moof", b"mdat", b"emsg"):
        if box in head:
            return True
    if b"moov" in data[:16384] or b"mvhd" in data[:16384]:
        return True
    if b"ID3" in head or b"\xff\xfb" in head or b"\xff\xf3" in head or b"\xff\xf2" in head:
        return True
    if head[0] == 0x47 and (len(data) % 188 == 0 or data[188] == 0x47):
        return True

    # CMAF pode começar direto em mdat. Um payload binário grande não é página
    # de erro, então treatá-lo como mídia é o melhor sinal disponível.
    if len(data) >= MIN_SEGMENT_BYTES and b"\x00" in data[:1024]:
        try:
            data[:4096].decode("utf-8")
        except UnicodeDecodeError:
            return True
    return False


def is_playlist(data):
    return b"#EXTM3U" in data[:4096]


def parse_playlist(text):
    """Retorna (media_uris, variants[(bandwidth, uri)])."""
    media, variants = [], []
    pending_variant = False
    lines = text.splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF"):
            pending_variant = True
            for token in line.split(":"):
                name, _, value = token.partition("=")
                if name.strip().upper() != "BANDWIDTH":
                    continue
                digits = ""
                for ch in value:
                    if ch in ",;":
                        break
                    if ch.isdigit():
                        digits += ch
                variants.append((int(digits) if digits else 0, None))
                break
            else:
                variants.append((0, None))
            continue
        if line.startswith("#"):
            continue
        if pending_variant:
            if variants:
                variants[-1] = (variants[-1][0], line)
            pending_variant = False
        else:
            media.append(line)
    variants = [(bw, uri) for bw, uri in variants if uri]
    return media, variants


def check_segment(url, depth=0):
    """Baixa o manifesto e um segmento. Retorna (ok, detail)."""
    if depth > 3:
        return False, "profundidade de variantes excedida"

    code, data = get(url)
    if code is None:
        return False, data

    if not is_playlist(data):
        if looks_like_media(data):
            return True, "midia direta (%d KB)" % (len(data) // 1024)
        return False, "resposta nao-HLS sem midia (%d B)" % len(data)

    media, variants = parse_playlist(data.decode("utf-8", "ignore"))
    if variants and not media:
        best = max(variants, key=lambda v: v[0])
        variant_url = resolve(best[1], url)
        ok, detail = check_segment(variant_url, depth + 1)
        return ok, "variant %dKbps: %s" % (best[0] // 1000, detail)

    if not media:
        return False, "playlist HLS sem segmentos"

    probes = media[-2:] if len(media) >= 2 else media
    last_err = "sem segmento valido"
    for uri in probes:
        seg_url = resolve(uri, url)
        scode, sdata = get(seg_url)
        if scode is None:
            last_err = "segmento: %s" % sdata
            continue
        if looks_like_media(sdata):
            return True, "%d segmentos, midia ok (%d KB)" % (
                len(media), len(sdata) // 1024)
        last_err = "segmento invalido (%d B)" % len(sdata)
    return False, last_err


def test_url(url, attempts=ATTEMPTS):
    last = "desconhecido"
    for attempt in range(1, attempts + 1):
        ok, detail = check_segment(url)
        if ok:
            return True, detail
        last = detail
        if attempt < attempts:
            time.sleep(1.5 * attempt)
    return False, last


def parse_m3u(path):
    """Retorna (header, [(extinf, url)]) preservando a ordem original."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    header, entries = [], []
    i = 0
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1

    pending = None
    for line in lines[i:]:
        if line.startswith("#EXTINF"):
            pending = line
        elif line.strip() and not line.startswith("#"):
            entries.append((pending or "", line))
            pending = None
    return header, entries


def channel_name(extinf, index=0):
    if "," in extinf:
        return extinf.rsplit(",", 1)[-1].strip()
    return extinf.strip() or "canal %d" % index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=M3U_FILE)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    header, entries = parse_m3u(args.file)
    unique = {u for _, u in entries}
    print("Arquivo  : %s" % args.file)
    print("Entradas : %d" % len(entries))
    print("URLs     : %d unicas\n" % len(unique))

    cache, results = {}, []
    for n, (extinf, url) in enumerate(entries, 1):
        if url not in cache:
            cache[url] = test_url(url)
            time.sleep(PAUSE)
        ok, detail = cache[url]
        name = channel_name(extinf, n)
        results.append({
            "name": name, "url": url, "extinf": extinf,
            "ok": ok, "detail": detail,
        })
        print("  [%2d/%d] %s  %-44s %s" % (
            n, len(entries), "OK  " if ok else "FAIL", name[:44], detail[:56]))

    ok_rows = [r for r in results if r["ok"]]
    dead = [r for r in results if not r["ok"]]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print("Testados        : %d" % len(results))
    print("Funcionando     : %d" % len(ok_rows))
    print("Nao funcionam   : %d" % len(dead))
    print("=" * 64)

    if dead:
        print("\nRemovidos:")
        for r in dead:
            print("  - %-44s %s" % (r["name"][:44], r["detail"][:60]))
            print("      %s" % r["url"][:150])

    dupes = len(results) - len({r["url"] for r in ok_rows})
    if dupes:
        print("\nAviso: %d entradas sao URLs duplicadas mantidas como estao."
              % dupes)

    if args.dry_run:
        print("\n[dry-run] %s nao foi alterado." % args.file)
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = "%s.bak_%s_pre_verify" % (args.file, stamp)
    shutil.copy2(args.file, backup)
    print("\nBackup: %s" % backup)

    if not dead:
        print("Nenhum canal removido; arquivo mantido como esta.")
        return

    out = list(header) or ["#EXTM3U"]
    if not out[0].startswith("#EXTM3U"):
        out.insert(0, "#EXTM3U")
    for r in ok_rows:
        out.append(r["extinf"] or r["name"])
        out.append(r["url"])

    tmp = args.file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, args.file)
    print("%s reescrito: %d mantidos, %d removidos." % (
        args.file, len(ok_rows), len(dead)))


if __name__ == "__main__":
    main()
