#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5.m3u.tmp"

echo "#EXTM3U" > "$OUTPUT_FILE"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0
WORKING=0
FAILING=0

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
            echo "$EXTINF_LINE" >> "$OUTPUT_FILE"
            echo "$URL_LINE" >> "$OUTPUT_FILE"
            WORKING=$((WORKING + 1))
            echo "[$CHANNEL_NUM] WORKING - $NAME"
        else
            FAILING=$((FAILING + 1))
            echo "[$CHANNEL_NUM] FAIL (HTTP=$HTTP_CODE, HLS=$HAS_HLS, ERR=$HAS_ERROR) - $NAME"
        fi

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

mv "$OUTPUT_FILE" "$INPUT_FILE"

echo ""
echo "========================================="
echo "LIMPEZA CONCLUIDA"
echo "========================================="
echo "Total testados: $CHANNEL_NUM"
echo "Funcionando:    $WORKING"
echo "Nao funcionando: $FAILING"
echo "========================================="