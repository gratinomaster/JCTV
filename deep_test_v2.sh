#!/bin/bash

INPUT_FILE="lista5.m3u"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0

declare -a WORKING_KEYS
declare -a FAIL_KEYS

# Resolve a possibly-relative URI against a base URL (keeping base query string)
resolve_url() {
    local base="$1"
    local uri="$2"
    local base_path base_query
    if [[ "$uri" == http* ]]; then
        if [[ "$uri" != *\?* && "$base" == *\?* ]]; then
            echo "${uri}?${base#*\?}"
        else
            echo "$uri"
        fi
        return
    fi
    base_path="${base%%\?*}"
    base_query=""
    [[ "$base" == *\?* ]] && base_query="?${base#*\?}"
    local dir
    dir="${base_path%/*}/"
    echo "${dir}${uri}${base_query}"
}

check_url() {
    local url="$1"
    local content variant media seg code

    content=$(curl -s -L --max-time 15 -A "$UA" "$url" 2>/dev/null)
    [[ -z "$content" ]] && return 1

    if echo "$content" | head -5 | grep -qE '#EXT-X-STREAM-INF'; then
        variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
        [[ -z "$variant" ]] && return 1
        variant=$(resolve_url "$url" "$variant")
        content=$(curl -s -L --max-time 15 -A "$UA" "$variant" 2>/dev/null)
        [[ -z "$content" ]] && return 1
    fi

    # Now content should be a media playlist
    if ! echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
        return 1
    fi

    seg=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
    if [[ -z "$seg" ]]; then
        return 1
    fi

    seg=$(resolve_url "$url" "$seg")
    code=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 15 -A "$UA" "$seg" 2>/dev/null)
    if [[ -z "$code" || "$code" -ge 400 ]]; then
        return 1
    fi
    return 0
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
            WORKING_KEYS+=("$CHANNEL_NUM|$EXTINF_LINE|$URL_LINE")
            echo "[$CHANNEL_NUM] OK  - $NAME"
        else
            FAIL_KEYS+=("$CHANNEL_NUM|$EXTINF_LINE|$URL_LINE")
            echo "[$CHANNEL_NUM] FAIL - $NAME"
        fi
        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

echo ""
echo "=== RESUMO ==="
echo "Funcionando: ${#WORKING_KEYS[@]}"
echo "Falhando:    ${#FAIL_KEYS[@]}"

if [[ ${#FAIL_KEYS[@]} -gt 0 ]]; then
    echo ""
    echo "=== CANAIS FALHANDO ==="
    for entry in "${FAIL_KEYS[@]}"; do
        echo "$entry"
    done
fi
