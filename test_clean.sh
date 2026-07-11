#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5.m3u"
TEMP_FILE="/tmp/lista5_new.m3u"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0
WORKING=0
FAILING=0

echo "#EXTM3U" > "$TEMP_FILE"

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

        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 -L "$URL_LINE" 2>/dev/null)
        RESPONSE=$(curl -s --max-time 10 -L "$URL_LINE" 2>/dev/null)
        HAS_HLS=$(echo "$RESPONSE" | grep -c "#EXT-X-")

        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        if [[ "$HTTP_CODE" == "200" && "$HAS_HLS" -gt 0 ]]; then
            echo "$EXTINF_LINE" >> "$TEMP_FILE"
            echo "$URL_LINE" >> "$TEMP_FILE"
            WORKING=$((WORKING + 1))
            echo "  OK [$CHANNEL_NUM] $NAME"
        else
            FAILING=$((FAILING + 1))
            echo "  FAIL [$CHANNEL_NUM] HTTP=$HTTP_CODE HLS=$HAS_HLS - $NAME"
        fi

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

cp "$TEMP_FILE" "$OUTPUT_FILE"

echo ""
echo "========================================="
echo "RESULTADO FINAL"
echo "========================================="
echo "Total: $CHANNEL_NUM"
echo "Mantidos: $WORKING"
echo "Removidos: $FAILING"
echo "========================================="
