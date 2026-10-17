#!/usr/bin/env python3
"""Validador do lista5.m3u (nao modifica a playlist).

Checa:
  1. Todo link fica logo abaixo de uma linha #EXTINF (nunca "solto").
  2. tvg-id presente e existente no EPG; tvg-logo em .jpg (sem imgur).
  3. EPG: baixa os url-tvg/x-tvg-url e confirma programacao para
     hoje, amanha e depois de amanha em cada canal.
  4. Streams: HTTPS + dominio limpo (anti-virus: Spamhaus DBL/SURBL) +
     manifesto HLS real com segmento de video servido.
  5. Logos: respondem 200 com content-type de imagem.
"""
import datetime
import gzip
import io
import re
import shutil
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

M3U = "lista5.m3u"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
TIMEOUT = 25

ok_all = True


def curl(url, rng=None, timeout=TIMEOUT):
    """Retorna (bytes, http_code, content_type)."""
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", UA,
           "-w", "\n@@@%{http_code}|%{content_type}", "-o", "/tmp/opencode/_v.bin"]
    if rng:
        cmd += ["-r", rng]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    meta = r.stdout.strip().split("@@@")[-1] if "@@@" in r.stdout else "0|"
    try:
        body = open("/tmp/opencode/_v.bin", "rb").read()
    except OSError:
        body = b""
    code, _, ctype = meta.partition("|")
    try:
        return body, int(code), ctype
    except ValueError:
        return body, 0, ctype


def dns_listed(domain):
    """Anti-virus via blocklists publicas de malware/phishing (DNS)."""
    if not shutil.which("dig"):
        return False
    for zone in (".dbl.spamhaus.org", ".multi.surbl.org"):
        r = subprocess.run(["dig", "+short", "+time=5", "+tries=1",
                            domain + zone, "A"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("127.") and not line.startswith("127.255."):
                return True
    return False


def parse_channels():
    with open(M3U, encoding="utf-8") as f:
        lines = [l.rstrip("\n") for l in f]

    header = lines[0] if lines else ""
    epgs = []
    m = re.search(r'url-tvg="([^"]*)"', header)
    if m:
        epgs = [u for u in m.group(1).split(",") if u.strip()]
    channels = []
    prev_info = None
    for idx, line in enumerate(lines[1:], start=2):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#EXTINF"):
            prev_info = s
            channels.append({"info": s, "url": None, "line": idx})
        elif s.startswith("#"):
            continue
        else:
            if prev_info is None:
                print(f"[FALHA] linha {idx}: URL sem '#EXTINF' acima -> {s[:70]}")
                global ok_all
                ok_all = False
            if channels:
                channels[-1]["url"] = s
            prev_info = None
    return header, epgs, channels


def check_structure(channels):
    print("== Estrutura ==")
    for ch in channels:
        info = ch["info"]
        name = info.split(",")[-1]
        tid = re.search(r'tvg-id="([^"]*)"', info)
        logo = re.search(r'tvg-logo="([^"]*)"', info)
        if not tid or not tid.group(1):
            print(f"[FALHA] {name}: sem tvg-id")
            globals()["ok_all"] = False
        if not logo or not logo.group(1):
            print(f"[FALHA] {name}: sem tvg-logo")
            globals()["ok_all"] = False
        else:
            lu = logo.group(1)
            if not lu.lower().endswith(".jpg") or "imgur.com" in lu:
                print(f"[FALHA] {name}: logo invalido (precisa .jpg, sem imgur): {lu}")
                globals()["ok_all"] = False
        if not ch["url"] or not ch["url"].startswith("http"):
            print(f"[FALHA] {name}: sem URL")
            globals()["ok_all"] = False
    print(f"  {len(channels)} canais analisados")


def load_epg(url, cache):
    if url in cache:
        return cache[url]
    body, code, _ = curl(url, timeout=60)
    if code != 200 or not body:
        cache[url] = None
        return None
    data = body
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        root = ET.fromstring(data.decode("utf-8", "replace"))
    except ET.ParseError:
        cache[url] = None
        return None
    prog = {}
    for p in root.findall("programme"):
        start = p.get("start", "")
        cid = p.get("channel", "")
        if len(start) >= 8:
            prog.setdefault(cid, set()).add(start[:8])
    cache[url] = prog
    return prog


def check_epg(epgs, channels):
    print("== EPG ==")
    today = datetime.date.today()
    need = {(today + datetime.timedelta(days=d)).strftime("%Y%m%d") for d in range(3)}
    print(f"  datas exigidas: {sorted(need)}")
    cache = {}
    merged = {}
    for u in epgs:
        prog = load_epg(u, cache)
        if prog is None:
            print(f"[FALHA] EPG inacessivel: {u}")
            globals()["ok_all"] = False
            continue
        print(f"  OK  {u} ({len(prog)} canais)")
        for cid, days in prog.items():
            merged.setdefault(cid, set()).update(days)
    for ch in channels:
        tid = re.search(r'tvg-id="([^"]*)"', ch["info"]).group(1)
        days = merged.get(tid, set())
        missing = need - days
        name = ch["info"].split(",")[-1]
        if not days:
            print(f"[FALHA] {name} ({tid}): sem grade no EPG")
            globals()["ok_all"] = False
        elif missing:
            print(f"[FALHA] {name} ({tid}): sem programa em {sorted(missing)}")
            globals()["ok_all"] = False
        else:
            print(f"  OK  {name} ({tid}): hoje+amanha+depois de amanha")


def first_variant(playlist, base):
    txt = playlist.decode("utf-8", "replace")
    best, bw = None, -1
    for m in re.finditer(r"#EXT-X-STREAM-INF:[^\n]*BANDWIDTH=(\d+)[^\n]*\n([^\s#]+)", txt):
        if int(m.group(1)) > bw:
            bw, best = int(m.group(1)), m.group(2)
    if best:
        return urllib.parse.urljoin(base, best)
    lines = [l.strip() for l in txt.splitlines() if l.strip() and not l.startswith("#")]
    return urllib.parse.urljoin(base, lines[-1]) if lines else None


def check_streams(channels):
    print("== Streams (anti-virus + video) ==")
    for ch in channels:
        name = ch["info"].split(",")[-1]
        url = ch["url"]
        host = urllib.parse.urlparse(url).hostname or ""
        if not url.startswith("https://"):
            print(f"[FALHA] {name}: sem HTTPS")
            globals()["ok_all"] = False
            continue
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
            print(f"[FALHA] {name}: host e IP literal")
            globals()["ok_all"] = False
            continue
        if dns_listed(host):
            print(f"[FALHA] {name}: {host} listado em blocklist de malware")
            globals()["ok_all"] = False
            continue
        body, code, ctype = curl(url, rng="0-4000")
        if code not in (200, 206) or b"#EXTM3U" not in body:
            print(f"[FALHA] {name}: manifesto HLS invalido (http {code})")
            globals()["ok_all"] = False
            continue
        variant = first_variant(body, url)
        seg_b, seg_c, seg_t = b"", 0, ""
        if variant:
            pl, pc, _ = curl(variant, rng="0-3000")
            lines = [l.strip() for l in pl.decode("utf-8", "replace").splitlines()
                     if l.strip() and not l.startswith("#")]
            if lines:
                seg = urllib.parse.urljoin(variant, lines[-1])
                seg_b, seg_c, seg_t = curl(seg, rng="0-2000")
        is_ts = seg_b[:1] == b"\x47"
        is_fmp4 = b"styp" in seg_b[:16] or b"moof" in seg_b[:16]
        if seg_c in (200, 206) and (is_ts or is_fmp4) and len(seg_b) > 100:
            print(f"  OK  {name}: HLS video OK ({host})")
        else:
            print(f"[FALHA] {name}: sem segmento de video valido ({host}, http {seg_c})")
            globals()["ok_all"] = False


def check_logos(channels):
    print("== Logos ==")
    for ch in channels:
        name = ch["info"].split(",")[-1]
        logo = re.search(r'tvg-logo="([^"]*)"', ch["info"])
        if not logo:
            continue
        _, code, ctype = curl(logo.group(1), rng="0-200")
        if code in (200, 206) and ctype.startswith("image/"):
            print(f"  OK  {name}: {ctype}")
        else:
            print(f"[FALHA] {name}: logo http {code} / {ctype}")
            globals()["ok_all"] = False


def main():
    print(f"Validando {M3U} em {datetime.datetime.now():%Y-%m-%d %H:%M}\n")
    header, epgs, channels = parse_channels()
    if not header.startswith("#EXTM3U"):
        print("[FALHA] primeira linha nao e #EXTM3U")
        globals()["ok_all"] = False
    if not epgs:
        print("[FALHA] cabecalho sem url-tvg")
        globals()["ok_all"] = False
    print(f"Canais: {len(channels)} | EPGs: {len(epgs)}\n")
    check_structure(channels)
    print()
    check_streams(channels)
    print()
    check_logos(channels)
    print()
    check_epg(epgs, channels)
    print()
    if ok_all:
        print("RESULTADO: TODOS OS TESTES PASSARAM")
        return 0
    print("RESULTADO: HOUVE FALHAS")
    return 1


if __name__ == "__main__":
    sys.exit(main())
