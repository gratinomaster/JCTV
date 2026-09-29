import re, sys, concurrent.futures as cf
import requests

H = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

lines = [l.strip() for l in open("lista5.m3u", encoding="utf-8", errors="replace") if l.strip()]
urls = [l for l in lines if l.startswith("http")]


def probe(u):
    out = {"url": u[:110]}
    try:
        r = requests.get(u, headers=H, timeout=25, stream=True, allow_redirects=True)
        out["status"] = r.status_code
        ct = r.headers.get("content-type", "")
        out["ct"] = ct
        if "mpegurl" in ct or u.split("?")[0].endswith(".m3u8"):
            txt = r.raw.read(40000, decode_content=True).decode("utf-8", "replace")
            out["is_m3u8"] = txt.lstrip().startswith("#EXTM3U")
            out["is_master"] = "#EXT-X-STREAM-INF" in txt
            out["seg"] = ".ts" in txt or ".m4s" in txt or ".aac" in txt
            out["len"] = len(txt)
        else:
            out["body"] = r.raw.read(200, decode_content=True)[:60]
        r.close()
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"
    return out


with cf.ThreadPoolExecutor(10) as ex:
    for o in ex.map(probe, urls):
        print(o, flush=True)
