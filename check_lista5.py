#!/usr/bin/env python3
"""Testa todos os canais do lista5.m3u e reescreve o arquivo sem os que falham."""

import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

LISTA = "lista5.m3u"
RELATORIO = "lista5.m3u.removidos.txt"
WORKERS = 4
TIMEOUT = 15
RETRIES = 3
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept": "*/*"})


def parse(path):
    lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    entries, header, cur = [], [], None
    for line in lines:
        if line.startswith("#EXTINF"):
            cur = [line]
        elif cur is not None and line.strip() and not line.startswith("#"):
            cur.append(line)
            entries.append(cur)
            cur = None
        elif line.startswith("#"):
            if cur is None:
                header.append(line)
            else:
                cur.append(line)
        elif not line.strip():
            continue
        else:
            cur = None
    return header, entries


def name_of(extinf):
    return extinf.rsplit(",", 1)[-1].strip()[:70]


def get(url):
    r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r


def looks_like_playlist(resp):
    ctype = resp.headers.get("Content-Type", "").lower()
    body = resp.content[:2048]
    if "mpegurl" in ctype:
        return True
    return body.lstrip(b"\xef\xbb\xbf\r\n\t ").startswith(b"#EXTM3U")


def is_master(text):
    return "#EXT-X-STREAM-INF" in text


def all_uris(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def uri_after(text, tag):
    """1a URI que aparece depois de tag."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(tag):
            for nxt in lines[i + 1:]:
                nxt = nxt.strip()
                if nxt and not nxt.startswith("#"):
                    return nxt
    return None


def ok_media(resp):
    ctype = resp.headers.get("Content-Type", "").lower()
    if "mpegurl" in ctype or "text/" in ctype or "json" in ctype or "html" in ctype:
        return False
    body = resp.content
    if len(body) < 256:
        return False
    head = body[:512].lower()
    if b"<html" in head or b"<!doctype" in head:
        return False
    if body[0] == 0x47:
        return True
    if b"ftyp" in body[:64] or b"moof" in body[:64] or b"styp" in body[:64]:
        return True
    if len(body) > 1 and body[0] == 0xFF and (body[1] & 0xF0) == 0xF0:
        return True
    return b"ID3" in body[:16]


def segment_ok(url):
    try:
        return ok_media(get(url))
    except Exception:  # noqa: BLE001
        return False


def probe(url, depth=0):
    """Segue manifesto -> variante -> segmento. Retorna (ok, motivo)."""
    if depth > 4:
        return False, "playlist muito aninhada"
    resp = get(url)
    if not looks_like_playlist(resp):
        return (True, "midia direta") if ok_media(resp) else (False, "conteudo invalido")

    text = resp.content.decode("utf-8", "replace")
    if is_master(text):
        variant = uri_after(text, "#EXT-X-STREAM-INF")
        if not variant:
            return False, "master sem variantes"
        ok, reason = probe(requests.compat.urljoin(url, variant), depth + 1)
        return (ok, "master ok" if ok else reason)

    uris = all_uris(text)
    if not uris:
        return False, "playlist sem segmentos"
    # Procura primeiro pela borda viva (ultimo segmento) e cai para os anteriores.
    for ref in reversed(uris[-3:]):
        if segment_ok(requests.compat.urljoin(url, ref)):
            return True, "playlist ok"
    return False, "nenhum segmento respondeu"


def verify(url):
    """Retorna (True, 'ok') se o stream reproduz, senao (False, motivo)."""
    reason = "desconhecido"
    for attempt in range(RETRIES):
        try:
            return probe(url)
        except requests.HTTPError as e:
            reason = "HTTP %d" % e.response.status_code if e.response is not None else "HTTP"
        except requests.RequestException as e:
            reason = type(e).__name__
        except Exception as e:  # noqa: BLE001
            reason = type(e).__name__
        time.sleep(1 + attempt)
    return False, reason


def main():
    header, entries = parse(LISTA)
    print("canais encontrados: %d" % len(entries))

    def job(item):
        idx, entry = item
        url = entry[-1].strip()
        ok, reason = verify(url)
        return idx, ok, reason, name_of(entry[0])

    results = [None] * len(entries)
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for idx, ok, reason, name in ex.map(job, list(enumerate(entries))):
            results[idx] = (ok, reason, name)

    # Reconfirma em serie: falhas em paralelo costumam ser rate limit do host.
    for idx, (ok, _, _) in enumerate(results):
        if ok:
            continue
        entry = entries[idx]
        ok2, reason2 = verify(entry[-1].strip())
        print("recheck %s %-22s %s" % ("OK  " if ok2 else "FAIL", reason2, name_of(entry[0])))
        results[idx] = (ok2, reason2, name_of(entry[0]))

    for idx, (ok, reason, name) in enumerate(results):
        print("%s  %-22s %s" % ("OK  " if ok else "FAIL", reason, name))

    alive = [e for e, r in zip(entries, results) if r[0]]
    dead = [(e, r) for e, r in zip(entries, results) if not r[0]]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(LISTA, "lista5.m3u.backup_%s_pre_test" % stamp)
    print("backup: lista5.m3u.backup_%s_pre_test" % stamp)

    with open(LISTA, "w", encoding="utf-8") as fh:
        fh.write("\n".join(header + [l for e in alive for l in e]) + "\n")

    with open(RELATORIO, "w", encoding="utf-8") as fh:
        fh.write("# canais removidos de %s em %s (motivo: motivo)\n" % (LISTA, stamp))
        for entry, (_, reason, name) in dead:
            fh.write("[%s] %s\n%s\n" % (reason, name, entry[-1].strip()))

    print("removidos: %d | mantidos: %d | relatorio: %s" % (len(dead), len(alive), RELATORIO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
