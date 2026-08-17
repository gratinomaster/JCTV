#!/bin/bash

INPUT="lista5.m3u"
TMP="lista5_test.m3u"
LOG="test_log.txt"

> "$TMP"
> "$LOG"

echo "#EXTM3U" > "$TMP"

total=0
working=0
failed=0

while IFS= read -r line; do
    if [[ "$line" == "#EXTINF:"* ]]; then
        extinf="$line"
        read -r url
        total=$((total + 1))
        channel_name=$(echo "$extinf" | sed 's/.*,\(.*\)/\1/')
        http_code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 15 --connect-timeout 10 -A "Mozilla/5.0" "$url" 2>/dev/null)
        if [[ "$http_code" -ge 200 && "$http_code" -lt 400 ]]; then
            echo "$extinf" >> "$TMP"
            echo "$url" >> "$TMP"
            working=$((working + 1))
            echo "[OK] ($http_code) $channel_name" >> "$LOG"
        else
            failed=$((failed + 1))
            echo "[FAIL] ($http_code) $channel_name" >> "$LOG"
        fi
    fi
done < "$INPUT"

cp "$TMP" "$INPUT"
rm -f "$TMP"

echo "=== Resultado ==="
echo "Total: $total | Funcionando: $working | Falhando: $failed"
echo ""
cat "$LOG"
