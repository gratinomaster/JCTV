#!/bin/bash

INPUT="/home/runner/work/JCTV/JCTV/lista5.m3u"
OUTPUT="/home/runner/work/JCTV/JCTV/lista5.m3u"
TIMEOUT=10
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

total=0
working=0
failed=0

> /tmp/channels_ok.txt
echo "#EXTM3U" > /tmp/channels_ok.txt

while IFS= read -r extinf; do
    IFS= read -r url || break
    
    total=$((total + 1))
    channel_name=$(echo "$extinf" | grep -oP ',\K.*')
    echo -n "[$total] $channel_name ... "
    
    status=$(curl -s -o /tmp/resp_body.txt -w "%{http_code}" --max-time "$TIMEOUT" -A "$UA" "$url" 2>/dev/null)
    body_head=$(head -c 200 /tmp/resp_body.txt 2>/dev/null)
    
    if ([ "$status" -ge 200 ] && [ "$status" -lt 400 ]) && echo "$body_head" | grep -qiE '#EXTM3U|#EXT-X-|#EXTINF|\.ts|\.m3u8|\.aac|\.mp4'; then
        echo "OK ($status)"
        echo "$extinf" >> /tmp/channels_ok.txt
        echo "$url" >> /tmp/channels_ok.txt
        working=$((working + 1))
    else
        echo "FALHOU (HTTP $status)"
        failed=$((failed + 1))
    fi
done < <(tail -n +2 "$INPUT")

echo ""
echo "=== RESULTADO ==="
echo "Total: $total | Funcionando: $working | Falhou: $failed"

cp /tmp/channels_ok.txt "$OUTPUT"
