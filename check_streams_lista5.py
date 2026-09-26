#!/usr/bin/env python3
"""Testa cada canal do lista5.m3u decodificando frames reais via ffprobe/ffmpeg
e reescreve o arquivo removendo os canais que nao funcionam.

Uso:
    python3 check_streams_lista5.py --dry-run
    python3 check_streams_lista5.py
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

M3U_FILE = "lista5.m3u"
REPORT_FILE = "stream_check_lista5.json"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

ATTEMPTS = 3
PROBE_TIMEOUT = 30
DECODE_TIMEOUT = 45
RW_TIMEOUT_US = 15_000_000
READ_SECONDS = 3

VIDEO_OK = "A/V_OK"
SILENT = "VIDEO_ONLY"
AUDIO_ONLY = "AUDIO_ONLY"
DEAD = "DEAD"


def find_binaries():
    probe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not probe or not ffmpeg:
        print("ERRO: ffprobe/ffmpeg nao encontrados no PATH.", file=sys.stderr)
        sys.exit(2)
    return probe, ffmpeg


def run(cmd, timeout):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


def probe_streams(ffprobe, url):
    """Retorna (tipos_de_stream, descricao) lendo o cabecalho do stream."""
    proc = run([
        ffprobe, "-v", "error", "-user_agent", UA,
        "-rw_timeout", str(RW_TIMEOUT_US),
        "-probesize", "5000000",
        "-show_entries", "stream=codec_type,codec_name",
        "-of", "json", url,
    ], PROBE_TIMEOUT)
    if proc is None or proc.returncode != 0:
        return [], "probe falhou/timeout"
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return [], "json invalido"
    streams = [(s.get("codec_type"), s.get("codec_name", "?"))
               for s in data.get("streams", [])]
    return streams, ""


def decode_test(ffmpeg, url):
    """Decodifica alguns frames. Retorna (ok, nframes, erro)."""
    proc = run([
        ffmpeg, "-v", "error", "-nostdin", "-user_agent", UA,
        "-rw_timeout", str(RW_TIMEOUT_US),
        "-i", url, "-t", str(READ_SECONDS),
        "-map", "0:v:0?", "-map", "0:a:0?", "-f", "null", "-",
    ], DECODE_TIMEOUT)
    if proc is None:
        return False, 0, "decode timeout"
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, 0, err.splitlines()[-1] if err else f"exit {proc.returncode}"
    return True, 1, err


def check_one(ffprobe, ffmpeg, url):
    last_err = ""
    for attempt in range(1, ATTEMPTS + 1):
        streams, perr = probe_streams(ffprobe, url)
        if perr:
            last_err = perr
        else:
            types = {t for t, _ in streams}
            if not types:
                last_err = "nenhum stream encontrado"
            else:
                ok, _, derr = decode_test(ffmpeg, url)
                if not ok:
                    last_err = derr or "decode falhou"
                elif "video" in types and "audio" in types:
                    return VIDEO_OK, streams, ""
                elif "video" in types:
                    return SILENT, streams, "video sem audio (mudo)"
                else:
                    return AUDIO_ONLY, streams, "apenas audio (radio)"
        if attempt < ATTEMPTS:
            time.sleep(2 * attempt)
    return DEAD, streams, last_err


def parse_m3u(path):
    """Retorna (header_lines, [(atributos, nome, url, linhas_extra)])."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    header, entries, i = [], [], 0
    while i < len(lines) and not lines[i].startswith("#EXTINF"):
        if lines[i].strip():
            header.append(lines[i])
        i += 1

    pending = []
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            pending = [(i, line)]
        elif line.strip() and not line.startswith("#") and pending:
            idx, extinf = pending[0]
            entries.append((extinf, line))
            pending = []
        elif line.strip() and not line.startswith("#"):
            entries.append((pending[0][1] if pending else "", line))
            pending = []
        i += 1
    return header, entries


def channel_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", default=M3U_FILE)
    args = ap.parse_args()

    ffprobe, ffmpeg = find_binaries()
    header, entries = parse_m3u(args.file)
    print(f"Arquivo : {args.file}")
    print(f"Canais  : {len(entries)}")
    print(f"Unicos  : {len({u for _, u in entries})}\n")

    cache, results, order = {}, [], []
    for n, (extinf, url) in enumerate(entries, 1):
        if url not in cache:
            status, streams, err = check_one(ffprobe, ffmpeg, url)
            cache[url] = (status, streams, err)
            flag = {VIDEO_OK: "A/V OK ", SILENT: "MUDO  ",
                    AUDIO_ONLY: "AUDIO ", DEAD: "FALHOU"}[status]
            detail = streams and ",".join(
                f"{c}({t})" for t, c in streams) or err
            print(f"  [{n:2d}/{len(entries)}] {flag} {channel_name(extinf)[:46]:46s} {detail[:60]}")
        status, streams, err = cache[url]
        results.append({"name": channel_name(extinf), "url": url,
                        "extinf": extinf, "status": status,
                        "streams": streams, "error": err})
        order.append(url)

    ok = [r for r in results if r["status"] == VIDEO_OK]
    silent = [r for r in results if r["status"] == SILENT]
    audio = [r for r in results if r["status"] == AUDIO_ONLY]
    dead = [r for r in results if r["status"] == DEAD]

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 62)
    print(f"Total testados      : {len(results)}")
    print(f"Funcionando (A+V)   : {len(ok)}")
    print(f"Video sem audio     : {len(silent)}")
    print(f"Apenas audio        : {len(audio)}")
    print(f"Nao funcionando     : {len(dead)}")
    print("=" * 62)
    if dead:
        print("\nRemovidos (nao funcionam):")
        for r in dead:
            print(f"  - {r['name'][:60]} :: {r['error'][:70]}")
    if silent:
        print("\nRemovidos (video mudo, sem audio):")
        for r in silent:
            print(f"  - {r['name'][:60]} :: ...{r['url'][-70:]}")
    if audio:
        print("\nRemovidos (apenas audio, nao e canal):")
        for r in audio:
            print(f"  - {r['name'][:60]} :: ...{r['url'][-70:]}")

    if args.dry_run:
        print("\n[dry-run] lista5.m3u nao foi alterado.")
        return

    if len(ok) == len(results):
        print("\nNenhum canal removido; arquivo mantido como esta.")
        return

    out = list(header) or ["#EXTM3U"]
    if not out[0].startswith("#EXTM3U"):
        out.insert(0, "#EXTM3U")
    for r in ok:
        out.append(r["extinf"])
        out.append(r["url"])

    tmp = args.file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.replace(tmp, args.file)
    print(f"\n{args.file} reescrito: {len(ok)} canais mantidos, "
          f"{len(results) - len(ok)} removidos.")
    print(f"Backup: lista5.m3u.bak.{datetime.now():%Y%m%d_%H%M%S}_pre_test")


if __name__ == "__main__":
    main()
