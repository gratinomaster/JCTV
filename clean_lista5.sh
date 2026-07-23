#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_clean.m3u"
RESULTS_FILE="/tmp/channel_validation.txt"

# First run the test to get results
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

        if [[ "$HTTP_CODE" == "200" && ("$HAS_HLS" -gt 0 || "$HAS_M3U" -gt 0) && "$HAS_ERROR" == "0" ]]; then
            STATUS="WORKING"
        else
            STATUS="FAIL"
        fi

        echo "$STATUS|$CHANNEL_NUM|$EXTINF_LINE|$URL_LINE" >> "$RESULTS_FILE"

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

# Now create clean file with only working channels
echo "#EXTM3U" > "$OUTPUT_FILE"

while IFS='|' read -r status num extinf url; do
    if [[ "$status" == "WORKING" ]]; then
        echo "$extinf" >> "$OUTPUT_FILE"
        echo "$url" >> "$OUTPUT_FILE"
    fi
done < "$RESULTS_FILE"

echo "========================================="
echo "LIMPEZA CONCLUIDA"
echo "========================================="
echo "Arquivo original: $INPUT_FILE"
echo "Arquivo limpo: $OUTPUT_FILE"
echo "Canais mantidos: $(grep -c "^WORKING|" "$RESULTS_FILE")"
echo "Canais removidos: $(grep -c "^FAIL|" "$RESULTS_FILE")"
echo "========================================="