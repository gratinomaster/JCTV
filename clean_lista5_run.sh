#!/bin/bash

INPUT_FILE="lista5.m3u"
TMP_FILE="/tmp/lista5_clean.m3u"
LOG_FILE="clean_lista5_run.log"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

resolve_url() {
    local uri="$1" base="$2"
    if [[ "$uri" == http* ]]; then
        if [[ "$uri" != *\?* && "$base" == *\?* ]]; then
            echo "${uri}?${base#*\?}"
        else
            echo "$uri"
        fi
        return
    fi
    local base_path="${base%%\?*}"
    local base_query=""
    [[ "$base" == *\?* ]] && base_query="?${base#*\?}"
    echo "${base_path%/*}/${uri}${base_query}"
}

check_url() {
    local url="$1"
    local content variant seg code

    content=$(curl -s -L --max-time 20 -A "$UA" "$url" 2>/dev/null)
    [[ -z "$content" ]] && return 1

    if echo "$content" | head -5 | grep -qE '#EXT-X-STREAM-INF'; then
        variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
        [[ -z "$variant" ]] && return 1
        variant=$(resolve_url "$variant" "$url")
        content=$(curl -s -L --max-time 20 -A "$UA" "$variant" 2>/dev/null)
        [[ -z "$content" ]] && return 1
    fi

    if ! echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
        return 1
    fi

    seg=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
    [[ -z "$seg" ]] && return 1
    seg=$(resolve_url "$seg" "$url")
    code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 20 -A "$UA" "$seg" 2>/dev/null)
    [[ -z "$code" || "$code" -ge 400 ]] && return 1
    return 0
}

echo "#EXTM3U" > "$TMP_FILE"
: > "$LOG_FILE"

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

        if check_url "$URL_LINE"; then
            echo "$EXTINF_LINE" >> "$TMP_FILE"
            echo "$URL_LINE" >> "$TMP_FILE"
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

mv "$TMP_FILE" "$INPUT_FILE"

echo ""
echo "========================================="
echo "Total testados:    $CHANNEL_NUM"
echo "Funcionando:       $WORKING"
echo "Nao funcionando:   $FAILING"
echo "Arquivo atualizado: $INPUT_FILE"
echo "========================================="
