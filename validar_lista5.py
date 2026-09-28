#!/usr/bin/env python3
"""Testa todos os canais do lista5.m3u, remove os que nao funcionam e
sobrescreve a lista mantendo apenas os que entregam audio+video ao vivo.

Criterio de "funcionando" (todas as etapas precisam passar):

  T1  HTTP 200 e corpo HLS valido (#EXTM3U)
  T2  o manifesto entrega midia real: master cujas variantes resolvem para
      media, ou media playlist com segmentos. Um indice sem segmentos
      (sub-rendition / DVR) nao e um canal.
  T3  sem DRM (EXT-X-KEY METHOD!=NONE, EXT-X-SESSION-KEY, URL cmaf-cenc):
      Widevine/FairPlay exige licenca, nao toca em VLC/Kodi/ffmpeg.
  T4  segmento de inicializacao + pelo menos 1 segmento de midia baixam
      e tem container valido (fMP4 ftyp/moof/mdat ou MPEG-TS sync 0x47)
  T5  existe faixa de AUDIO real (muxed mp4a, grupo EXT-X-MEDIA, ou
      hdlr 'soun' no init segment) -- stream so de video nao e canal
  T6  e LIVE (sem #EXT-X-ENDLIST)

Nao ha ffmpeg neste ambiente, entao containers sao validados parseando as
boxes ISO-BMFF do init segment, que e o que decide se o player toca.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
PLAYLIST = "lista5.m3u"
REPORT = "validar_lista5.json"
TIMEOUT = 15
RETRIES = 3
WORKERS = 6
DRM_URL = re.compile(r"cmaf-cenc|(?:^|[/_-])(?:cenc|pssh)(?:[/_.-]|$)", re.I)
# CDNs como a 247.foxnews.com exigem o token de auth tambem nos filhos:
# sem propagate-lo o master responde 200 e o child responde 403.
AUTH_QUERY = re.compile(r"hdnea|hdnts|(?:^|~)(?:exp|acl|hmac|policy|sig|signature)"
                        r"(?:=|:)|token|expires|(?:^|[&?])(?:md5|key|psig)=",
                        re.I)


def carry_query(base, rel, q):
    """urljoin(base, rel) propagando o token de auth do pai para o filho."""
    child = urljoin(base, rel)
    if not q:
        return child
    if "?" in child:
        return child
    return f"{child}?{q}"


def auth_query(url):
    q = urlparse(url).query
    return q if q and AUTH_QUERY.search(q) else ""


# ----------------------------------------------------------------- m3u
def parse_m3u(path):
    """-> [dict(info=str, url=str, name=str, attrs=dict)] preservando ordem."""
    entries, pending = [], None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if not line.strip():
                continue
            if line.startswith("#EXTM3U"):
                continue
            if line.startswith("#EXTINF:"):
                pending = line
                continue
            if line.startswith("#"):
                continue
            name = pending.split(",", 1)[-1].strip() if pending else line
            entries.append({"info": pending, "url": line, "name": name})
            pending = None
    return entries


# ----------------------------------------------------------------- http
def get(url, limit=2_000_000, referer=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
         "Connection": "close"}
    if referer:
        h["Referer"] = referer
    last = None
    for i in range(RETRIES):
        try:
            r = requests.get(url, headers=h, timeout=TIMEOUT, stream=True)
            if r.status_code != 200:
                r.close()
                return {"status": r.status_code, "data": b"", "url": r.url,
                        "ctype": r.headers.get("Content-Type", "")}
            data = r.raw.read(limit + 1, decode_content=True) or b""
            return {"status": 200, "data": data[:limit], "url": r.url,
                    "ctype": r.headers.get("Content-Type", "")}
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(1.2 * (i + 1))
    raise last


# ----------------------------------------------------------------- hls
def parse_master(text, base, q=""):
    variants, auds, cur = [], {}, None
    for raw in text.splitlines():
        l = raw.strip()
        if not l:
            continue
        if l.startswith("#EXT-X-STREAM-INF:"):
            cur = dict(re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)',
                                  l.split(":", 1)[1]))
        elif l.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in l:
            a = dict(re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)',
                                l.split(":", 1)[1]))
            uri = a.get("URI", "").strip('"')
            if uri:
                auds[a.get("GROUP-ID", "").strip('"')] = carry_query(base, uri, q)
        elif not l.startswith("#") and cur is not None:
            variants.append({
                "url": carry_query(base, l, q),
                "bw": int(cur.get("BANDWIDTH", 0) or 0),
                "res": cur.get("RESOLUTION", "").strip('"'),
                "codecs": cur.get("CODECS", "").strip('"'),
                "audio": cur.get("AUDIO", "").strip('"'),
            })
            cur = None
    return variants, auds


def parse_media(text, base, q=""):
    segs, init, endlist, drm = [], None, False, []
    for raw in text.splitlines():
        l = raw.strip()
        if not l:
            continue
        if l.startswith("#EXT-X-ENDLIST"):
            endlist = True
        elif l.startswith("#EXT-X-MAP:"):
            m = re.search(r'URI="([^"]+)"', l)
            if m:
                init = carry_query(base, m.group(1), q)
        elif l.startswith("#EXT-X-KEY:"):
            m = re.search(r"METHOD=([A-Z0-9-]+)", l)
            if m and m.group(1) != "NONE":
                drm.append(m.group(1))
        elif l.startswith("#EXT-X-SESSION-KEY"):
            drm.append("SESSION-KEY")
        elif not l.startswith("#"):
            segs.append(carry_query(base, l, q))
    return segs, endlist, init, drm


def container(data):
    """-> (kind, boxes) validando boxes ISO-BMFF / sync MPEG-TS."""
    if not data:
        return None, []
    i, n, found = 0, len(data), []
    while i + 8 <= n and len(found) < 64:
        size = int.from_bytes(data[i:i + 4], "big")
        typ = data[i + 4:i + 8]
        if size == 1:
            if i + 16 > n:
                break
            size = int.from_bytes(data[i + 8:i + 16], "big")
        elif size == 0:
            size = n - i
        if size < 8 or i + size > n:
            break
        found.append(typ.decode("latin-1", "replace").strip())
        i += size
    if {"ftyp", "moof", "mdat", "styp", "sidx"} & set(found):
        return "fMP4", found
    if data[:1] == b"\x47" and len(data) > 188 and data[188:189] == b"\x47":
        return "MPEG-TS", ["TS"]
    return None, found


def has_audio(data, kind):
    """Init segment: procura hdlr 'soun' (fMP4). MPEG-TS: conta PIDs distintos."""
    if kind == "fMP4":
        return b"soun" in data
    if kind == "MPEG-TS":
        pids = set()
        for off in range(0, min(len(data), 60000) - 188, 188):
            if data[off:off + 1] != b"\x47":
                return False
            pids.add(((data[off + 1] & 0x1F) << 8) | data[off + 2])
        return len(pids) >= 2
    return False


def has_video(data, kind):
    if kind == "fMP4":
        return b"vide" in data
    if kind == "MPEG-TS":
        return True
    return False


# ----------------------------------------------------------------- check
def check(url, name=""):
    r = {"url": url, "name": name, "host": urlparse(url).netloc,
         "kind": None, "codec": None, "res": "", "drm": [], "live": None,
         "audio": None, "segs_ok": 0, "fail": [], "verdict": "FAIL"}
    F = r["fail"]

    # T1 -----------------------------------------------------------------
    try:
        g = get(url)
    except Exception as e:                          # noqa: BLE001
        F.append(f"T1 sem resposta: {type(e).__name__}")
        return r
    if g["status"] != 200:
        F.append(f"T1 HTTP {g['status']}")
        return r
    text = g["data"].decode("utf-8", "replace")
    if "#EXTM3U" not in text[:800]:
        F.append(f"T1 nao e HLS (Content-Type: {g['ctype'] or '?'})")
        return r
    r["http"] = 200

    # T2 -----------------------------------------------------------------
    q = auth_query(url)
    variants, auds = parse_master(text, g["url"], q)
    r["kind"] = "master" if variants else "media"
    if variants:
        best = max(variants, key=lambda v: (v["bw"], v["res"]))
        r["res"] = best["res"] or "?"
        r["codec"] = best["codecs"] or "?"
        try:
            vg = get(best["url"], referer=g["url"])
            vtext = vg["data"].decode("utf-8", "replace")
        except Exception as e:                      # noqa: BLE001
            F.append(f"T2 variante principal nao baixou: {type(e).__name__}")
            return r
        segs, endlist, init, drm = parse_media(vtext, g["url"], q)
        if not segs:
            F.append("T2 variante sem segmentos de midia")
            return r
    else:
        best = None
        segs, endlist, init, drm = parse_media(text, g["url"], q)
        if not segs:
            F.append("T2 sem segmentos nem variantes (indice/sub-rendition)")
            return r

    # T3 -----------------------------------------------------------------
    r["drm"] = sorted(set(drm))
    if DRM_URL.search(url):
        r["drm"].append("URL-cenc")
    if r["drm"]:
        F.append(f"T3 DRM ({','.join(r['drm'])}) - exige licenca, nao toca")

    # T4 -----------------------------------------------------------------
    try:
        ig = get(init or segs[0], limit=3_000_000, referer=g["url"])
        kind, _ = container(ig["data"])
        r["codec"] = r["codec"] if r["codec"] not in (None, "", "?") else (kind or "")
        if not kind:
            F.append("T4 init segment nao e container valido")
            return r
        r["container"] = kind
        r["audio"] = has_audio(ig["data"], kind)
        r["video"] = has_video(ig["data"], kind)
    except Exception as e:                          # noqa: BLE001
        F.append(f"T4 init segment nao baixou: {type(e).__name__}")
        return r

    for s in segs[-2:]:
        try:
            sg = get(s, limit=5_000_000, referer=g["url"])
            k, _ = container(sg["data"])
            if k and len(sg["data"]) > 2048:
                r["segs_ok"] += 1
        except Exception:                           # noqa: BLE001
            pass
    if not r["segs_ok"]:
        F.append("T4 nenhum segmento de midia baixou")
        return r

    # T5 -----------------------------------------------------------------
    if not r["video"]:
        F.append("T5 sem faixa de video (so audio / so imagem)")
        return r
    if r["audio"] is False and auds and best and best["audio"] in auds:
        try:
            ag = get(auds[best["audio"]], referer=g["url"])
            asegs, _, ainit, _ = parse_media(
                ag["data"].decode("utf-8", "replace"), g["url"], q)
            probe = get(ainit or asegs[0], limit=3_000_000,
                        referer=g["url"]) if (ainit or asegs) else None
            k = container(probe["data"])[0] if probe else None
            r["audio"] = bool(k)
        except Exception:                           # noqa: BLE001
            r["audio"] = False
    if r["audio"] is not True and "mp4a" in (r["codec"] or ""):
        r["audio"] = True
    if r["audio"] is not True:
        F.append("T5 sem faixa de audio (so video / so imagem)")
        return r

    # T6 -----------------------------------------------------------------
    r["live"] = not endlist
    if endlist:
        F.append("T6 nao e live (tem #EXT-X-ENDLIST)")

    r["verdict"] = "FAIL" if F else "PASS"
    return r


# ----------------------------------------------------------------- main
def main():
    path = sys.argv[1] if len(sys.argv) > 1 else PLAYLIST
    entries = parse_m3u(path)
    targets = list(OrderedDict((e["url"], e["name"]) for e in entries).items())
    print(f"{path}: {len(entries)} entradas, {len(targets)} URLs unicas")
    print(f"testando com {WORKERS} workers (T1..T6)...\n")

    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(check, u, n): u for u, n in targets}
        done = 0
        for fut in as_completed(futs):
            r = fut.result()
            results[r["url"]] = r
            done += 1
            mark = "OK  " if r["verdict"] == "PASS" else "FORA"
            extra = (f"{r['res']} {r['container']} audio={r['audio']} "
                     f"video={r.get('video')} live={r['live']}"
                     if r["verdict"] == "PASS" else "; ".join(r["fail"]))
            print(f"[{done:>2}/{len(targets)}] {mark} {r['host'][:34]:34s} {extra[:96]}")

    # reescreve mantendo a ordem original e o cabecalho #EXTM3U
    keep = [e for e in entries if results.get(e["url"], {}).get("verdict") == "PASS"]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for e in keep:
            fh.write((e["info"] or f'#EXTINF:-1,{e["name"]}') + "\n")
            fh.write(e["url"] + "\n")

    removed = [results[u] for u, _ in targets if results[u]["verdict"] != "PASS"]
    print(f"\n{'=' * 70}")
    print(f"FUNCTIONANDO (mantidos): {len(keep)}")
    print(f"REMOVIDOS:               {len(removed)}")
    for r in removed:
        print(f"  - {r['name'][:46]:46s} | {'; '.join(r['fail'])[:70]}")
    print(f"\nlista sobrescrita: {path}")

    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump({"tested_at": datetime.now(timezone.utc).isoformat(),
                   "playlist": path, "kept": len(keep), "removed": len(removed),
                   "results": list(results.values())}, fh, indent=2, ensure_ascii=False)
    print(f"relatorio: {REPORT}")


if __name__ == "__main__":
    main()
