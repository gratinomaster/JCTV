import re, requests, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"

def parse_m3u(path):
    with open(path,encoding='utf-8') as f:
        lines=[l.rstrip() for l in f]
    channels=[]
    info=None
    for l in lines:
        if l.startswith('#EXTINF'):
            info=l
        elif l.startswith('#') or not l:
            continue
        else:
            channels.append((info,l))
            info=None
    return channels

def fetch_one(url):
    try:
        r=requests.get(url,headers={'User-Agent':UA},timeout=20,stream=True,allow_redirects=True)
        ct=r.headers.get('content-type','')
        if r.status_code!=200:
            return (False,f'HTTP {r.status_code}')
        # read a bit
        data=b''
        for chunk in r.iter_content(65536):
            data+=chunk
            if len(data)>=150000: break
        low=data[:100000].lower()
        is_hls=b'#extm3u' in low or b'#ext-x-stream-inf' in low or b'application/' in ct or 'mpegurl' in ct or 'apple' in ct
        n_st=b'#ext-x-stream-inf' in low
        return (is_hls, f'{ct} | bytes={len(data)} | STREAM-INF={bool(n_st)}')
    except Exception as e:
        return (False, f'ERRO {type(e).__name__}: {e}')

channels=parse_m3u('lista5.m3u')
# dedup by url
seen=set(); uniq=[]
for info,url in channels:
    if url not in seen:
        seen.add(url); uniq.append((info,url))
print(f'Total entradas: {len(channels)} | URL unicas: {len(uniq)}')
results={}
with ThreadPoolExecutor(max_workers=8) as ex:
    futmap={ex.submit(fetch_one,u):(i,u) for i,u in uniq}
    for fut in as_completed(futmap):
        i,u=futmap[fut]
        ok,det=fut.result()
        results[u]=(ok,det)
        name=re.sub(r'^.*?,(.*)$',r'\1',i)[:44] if i else u[:44]
        print(f"{'OK ' if ok else 'FAIL'} | {name:44s} | {det}")
print('---RESUMO---')
working=[u for u,v in results.items() if v[0]]
dead=[u for u,v in results.items() if not v[0]]
print('WORKING:',len(working),'DEAD:',len(dead))
import json
json.dump({u:(v[0],v[1]) for u,v in results.items()},open('stream_test_full.json','w'),ensure_ascii=False,indent=1)
