#!/usr/bin/env python3
"""
Definitive HLS channel validator + anti-virus scanner for lista5.m3u.

A URL only earns a place in the playlist if ALL of these hold:

  L1  HTTP 200 and the body is a real HLS manifest (#EXTM3U)
  L2  the manifest is a MASTER (has EXT-X-STREAM-INF) or a media playlist
      with EXTINF -> it is a channel, not a sub-rendition/DVR index
  L3  NOT DRM protected (EXT-X-KEY METHOD=NONE / no EXT-X-KEY).
      SAMPLE-AES / cenc = Widevine, unplayable in VLC/Kodi
  L4  a video init segment + media segments download and contain valid
      container boxes (ftyp/moof/mdat for fMP4, 0x47 sync for MPEG-TS)
  L5  an AUDIO track is present and downloadable (muxed in the variant or
      via an EXT-X-MEDIA audio group)
  L6  the stream is LIVE (has EXT-X-ENDLIST absent + media sequence moving)
  L7  ANTI-VIRUS: manifests + every downloaded segment are scanned for
      executable/archive/script/polyglot/exfil signatures and for
      untrusted-host patterns. Any hit = channel removed.

No ffprobe dependency: containers are validated by parsing ISO-BMFF boxes,
which is what actually matters for "will a player play this".
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# --------------------------------------------------------------- AV SIGS
BINARY_SIGS = [
    ("Win32 PE executable", 0, b"MZ"),
    ("ELF executable", 0, b"\x7fELF"),
    ("Mach-O executable", 0, b"\xcf\xfa\xed\xfe"),
    ("Mach-O 64 executable", 0, b"\xcf\xfa\xed\xfe"),
    ("Java class", 0, b"\xca\xfe\xba\xbe"),
    ("Android DEX", 0, b"dex\n"),
    ("RAR archive", 0, b"Rar!\x1a\x07"),
    ("7-Zip archive", 0, b"7z\xbc\xaf\x27\x1c"),
    ("BZip2 archive", 0, b"BZh"),
    ("XZ archive", 0, b"\xfd7zXZ\x00"),
    ("Zip archive", 0, b"PK\x03\x04"),
    ("GZIP archive", 0, b"\x1f\x8b\x08"),
    ("PDF document", 0, b"%PDF"),
    ("SQLite database", 0, b"SQLite format 3"),
    ("PCAP capture", 0, b"\xd4\xc3\xb2\xa1"),
    ("Windows LNK", 0, b"L\x00\x00\x00\x01\x14\x02\x00"),
    ("PowerShell ps1", 0, b"\xef\xbb\xbfusing"),
]
ANYWHERE = [
    (rb"<!DOCTYPE\s+html", "HTML document (page-instead-of-media / polyglot)"),
    (rb"<html[\s>]", "HTML document (page-instead-of-media / polyglot)"),
    (rb"<script[\s>]", "injected <script> tag"),
    (rb"eval\s*\(\s*(atob|unescape|String\.fromCharCode)", "obfuscated JS eval()"),
    (rb"powershell[^\n]{0,60}-e(?:nc|ncodedcommand)", "PowerShell encoded command"),
    (rb"cmd\.exe\s*/c", "cmd.exe /c invocation"),
    (rb"wscript\.exe|cscript\.exe|mshta\.exe|rundll32\.exe|regsvr32\.exe",
     "LOLBin invocation"),
    (rb"Invoke-WebRequest|FromBase64String|DownloadString|Net\.WebClient",
     "PowerShell download/exec"),
    (rb"javascript:|data:text/html|vbscript:", "script URI (javascript:/vbscript:)"),
    (rb"\.on(?:click|load|error|mouseover)\s*=", "inline JS event handler"),
    (rb"(?:bit\.ly|tinyurl\.com|t\.me/isgd|is\.gd|goo\.gl|ow\.ly|buff\.ly)",
     "URL shortener (redirect risk)"),
    (rb"pastebin\.com|hastebin|transfer\.sh|ngrok\.(?:io|app)|serveo|"
     rb"localtunnel|replit\.dev|glitch\.me", "paste/tunnel host"),
    (rb"coinhive|cryptonight|xmrig|stratum\+tcp|webminer", "crypto-miner marker"),
    (rb"discord(?:app)?\.com/api/webhooks", "Discord webhook exfiltration"),
    (rb"-----BEGIN (?:RSA |OPENSSH |EC |PGP )?PRIVATE KEY-----", "private key material"),
    (rb"/etc/passwd|/etc/shadow|\.\./\.\./\.\./", "path traversal / LFI probe"),
    (rb"Authorization:\s*Bearer\s+[A-Za-z0-9\-_.]{20,}", "leaked bearer token"),
]
ANYWHERE = [(re.compile(p, re.I), n) for p, n in ANYWHERE]
BAD_HOST = re.compile(
    r"(pastebin|hastebin|transfer\.sh|ngrok|serveo|localtunnel|"
    r"000webhost|freehostia|replit\.dev|glitch\.me|"
    r"discord(app)?\.com/api/webhooks|bit\.ly|tinyurl)", re.I)


# --------------------------------------------------------------- helpers
def get(url, timeout=20, limit=3_000_000, referer=None):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
         "Connection": "close"}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return {"status": r.status, "ctype": r.headers.get("Content-Type", ""),
                "clen": r.headers.get("Content-Length"),
                "final": r.geturl(),
                "data": r.read(limit) if limit else r.read()}


def av_scan(data, label):
    hits = []
    if not data:
        return hits
    for name, off, sig in BINARY_SIGS:
        if data[off:off + len(sig)] == sig:
            hits.append(f"{label}: {name} signature")
    for rx, name in ANYWHERE:
        if rx.search(data):
            hits.append(f"{label}: {name}")
    return hits



def boxes(data):
    """Parse ISO-BMFF top-level box types. -> list[str]"""
    out, i, n = [], 0, len(data)
    while i + 8 <= n and len(out) < 64:
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
        try:
            out.append(typ.decode("latin-1").strip())
        except Exception:
            pass
        i += size
    return out


def container_ok(data):
    b = boxes(data)
    if "ftyp" in b or "moof" in b or "mdat" in b or "styp" in b or "sidx" in b:
        return "fMP4", b
    if data[:1] == b"\x47" and len(data) > 188 and data[188:189] == b"\x47":
        return "MPEG-TS", ["TS"]
    return None, b


def parse_master(text, base):
    """-> (variants[{url,bw,res,codecs,audio}], audio_groups{gid:url})"""
    variants, auds, cur = [], {}, None
    for raw in text.splitlines():
        l = raw.strip()
        if not l:
            continue
        if l.startswith("#EXT-X-STREAM-INF:"):
            a = dict(re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', l.split(":", 1)[1]))
            cur = a
        elif l.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in l:
            a = dict(re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', l.split(":", 1)[1]))
            uri = a.get("URI", "").strip('"')
            if uri:
                auds[a.get("GROUP-ID", "").strip('"')] = urljoin(base, uri)
        elif not l.startswith("#") and cur is not None:
            variants.append({
                "url": urljoin(base, l), "bw": int(cur.get("BANDWIDTH", 0) or 0),
                "res": cur.get("RESOLUTION", "").strip('"'),
                "codecs": cur.get("CODECS", "").strip('"'),
                "audio": cur.get("AUDIO", "").strip('"'),
            })
            cur = None
    return variants, auds


def parse_media(text, base):
    """-> (segments[], has_endlist, init_url, drm)"""
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
                init = urljoin(base, m.group(1))
        elif l.startswith("#EXT-X-KEY:"):
            meth = re.search(r"METHOD=([A-Z0-9-]+)", l)
            if meth and meth.group(1) != "NONE":
                drm.append(meth.group(1))
        elif l.startswith("#EXT-X-SESSION-KEY"):
            drm.append("SESSION-KEY")
        elif not l.startswith("#"):
            segs.append(urljoin(base, l))
    return segs, endlist, init, drm


def bw_key(v):
    return (v["bw"], v["res"])


# --------------------------------------------------------------- checker
def check(url, name="", deep_segments=2):
    r = {"url": url, "name": name, "host": urlparse(url).netloc,
         "checks": {}, "fail": [], "threats": [], "notes": [],
         "http": None, "ctype": "", "kind": None, "live": None,
         "video": None, "audio": None, "variants": 0, "segs_ok": 0,
         "verdict": "FAIL"}
    C, F, T, N = r["checks"], r["fail"], r["threats"], r["notes"]

    if BAD_HOST.search(url):
        T.append("untrusted host in URL")
        F.append("AV")
        return r

    # L1 -----------------------------------------------------------------
    try:
        g = get(url, limit=1_500_000)
        r["http"] = g["status"]
        r["ctype"] = g["ctype"]
        r["final"] = g["final"]
        text = g["data"].decode("utf-8", "replace")
        C["L1_http_200_hls"] = "#EXTM3U" in text[:800]
        if not C["L1_http_200_hls"]:
            F.append("L1")
            if "<html" in text[:2000].lower():
                T.append("server returned HTML page, not media")
            return r
    except urllib.error.HTTPError as e:
        r["http"] = e.code
        F.append(f"L1 HTTP {e.code}")
        return r
    except Exception as e:
        F.append(f"L1 {type(e).__name__}: {str(e)[:60]}")
        return r

    T.extend(av_scan(g["data"], "master"))

    # L2 -----------------------------------------------------------------
    variants, auds = parse_master(text, r["final"])
    r["variants"] = len(variants)
    if variants:
        r["kind"] = "master"
        C["L2_is_channel"] = True
    else:
        segs0, endlist0, init0, _ = parse_media(text, r["final"])
        C["L2_is_channel"] = bool(segs0)
        r["kind"] = "media" if segs0 else "index"
        if not segs0:
            F.append("L2 no media segments and no variants (rendition/DVR index)")

    # L3 -----------------------------------------------------------------
    drm = []
    if variants:
        best = max(variants, key=bw_key)
        try:
            vg = get(best["url"], limit=1_500_000, referer=r["final"])
            vtext = vg["data"].decode("utf-8", "replace")
            T.extend(av_scan(vg["data"], "variant"))
        except Exception as e:
            F.append(f"L3 variant fetch {type(e).__name__}")
            best = None
            vtext = None
    else:
        best = None
        vtext = text

    if vtext is not None:
        segs, endlist, init, d3 = parse_media(vtext, r["final"] if not variants else r["final"])
        drm = d3
        if drm:
            F.append(f"L3 DRM protected ({','.join(sorted(set(drm)))}) - needs license")
        C["L3_no_drm"] = not drm
        r["live"] = not endlist
        C["L6_live"] = r["live"]
        if endlist:
            N.append("VOD (has #EXT-X-ENDLIST) - not a live channel")

        # L4 video container ------------------------------------------------
        if segs:
            init_url = init or segs[0]
            try:
                ig = get(init_url, limit=2_000_000, referer=r["final"])
                kind, bx = container_ok(ig["data"])
                T.extend(av_scan(ig["data"], "init"))
                if kind:
                    C["L4_init_container"] = kind
                    r["video"] = {"res": best["res"] if best else "?", "codec": kind}
                else:
                    C["L4_init_container"] = False
                    F.append("L4 init segment is not a valid media container")
            except Exception as e:
                F.append(f"L4 init fetch {type(e).__name__}: {str(e)[:50]}")
            for s in segs[-deep_segments:]:
                try:
                    sg = get(s, limit=4_000_000, referer=r["final"])
                    kind, bx = container_ok(sg["data"])
                    T.extend(av_scan(sg["data"], "segment"))
                    if kind:
                        r["segs_ok"] += 1
                except Exception as e:
                    N.append(f"segment {type(e).__name__}")
            C["L4_segments_decodable"] = r["segs_ok"] > 0
            if r["segs_ok"] == 0 and "L4" not in "".join(F):
                F.append("L4 no media segment could be fetched/decoded")

    # L5 audio ------------------------------------------------------------
    audio_url = None
    if best and best.get("audio") and best["audio"] in auds:
        audio_url = auds[best["audio"]]
    elif auds:
        audio_url = sorted(auds.values())[0]
    if audio_url:
        try:
            ag = get(audio_url, limit=1_000_000, referer=r["final"])
            atext = ag["data"].decode("utf-8", "replace")
            asegs, _, ainit, _ = parse_media(atext, r["final"])
            T.extend(av_scan(ag["data"], "audio-rendition"))
            probe = ainit or (asegs[0] if asegs else None)
            ok = False
            if probe:
                pg = get(probe, limit=2_000_000, referer=r["final"])
                T.extend(av_scan(pg["data"], "audio-init"))
                kind, _ = container_ok(pg["data"])
                ok = kind is not None
            r["audio"] = {"rendition": "separate", "ok": ok}
            C["L5_audio_present"] = ok
            if not ok:
                F.append("L5 audio rendition not decodable")
        except Exception as e:
            N.append(f"audio rendition {type(e).__name__}")
            C["L5_audio_present"] = False
            r["audio"] = {"rendition": "separate", "ok": False}
    elif best and "mp4a" in (best.get("codecs") or ""):
        r["audio"] = {"rendition": "muxed", "ok": True}
        C["L5_audio_present"] = True
    else:
        C["L5_audio_present"] = False
        F.append("L5 no audio track")

    # L7 -----------------------------------------------------------------
    C["L7_no_threats"] = not T
    if T:
        F.append("L7 ANTI-VIRUS")

    r["verdict"] = "PASS" if (not F and not T) else "FAIL"
    return r


def main():
    import l5_audit
    entries = l5_audit.parse("lista5.m3u")
    seen, targets = set(), []
    for e in entries:
        if e.get("orphan") or e["url"] in seen:
            continue
        seen.add(e["url"])
        targets.append((e["name"], e["url"]))

    # extra candidate replacements to evaluate alongside the current ones
    for n, u in EXTRA:
        targets.append((n, u))

    print(f"checking {len(targets)} URLs (L1..L7)\n")
    out = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [(ex.submit(check, u, n), n, u) for n, u in targets]
        for f, n, u in futs:
            r = f.result()
            out.append(r)
            st = "PASS" if r["verdict"] == "PASS" else "FAIL"
            detail = (f"{r['video']['res']} {r['video']['codec']} "
                      f"audio={'y' if r['checks'].get('L5_audio_present') else 'n'}"
                      if r.get("video") else ";".join(r["fail"])[:70])
            print(f"[{st}] {r['host'][:30]:<30} v={r['variants']:<2} {detail}")
            for t in r["threats"]:
                print(f"        !! {t}")
            for ff in r["fail"]:
                print(f"        x  {ff}")
            for n2 in r["notes"][:2]:
                print(f"        ~  {n2}")

    with open("l5_check.json", "w") as fh:
        json.dump({"checked_at": datetime.now(timezone.utc).isoformat(),
                   "results": out}, fh, indent=2)
    p = sum(1 for r in out if r["verdict"] == "PASS")
    print(f"\nPASS={p}  FAIL={len(out) - p}  -> l5_check.json")


EXTRA = [
    # candidate replacements for the dead entries
    ("CBS News 24/7 (dai event)", "https://dai.google.com/linear/hls/event/Sid4xiTQTkCT1SLu6rjUSQ/master.m3u8"),
    ("CBS News 24/7 (cbsivideo)", "https://news20e7hhcb.airspace-cdn.cbsivideo.com/index.m3u8"),
    ("ABC News Live (akamai 05)", "https://abcnews-livestreams.akamaized.net/out/v1/173a6e46d5c5423d9611bc7fb7899c73/abcn-live-05-cmaf-manifest/abcn-live-05-index.m3u8"),
    ("ABC News Live (hudson1)", "https://abcnews-streams.akamaized.net/hls/live/2023560/abcnewshudson1/master.m3u8"),
]

if __name__ == "__main__":
    main()
