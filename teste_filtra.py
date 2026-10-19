#!/usr/bin/env python3
"""Testa todos os canais de lista5.m3u e remove os que nao funcionam.

 criterio de "funcionando":
   1. URL responde 200/206 com manifesto HLS (#EXTM3U);
   2. se for master playlist, a variante de maior bitrate tambem responde;
   3. o playlist de midia nao exige DRM (SAMPLE-AES/Widevine/PlayReady);
   4. o stream tem video de verdade (rendicao so-audio nao e canal);
   5. o segmento baixado contem midia real (MPEG-TS, fMP4/CMAF ou ADTS/AAC).
"""
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

M3U = "lista5.m3u"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 15
WORKERS = 4
TMPDIR = tempfile.mkdtemp(prefix="m3u_")


def curl(url, rng=None, timeout=TIMEOUT):
    """Retorna (bytes, http_code, content_type)."""
    url = re.sub(r"[\s\x00-\x1f\x7f]", "", url)
    fd, path = tempfile.mkstemp(dir=TMPDIR)
    os.close(fd)
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
           "-w", "\n@@@%{http_code}|%{content_type}", "-o", path]
    if rng:
        cmd += ["-r", rng]
    cmd.append(url)
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        os.unlink(path)
        return b"", 0, ""
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError:
        body = b""
    finally:
        os.unlink(path)
    meta = r.stdout.strip().split(b"@@@")[-1] if b"@@" in r.stdout else b"0|"
    code_s, _, ctype = meta.partition(b"|")
    try:
        code = int(code_s)
    except ValueError:
        code = 0
    return body, code, ctype.decode("utf-8", "replace")


def is_media(data):
    """Confirma que o segmento traz midia de verdade."""
    if not data or len(data) < 128:
        return False
    if data[:1] == b"\x47":
        return True
    head = data[:96]
    for tag in (b"styp", b"moof", b"sidx", b"ftyp", b"mdat"):
        if tag in head:
            return True
    if data[0] == 0xFF and (data[1] & 0xF0) == 0xF0:
        return True
    if data[:3] == b"ID3":
        return True
    return False


VIDEO_CODEC_RE = re.compile(
    r"avc[13]|hvc1|hev1|dvh1|dvhe|vp0[89]|av01|h264|hevc|mpeg-?2", re.I)


def pick_variant(text, base):
    """Retorna (url, codecs) da variante de maior bitrate."""
    best, bw, codecs = None, -1, ""
    for m in re.finditer(r"#EXT-X-STREAM-INF:([^\n]*)\n([^\s#]+)", text):
        attrs = m.group(1)
        bwm = re.search(r"BANDWIDTH=(\d+)", attrs)
        cur = int(bwm.group(1)) if bwm else 0
        if cur > bw:
            cm = re.search(r'CODECS="([^"]*)"', attrs)
            bw, best = cur, m.group(2).strip()
            codecs = cm.group(1) if cm else ""
    if best:
        return urllib.parse.urljoin(base, best), codecs
    return None, ""


VIDEO_SAMPLE_ENTRIES = {
    b"avc1", b"avc3", b"hvc1", b"hev1", b"dvav", b"dva1", b"dvhe", b"dvh1",
    b"vp08", b"vp09", b"av01", b"mp4v",
}


def mp4_has_video(data):
    """Le os fourcc das entradas de sample (stsd) de um init segment."""
    hits = []
    i = -1
    while True:
        i = data.find(b"stsd", i + 1)
        if i < 0:
            break
        # stsd: size(4) type(4) ver+flags(4) entry_count(4) | entradas
        p, end = i + 12, min(len(data), i + 256)
        while p + 8 <= end:
            size = int.from_bytes(data[p:p + 4], "big")
            hits.append(data[p + 4:p + 8])
            if size < 8:
                break
            p += size
    if not hits:
        return None
    return any(f in VIDEO_SAMPLE_ENTRIES for f in hits)


def init_has_video(text, base):
    """True/False se da pra afirmar pelo init segment; None se inconclusivo."""
    m = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
    if not m:
        return None
    data, code, _ = curl(urllib.parse.urljoin(base, m.group(1)), rng="0-8191")
    if code not in (200, 206) or not data:
        return None
    return mp4_has_video(data)


def drm_reason(text):
    """Retorna motivo se o playlist exige DRM (inassistivel em players)."""
    if re.search(r"METHOD=SAMPLE-AES", text, re.I):
        return "DRM (SAMPLE-AES)"
    if re.search(r"urn:uuid:(edef8ba9|9a04f079|f6dd3613|1077efec)", text, re.I):
        return "DRM (Widevine/PlayReady)"
    if re.search(r'"com\.microsoft\.playready"', text, re.I):
        return "DRM (PlayReady)"
    if re.search(r'"com\.apple\.streamingkeydelivery"', text, re.I):
        return "DRM (FairPlay)"
    if re.search(r'KEYFORMAT="?(PRMNAGRA|nagra)', text, re.I):
        return "DRM (Nagra)"
    return None


def segment_ok(text, base):
    """Baixa um segmento e confirma midia valida."""
    segs = [l.strip() for l in text.splitlines()
            if l.strip() and not l.strip().startswith("#")]
    if not segs:
        m = re.search(r'#EXT-X-MAP:URI="([^"]+)"', text)
        if not m:
            return False, "playlist sem segmentos"
        segs = [m.group(1)]
    # live: a borda nova nem sempre esta pronta -> testa o ultimo e o primeiro
    cand = list(dict.fromkeys([segs[-1], segs[0]]))
    code = 0
    for seg in cand:
        sb, sc, _ = curl(urllib.parse.urljoin(base, seg), rng="0-4095")
        code = sc
        if sc in (200, 206) and is_media(sb):
            return True, ""
    return False, f"segmento sem midia valida (http {code})"


def test_once(url):
    body, code, _ = curl(url)
    if code not in (200, 206):
        return False, f"http {code}"
    if b"#EXTM3U" not in body:
        return False, "nao e manifesto HLS"
    text = body.decode("utf-8", "replace")
    base = url
    video = None
    if "#EXT-X-STREAM-INF" in text:
        variant, codecs = pick_variant(text, url)
        if not variant:
            return False, "master sem variante"
        if codecs and not VIDEO_CODEC_RE.search(codecs):
            return False, "apenas audio (sem variante de video)"
        video = bool(codecs and VIDEO_CODEC_RE.search(codecs))
        body, code, _ = curl(variant)
        if code not in (200, 206) or b"#EXTM3U" not in body:
            return False, f"variante inacessivel (http {code})"
        text = body.decode("utf-8", "replace")
        base = variant
    reason = drm_reason(text)
    if reason:
        return False, reason
    if video is None:
        video = init_has_video(text, base)
        if video is False:
            return False, "apenas audio (init sem pista de video)"
    return segment_ok(text, base)


def test_url(url):
    """Retorna (ok, motivo). Falhas transitórias sao retestadas."""
    ok, why = test_once(url)
    if ok or why.startswith("DRM"):
        return ok, why
    return test_once(url)


def parse(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = [l.rstrip("\n") for l in f]
    header = lines[0] if lines else "#EXTM3U"
    entries = []
    i = 1
    while i < len(lines):
        s = lines[i].strip()
        i += 1
        if not s.startswith("#EXTINF"):
            continue
        url = None
        while i < len(lines):
            l2 = lines[i].strip()
            i += 1
            if not l2 or l2.startswith("#"):
                if l2.startswith("#EXTINF"):
                    i -= 1
                continue
            url = l2
            break
        entries.append((s, url))
    return header, entries


def main():
    check_only = "--check" in sys.argv
    header, entries = parse(M3U)

    # remove duplicatas exatas (mesmo #EXTINF + mesma URL)
    seen, unique = set(), []
    for extinf, url in entries:
        key = (extinf, url)
        if key in seen:
            continue
        seen.add(key)
        unique.append((extinf, url))
    if len(unique) != len(entries):
        print(f"Duplicatas exatas removidas: {len(entries) - len(unique)}")
    entries = unique

    print(f"Testando {len(entries)} entradas de {M3U}...\n")

    urls = {u for _, u in entries if u}
    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for u, res in zip(urls, ex.map(test_url, urls)):
            results[u] = res

    # CDN pode engasgar com requisicoes paralelas: revalida as falhas,
    # uma a uma, antes de decidir a remocao
    for u in [u for u, (ok, _) in results.items() if not ok]:
        results[u] = test_url(u)

    kept, removed = [], []
    for extinf, url in entries:
        name = extinf.split(",")[-1].strip() if "," in extinf else extinf
        if not url:
            removed.append((name, "sem URL", ""))
            continue
        ok, why = results[url]
        if ok:
            kept.append((extinf, url))
            print(f"OK     {name[:70]}")
        else:
            removed.append((name, why, url))
            print(f"REMOVO {name[:70]} ({why})")

    print(f"\nMantidos: {len(kept)}/{len(entries)} | Removidos: {len(removed)}")
    if removed:
        print("Removidos:")
        for name, why, url in removed:
            print(f"  - {name[:70]} ({why})")
            if url:
                print(f"      {url[:110]}")

    if check_only:
        print("\n(--check: arquivo nao alterado)")
        return 0

    with open(M3U, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for extinf, url in kept:
            f.write(extinf + "\n" + url + "\n")
    print(f"\n{M3U} sobrescrito com {len(kept)} canais")
    return 0


if __name__ == "__main__":
    sys.exit(main())
