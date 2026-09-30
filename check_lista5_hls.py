#!/usr/bin/env python3
"""Testa cada canal do lista5.m3u sem depender de ffmpeg/ffprobe.

O teste segue a cadeia HLS real: baixa o manifest, resolve variantes, escolhe
um segmento de midia e valida os bytes recebidos (sync byte MPEG-TS ou box
ftyp fMP4). O tipo de track e lido do init segment (fMP4) ou do PMT (TS) para
distinguir canal de video de apenas audio.

Uso:
    python3 check_lista5_hls.py --dry-run
    python3 check_lista5_hls.py
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests

M3U_FILE = "lista5.m3u"
REPORT_FILE = "stream_check_lista5.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

ATTEMPTS = 3
CONNECT_TIMEOUT = 12
READ_TIMEOUT = 20
SEGMENT_BYTES = 262144
MAX_DEPTH = 4

LAST_ERR = ""

OK = "A/V_OK"
AUDIO = "AUDIO_ONLY"
DEAD = "DEAD"

VIDEO_CODECS = ("avc1", "avc3", "hvc1", "hev1", "av01", "vp9", "vp09", "dvhe")
VIDEO_TS_TYPES = {0x01, 0x02, 0x10, 0x1B, 0x24, 0x27, 0x51, 0xD1}
AUDIO_TS_TYPES = {0x03, 0x04, 0x0F, 0x11, 0x81, 0x82, 0x83, 0x84, 0x85, 0x86,
                  0x87, 0x8A, 0x91, 0x94, 0x06}


def get(url, want_bytes=False, extra=None):
    """GET simples. Retorna bytes, texto ou None em falha (detalhe em LAST_ERR)."""
    global LAST_ERR
    h = dict(HEADERS)
    if extra:
        h.update(extra)
    try:
        r = requests.get(url, headers=h, timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                         stream=not want_bytes, allow_redirects=True)
    except requests.RequestException as exc:
        LAST_ERR = type(exc).__name__
        return None
    if r.status_code != 200:
        r.close()
        LAST_ERR = f"HTTP {r.status_code}"
        return None
    if want_bytes:
        data = b""
        try:
            for chunk in r.iter_content(65536):
                data += chunk
                if len(data) >= SEGMENT_BYTES:
                    break
        except requests.RequestException as exc:
            LAST_ERR = f"leitura: {type(exc).__name__}"
        r.close()
        if not data:
            return None
        LAST_ERR = ""
        return data
    r.encoding = r.apparent_encoding or "utf-8"
    LAST_ERR = ""
    return r.text


def inherit_query(child, parent):
    """Propaga query string do pai (token de CDN) para o filho, se faltar.

    Alguns CDNs (ex.: 247.foxnews.com) autorizam apenas o master com
    `hdnea=...` e deixam as variantes sem query. Sem propagar, toda variante
    responde 403 e o canal parece quebrado.
    """
    if not child or urlparse(child).query:
        return child
    parent_query = urlparse(parent).query
    return f"{child}?{parent_query}" if parent_query else child


def bandwidth_of(tag):
    m = re.search(r'BANDWIDTH=(\d+)', tag)
    return int(m.group(1)) if m else 0


def codecs_of(tag):
    m = re.search(r'CODECS="([^"]*)"', tag)
    return m.group(1) if m else ""


def parse_master(text, base):
    """Retorna lista de (bandwidth, codecs, url) das variantes."""
    out = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF"):
            continue
        uri = None
        for nxt in lines[i + 1:i + 4]:
            s = nxt.strip()
            if s and not s.startswith("#"):
                uri = s
                break
        if uri:
            out.append((bandwidth_of(line), codecs_of(line),
                        inherit_query(urljoin(base, uri), base)))
    return out


def parse_media(text, base):
    """Retorna (init_url, [segment_urls]) de uma media playlist."""
    init_url, segments = None, []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#EXT-X-MAP:"):
            m = re.search(r'URI="([^"]*)"', s)
            if m:
                init_url = inherit_query(urljoin(base, m.group(1)), base)
        elif s and not s.startswith("#"):
            segments.append(inherit_query(urljoin(base, s), base))
    return init_url, segments


def has_endlist(text):
    return "#EXT-X-ENDLIST" in text


def ftyp_tracks(data):
    """Le handler types do moov de um init segment fMP4 (box 4CC 'hdlr')."""
    return {m.group(1).decode()
            for m in re.finditer(rb'hdlr.{0,8}?(vide|soun|subt)', data, re.S)}


def is_mp4(data):
    """True se comeca com um box ISO-BMFF valido (ftyp/styp/moof/emsg)."""
    return len(data) >= 8 and data[4:8] in (b"ftyp", b"styp", b"moof", b"emsg",
                                            b"sidx")


def ts_tracks(data):
    """Parseia PAT/PMT de um segmento MPEG-TS e devolve os stream types."""
    pmt_pid, pmt = None, None
    pos = 0
    while pos + 188 <= len(data):
        if data[pos] != 0x47:
            nxt = data.find(b"\x47", pos + 1)
            if nxt == -1:
                break
            pos = nxt
            continue
        pkt = data[pos:pos + 188]
        pos += 188
        pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
        pusi = bool(pkt[1] & 0x40)
        afc = (pkt[3] >> 4) & 0x3
        idx = 4
        if afc in (2, 3):
            idx += 1 + pkt[4]
        if afc in (1, 3) and idx < 188:
            if pid == 0 and pmt is None:
                sec = pkt[idx:]
                if len(sec) > 8 and sec[0] == 0:
                    prog = sec[8:]
                    for k in range(0, len(prog) - 4, 4):
                        if prog[k:k + 3] == b"\x00\x00\x01":
                            pmt_pid = ((prog[k + 3] & 0x1F) << 8) | prog[k + 4]
                            break
            elif pmt_pid is not None and pid == pmt_pid and pmt is None:
                pmt = pkt[idx:]
                break
    if pmt is None:
        return set()
    if len(pmt) < 12 or pmt[0] != 0x02:
        return set()
    info_len = ((pmt[10] & 0x0F) << 8) | pmt[11]
    pos2, end = 12, min(len(pmt), 12 + info_len)
    pos2 += 4
    types = set()
    while pos2 + 5 <= end:
        stype = pmt[pos2]
        es_len = ((pmt[pos2 + 3] & 0x0F) << 8) | pmt[pos2 + 4]
        types.add(stype)
        pos2 += 5 + es_len
    return types


def track_kind(url, text):
    """Retorna ('video'|'audio'|'unknown', motivo) analisando segmentos reais."""
    init_url, segments = parse_media(text, url)
    if init_url:
        data = get(init_url, want_bytes=True)
        if data and is_mp4(data):
            kinds = ftyp_tracks(data)
            if "vide" in kinds:
                return "video", "init fMP4 com trilha video"
            if "soun" in kinds:
                return "audio", "init fMP4 somente audio"
            return "unknown", "init fMP4 sem trilha identificavel"
    target = segments[0] if segments else None
    if not target:
        return "unknown", "sem segmentos"
    data = get(target, want_bytes=True)
    if not data:
        return "unknown", "init/segmento ilegivel"
    if is_mp4(data):
        kinds = ftyp_tracks(data)
        if "vide" in kinds:
            return "video", "segmento fMP4 com trilha video"
        if "soun" in kinds:
            return "audio", "segmento fMP4 somente audio"
        return "unknown", "fMP4 sem trilha identificavel"
    if data[0] == 0x47:
        types = ts_tracks(data)
        if types & VIDEO_TS_TYPES:
            return "video", "PMT com stream de video"
        if types & AUDIO_TS_TYPES:
            return "audio", "PMT somente com stream de audio"
        return "unknown", "PMT sem stream reconhecido"
    return "unknown", "bytes nao reconhecidos como TS/fMP4"


def classify(url, text):
    """Usa o init segment / PMT para dizer se o canal tem video."""
    kind, why = track_kind(url, text)
    if kind == "audio":
        return AUDIO, why
    if kind == "video":
        return OK, why
    return None, why


def validate(url, depth=0):
    """Valida a cadeia HLS. Retorna (status, motivo)."""
    if depth > MAX_DEPTH:
        return DEAD, "profundidade de variantes excedida"

    text = get(url)
    if text is None:
        return DEAD, f"manifesto inacessivel ({LAST_ERR})"
    if not text.lstrip().startswith("#EXTM3U"):
        return DEAD, "resposta nao e um manifest M3U"

    if "#EXT-X-STREAM-INF" in text:
        variants = parse_master(text, url)
        if not variants:
            return DEAD, "master sem variantes"
        variants.sort(key=lambda v: v[0], reverse=True)
        last = "todas as variantes falharam"
        for _bw, _codecs, vurl in variants:
            status, reason = validate(vurl, depth + 1)
            if status != DEAD:
                kind_status, why = classify(vurl, get(vurl) or "")
                if kind_status == AUDIO:
                    return AUDIO, why
                return status, reason
            last = reason
        return DEAD, last

    init_url, segments = parse_media(text, url)
    if not segments:
        return DEAD, "media playlist sem segmentos"

    live = not has_endlist(text)
    # Em live, o ultimo segmento costuma estar ainda em_buffer; usa o anterior.
    candidates = segments[-2::-1][:3] if live and len(segments) > 1 else segments[:3]

    seg_err = ""
    for seg in candidates:
        data = get(seg, want_bytes=True)
        if not data:
            seg_err = f"segmento inacessivel ({LAST_ERR})"
            continue
        kind_name = None
        if is_mp4(data):
            kind_name = "fMP4"
        elif len(data) >= 188 and data[0] == 0x47:
            kind_name = "MPEG-TS"
        if kind_name:
            # Segmento valido: agora confirma se o fluxo tem video.
            kind_status, why = classify(url, text)
            if kind_status == AUDIO:
                return AUDIO, why
            return OK, f"segmento {kind_name} valido ({len(data)} bytes)"
        seg_err = f"segmento invalido (head={data[:8].hex()})"
    return DEAD, seg_err or "nenhum segmento valido"


def check_one(url):
    last = ""
    for attempt in range(1, ATTEMPTS + 1):
        status, reason = validate(url)
        last = reason
        if status != DEAD:
            return status, reason
        if attempt < ATTEMPTS:
            time.sleep(3 * attempt)
    media = get(url)
    if media and "#EXT-X-STREAM-INF" not in media:
        kind, why = track_kind(url, media)
        if kind == "audio":
            return AUDIO, why
    return DEAD, last


def parse_m3u(path):
    """Retorna (header, [(extinf, url)])."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    header, entries, pending, i = [], [], None, 0
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF"):
            pending = line
        elif line and not line.startswith("#") and pending is not None:
            entries.append((pending, line))
            pending = None
        i += 1
    return header, entries


def channel_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", default=M3U_FILE)
    args = ap.parse_args()

    header, entries = parse_m3u(args.file)
    unique = list(dict.fromkeys(u for _, u in entries))
    print(f"Arquivo  : {args.file}")
    print(f"Canais   : {len(entries)}")
    print(f"URLs     : {len(unique)} unicas\n")

    cache, results = {}, []
    for n, (extinf, url) in enumerate(entries, 1):
        name = channel_name(extinf)
        if url not in cache:
            status, reason = check_one(url)
            cache[url] = (status, reason)
            print(f"  [{n:2d}/{len(entries)}] {status:10s} {name[:44]:44s} {reason[:44]}")
        status, reason = cache[url]
        results.append({"name": name, "url": url, "extinf": extinf,
                        "status": status, "reason": reason})

    ok = [r for r in results if r["status"] == OK]
    audio = [r for r in results if r["status"] == AUDIO]
    dead = [r for r in results if r["status"] == DEAD]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 64)
    print(f"Total testados   : {len(results)}")
    print(f"Funcionando (A/V): {len(ok)}")
    print(f"Apenas audio     : {len(audio)}")
    print(f"Nao funcionando  : {len(dead)}")
    print("=" * 64)
    for r in dead:
        print(f"  - {r['name'][:52]:52s} {r['reason'][:40]}")
    for r in audio:
        print(f"  ~ {r['name'][:52]:52s} {r['reason'][:40]}")

    if args.dry_run:
        print("\n[dry-run] lista5.m3u nao foi alterado.")
        return

    keep = [r for r in results if r["status"] == OK]
    if len(keep) == len(results):
        print("\nTodos os canais funcionam; arquivo mantido como esta.")
        return

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(args.file, f"{args.file}.backup_{stamp}_pre_test")

    out = list(header) or ["#EXTM3U"]
    if not out[0].startswith("#EXTM3U"):
        out.insert(0, "#EXTM3U")
    for r in keep:
        out.append(r["extinf"])
        out.append(r["url"])

    tmp = args.file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, args.file)
    print(f"\n{args.file} reescrito: {len(keep)} mantidos, "
          f"{len(results) - len(keep)} removidos.")
    print(f"Backup: {args.file}.backup_{stamp}_pre_test")


if __name__ == "__main__":
    main()
