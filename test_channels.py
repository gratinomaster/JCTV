import asyncio
import aiohttp
import sys

async def test_url(session, url, timeout=10):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=True) as resp:
            return url, resp.status == 200, resp.status
    except asyncio.TimeoutError:
        return url, False, 'timeout'
    except Exception as e:
        return url, False, f'{type(e).__name__}: {str(e)[:50]}'

async def main():
    with open('lista5.m3u', 'r') as f:
        lines = f.readlines()

    entries = []
    urls = []
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF'):
            if i + 1 < len(lines) and not lines[i+1].startswith('#'):
                url = lines[i+1].strip()
                if url.startswith('http'):
                    entries.append((lines[i], lines[i+1]))
                    urls.append(url)
                    i += 2
                    continue
        i += 1

    print(f"Found {len(urls)} URLs to test", file=sys.stderr)

    connector = aiohttp.TCPConnector(limit=50, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [test_url(session, url) for url in urls]
        results = await asyncio.gather(*tasks)

    working = set()
    dead = []
    error_counts = {}
    for url, ok, detail in results:
        if ok:
            working.add(url)
        else:
            dead.append((url, detail))
            error_counts[detail] = error_counts.get(detail, 0) + 1

    print(f"\nResults: Working={len(working)}, Dead={len(dead)}", file=sys.stderr)
    for detail, count in sorted(error_counts.items(), key=lambda x: -x[1]):
        print(f"  {detail}: {count}", file=sys.stderr)

    with open('lista5.m3u', 'w') as f:
        f.write('#EXTM3U\n')
        kept = 0
        for extinf, url_line in entries:
            if url_line.strip() in working:
                f.write(extinf)
                f.write(url_line)
                kept += 1

    print(f"\nKept {kept} working entries in lista5.m3u", file=sys.stderr)

if __name__ == '__main__':
    asyncio.run(main())
