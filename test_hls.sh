#!/bin/bash

INPUT_FILE="lista5.m3u"
RESULTS_FILE="/tmp/channel_validation.txt"

> "$RESULTS_FILE"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0

while IFS= read -r line; do
    if [[ "$line" == "#EXTM3U" ]]; then
        continue
    fi

    if [[ "$line" == "#EXTINF"* ]]; then
        EXTINF_LINE="$line"
        continue
    fi

    if [[ -n "$EXTINF_LINE" && -n "$line" && "$line" != "#"* ]]; then
        URL_LINE="$line"
        CHANNEL_NUM=$((CHANNEL_NUM + 1))

        RESPONSE=$(curl -s --max-time 10 -L "$URL_LINE" 2>/dev/null)
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -L "$URL_LINE" 2>/dev/null)

        HAS_HLS=$(echo "$RESPONSE" | grep -c "#EXT-X-")
        HAS_M3U=$(echo "$RESPONSE" | grep -c "#EXTM3U")
        HAS_ERROR=$(echo "$RESPONSE" | grep -ci "error\|expired\|unauthorized\|forbidden\|not found\|403\|404")

        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        if [[ "$HTTP_CODE" == "200" && ("$HAS_HLS" -gt 0 || "$HAS_M3U" -gt 0) && "$HAS_ERROR" == "0" ]]; then
            STATUS="WORKING"
        else
            STATUS="FAIL"
        fi

        echo "$STATUS|$CHANNEL_NUM|$HTTP_CODE|HLS=$HAS_HLS|ERR=$HAS_ERROR|$NAME" >> "$RESULTS_FILE"

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

WORKING=$(grep -c "^WORKING|" "$RESULTS_FILE")
FAILING=$(grep -c "^FAIL|" "$RESULTS_FILE")

echo "========================================="
echo "VALIDACAO DE CONTEUDO HLS"
echo "========================================="
echo "Total testados: $CHANNEL_NUM"
echo "Funcionando:    $WORKING"
echo "Nao funcionando: $FAILING"
echo "========================================="
echo ""
echo "Canais FAIL:"
grep "^FAIL|" "$RESULTS_FILE" | while IFS='|' read -r status num http hls err name; do
    echo "  [$num] HTTP=$http $hls $err - $name"
done
