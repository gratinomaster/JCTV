#!/usr/bin/env python3
"""Testa todos os canais do lista5.m3u e reescreve o arquivo sem os que nao funcionam."""
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests

LISTA = "lista5.m3u"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HDRS = {"User-Agent": UA, "Accept": "*/*"}
TIMEOUT = (10, 15)


def parse(path):
    """Retorna (header, [(linhas_extinf, url, idx), ...])."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read().splitlines()

    header = [l for l in raw if l.startswith("#EXTM3U")]
    entries = []
    ext = []
    for line in raw:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            if s.startswith("#EXTINF"):
                ext = [s]
            continue
        if ext:
            entries.append((ext, s, len(raw)))
            ext = []
    return (header or ["#EXTM3U"]), entries, raw


def fetch(url, sess=None):
    s = sess or requests
    return s.get(url, headers=HDRS, timeout=TIMEOUT, allow_redirects=True, stream=True)


def segment_ok(url):
    """Baixa parte do segmento e confirma bytes de video/TS/fMP4."""
    try:
        r = fetch(url)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        head = r.raw.read(8192, decode_content=True)
        r.close()
        if len(head) < 1024:
            return False, f"corpo curto ({len(head)}B)"
        if b"#EXTM3U" in head[:200]:
            return False, "manifest aninhado inesperado"
        return True, f"{len(head)}B ok"
    except Exception as exc:
        return False, type(exc).__name__


def probe(url, depth=0):
    """Verifica se a URL entrega um stream vivo. Retorna (ok, detalhe)."""
    try:
        r = fetch(url)
    except Exception as exc:
        return False, f"conexao: {type(exc).__name__}"
    if r.status_code != 200:
        r.close()
        return False, f"HTTP {r.status_code}"
    body = r.raw.read(600000, decode_content=True)
    r.close()
    if len(body) < 200:
        return False, f"resposta vazia ({len(body)}B)"

    text = body.decode("utf-8", "replace")
    if "#EXTM3U" not in text:
        return True, "stream direto (nao-HLS)"

    variants = []
    segs = []
    lines = text.splitlines()
    pending_uri = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#EXT-X-STREAM-INF"):
            pending_uri = True
        elif s.startswith("#EXTINF") and pending_uri:
            segs.append(("pending", None))
            pending_uri = None
        elif s.startswith("#"):
            continue
        else:
            if pending_uri:
                variants.append(s)
                pending_uri = None
            else:
                segs.append(("seg", s))

    if variants:
        if depth >= 1:
            return segment_ok(variants[0])
        for v in variants[:4]:
            ok, det = probe(urljoin(url, v), depth + 1)
            if ok:
                return True, f"master->ok ({det})"
        return False, f"master->todas as {len(variants)} variantes falharam"

    real = [u for kind, u in segs if u]
    if not real:
        return False, "manifest sem segmentos"
    # testa o primeiro e um segmento do meio/fim da janela live
    picks = [real[0]] + ([real[len(real) // 2]] if len(real) > 2 else [])
    fails = []
    for p in picks:
        ok, det = segment_ok(urljoin(url, p))
        if not ok:
            fails.append(det)
    if fails:
        return False, f"segmento: {fails[0]}"
    return True, f"media ok ({len(real)} seg)"


def main():
    header, entries, _ = parse(LISTA)
    urls = [u for _, u, _ in entries]
    uniq = sorted(set(urls))
    print(f"entradas: {len(entries)} | urls unicas: {len(uniq)}")

    results = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = {pool.submit(probe, u): u for u in uniq}
        for i, fut in enumerate(futs, 1):
            u = futs[fut]
            try:
                results[u] = fut.result()
            except Exception as exc:
                results[u] = (False, f"erro: {exc}")
            ok, det = results[u]
            print(f"[{i}/{len(uniq)}] {'OK  ' if ok else 'FALHA'} {det:34s} {u[:105]}")

    # dedupe por url, preservando a primeira ocorrencia e a ordem original
    seen = set()
    kept, dropped = [], []
    for ext, url, _ in entries:
        ok, _det = results[url]
        if not ok:
            dropped.append((ext[0][:120], url))
            continue
        if url in seen:
            dropped.append((ext[0][:120] + " [duplicado]", url))
            continue
        seen.add(url)
        kept.append((ext, url))

    with open(LISTA, "w", encoding="utf-8") as fh:
        fh.write(header[0] + "\n")
        for ext, url in kept:
            fh.write(ext[0] + "\n")
            fh.write(url + "\n")

    print("\n=== resumo ===")
    print(f"mantidos: {len(kept)} | removidos: {len(dropped)}")
    for name, url in dropped:
        print(f"- {name} | {url[:100]}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())