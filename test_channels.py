import urllib.request
import urllib.error
import sys
import os

M3U_FILE = "lista5.m3u"
TIMEOUT = 10

def test_url(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status < 400
    except Exception:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.status < 400
        except Exception:
            return False

def main():
    if not os.path.exists(M3U_FILE):
        print(f"Error: {M3U_FILE} not found")
        sys.exit(1)

    with open(M3U_FILE, "r") as f:
        lines = [line.rstrip("\n") for line in f.readlines()]

    if not lines or lines[0] != "#EXTM3U":
        print("Error: Invalid M3U file (missing #EXTM3U header)")
        sys.exit(1)

    header = lines[0]
    entries = []
    i = 1
    while i < len(lines):
        if lines[i].startswith("#EXTINF:"):
            if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                entries.append((lines[i], lines[i + 1]))
                i += 2
            else:
                print(f"Warning: EXTINF at line {i+1} without URL, skipping")
                i += 1
        else:
            print(f"Warning: Unexpected line {i+1}: {lines[i][:60]}..., skipping")
            i += 1

    print(f"Found {len(entries)} channel entries to test\n")

    working_entries = []
    for idx, (extinf, url) in enumerate(entries, 1):
        name = extinf.split(",")[-1] if "," in extinf else "Unknown"
        print(f"[{idx}/{len(entries)}] Testing: {name[:50]}...", end=" ")
        sys.stdout.flush()
        if test_url(url):
            working_entries.append((extinf, url))
            print("OK")
        else:
            print("FAIL")

    with open(M3U_FILE, "w") as f:
        f.write(header + "\n")
        for extinf, url in working_entries:
            f.write(extinf + "\n")
            f.write(url + "\n")

    print(f"\nDone. {len(working_entries)}/{len(entries)} channels working. {M3U_FILE} updated.")

if __name__ == "__main__":
    main()
