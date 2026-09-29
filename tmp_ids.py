import requests, re, sys

H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
BASE = "https://raw.githubusercontent.com/iptv-org/iptv/master/"

# find channel ids from CHANNELS.m3u
ch = requests.get(BASE + "CHANNELS.m3u", headers=H, timeout=60).text
targets = ["ABC News", "Fox News", "Fox Business", "CBS News"]
ids = {}
for line in ch.splitlines():
    if not line.startswith("#EXTINF"):
        continue
    m = re.search(r',(.+)$', line)
    name = m.group(1).strip() if m else ""
    for t in targets:
        if name.lower() == t.lower():
            cid = line.split(":")[0].split(",")[0].split('"')[-1]
            tvg = re.search(r'tvg-id="([^"]*)"', line)
            cc = re.search(r'group-title="([^"]*)"', line)
            print("CHANNEL:", name, "| id=", cid, "| tvg-id=", tvg.group(1) if tvg else None, "| group=", cc.group(1) if cc else None)
            ids.setdefault(t, []).append((cid, tvg.group(1) if tvg else ""))
print("IDS:", json.dumps(ids) if False else ids)
