#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="/tmp/lista5_clean.m3u"
LOG_FILE="/tmp/lista5_v4_validation.txt"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

cp "$INPUT_FILE" "$INPUT_FILE.bak.$(date +%Y%m%d_%H%M%S)"

> "$LOG_FILE"
> "$OUTPUT_FILE"
echo "#EXTM3U" > "$OUTPUT_FILE"

resolve_url() {
    local url="$1"
    local ref="$2"
    if [[ "$url" == http* ]]; then
        echo "$url"
    else
        echo "$(echo "$ref" | sed 's|/[^/]*$|/|')$url"
    fi
}

check_url() {
    local url="$1"
    local content
    content=$(curl -s -L --max-time 20 -A "$UA" "$url" 2>/dev/null)
    if [[ -z "$content" ]]; then
        return 1
    fi
    if echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
        return 0
    fi
    if echo "$content" | grep -qE '\.m3u8|\.ts|#EXT-X-STREAM-INF|BANDWIDTH'; then
        return 0
    fi
    return 1
}

test_segment() {
    local url="$1"
    local content="$2"
    if ! echo "$content" | grep -q "#EXTINF"; then
        return 0
    fi
    local segment
    segment=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
    if [[ -z "$segment" ]]; then
        return 0
    fi
    segment=$(resolve_url "$segment" "$url")
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 20 -A "$UA" "$segment" 2>/dev/null)
    if [[ "$status" -ge 400 ]] || [[ -z "$status" ]]; then
        return 1
    fi
    return 0
}

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
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        OK="no"
        if check_url "$URL_LINE"; then
            content=$(curl -s -L --max-time 20 -A "$UA" "$URL_LINE" 2>/dev/null)
            if echo "$content" | grep -q "EXT-X-STREAM-INF"; then
                variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
                if [[ -n "$variant" ]]; then
                    variant=$(resolve_url "$variant" "$URL_LINE")
                    vcontent=$(curl -s -L --max-time 20 -A "$UA" "$variant" 2>/dev/null)
                    if [[ -n "$vcontent" ]] && echo "$vcontent" | grep -qE '#EXT-X-'; then
                        if test_segment "$variant" "$vcontent"; then
                            OK="yes"
                        fi
                    fi
                fi
            else
                if test_segment "$URL_LINE" "$content"; then
                    OK="yes"
                fi
            fi
        fi

        if [[ "$OK" == "yes" ]]; then
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
