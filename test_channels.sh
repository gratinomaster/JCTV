#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_clean.m3u"
RESULTS_FILE="/tmp/channel_results.txt"

> "$RESULTS_FILE"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0

while IFS= read -r line; do
    if [[ "$line" == "#EXTM3U" ]]; then
        echo "$line" > "$OUTPUT_FILE"
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

        if [[ "$HTTP_CODE" == "200" ]]; then
            echo "OK|$CHANNEL_NUM|$HTTP_CODE|$EXTINF_LINE" >> "$RESULTS_FILE"
            echo "$URL_LINE" >> "$RESULTS_FILE"
        else
            echo "FAIL|$CHANNEL_NUM|$HTTP_CODE|$EXTINF_LINE" >> "$RESULTS_FILE"
        fi

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

echo "" >> "$OUTPUT_FILE"
grep "^OK|" "$RESULTS_FILE" | while IFS='|' read -r status num code extinf; do
    url_line=$(grep -A1 "^OK|$num|" "$RESULTS_FILE" | tail -1)
    echo "$extinf" >> "$OUTPUT_FILE"
    echo "$url_line" >> "$OUTPUT_FILE"
done

TOTAL=$CHANNEL_NUM
WORKING=$(grep -c "^OK|" "$RESULTS_FILE")
FAILING=$(grep -c "^FAIL|" "$RESULTS_FILE")

echo "========================================="
echo "TESTE DE CANAIS CONCLUIDO"
echo "========================================="
echo "Total testados: $TOTAL"
echo "Funcionando:    $WORKING"
echo "Nao funcionando: $FAILING"
echo "========================================="
echo ""
echo "Canais FAIL:"
grep "^FAIL|" "$RESULTS_FILE" | while IFS='|' read -r status num code extinf; do
    name=$(echo "$extinf" | grep -oP ',[^,]+$' | sed 's/^,//')
    echo "  [$num] HTTP $code - $name"
done
