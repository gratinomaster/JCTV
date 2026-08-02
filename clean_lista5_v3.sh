#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_clean.m3u"
LOG_FILE="/tmp/lista5_v3_validation.txt"

> "$LOG_FILE"

echo "#EXTM3U" > "$OUTPUT_FILE"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0
WORKING=0
FAILING=0

check_url() {
    local url="$1"
    local content
    content=$(curl -s -L --max-time 15 -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36" "$url" 2>/dev/null)

    if [[ -z "$content" ]]; then
        return 1
    fi

    if echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
        return 0
    fi

    if echo "$content" | grep -qE '\.m3u8|\.ts|BANDWIDTH|#EXT-X-STREAM-INF'; then
        return 0
    fi

    return 1
}

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
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        if check_url "$URL_LINE"; then
            echo "$EXTINF_LINE" >> "$OUTPUT_FILE"
            echo "$URL_LINE" >> "$OUTPUT_FILE"
            WORKING=$((WORKING + 1))
            echo "[$CHANNEL_NUM] WORKING - $NAME" | tee -a "$LOG_FILE"
        else
            FAILING=$((FAILING + 1))
            echo "[$CHANNEL_NUM] FAIL - $NAME" | tee -a "$LOG_FILE"
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
echo "Total testados:    $CHANNEL_NUM"
echo "Funcionando:       $WORKING"
echo "Nao funcionando:   $FAILING"
echo "Arquivo atualizado: $INPUT_FILE"
echo "========================================="
