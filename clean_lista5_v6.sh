#!/bin/bash
INPUT_FILE="lista5.m3u"
TMP_FILE="/tmp/lista5_v6_out.m3u"
LOG_FILE="/tmp/lista5_v6.log"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
ATTEMPTS=3

: > "$LOG_FILE"

extract_query() { echo "$1" | grep -o '?.*$' | sed 's/^?//'; }

append_query() {
    local url="$1" q="$2"
    if [[ -z "$q" ]]; then echo "$url"
    elif [[ "$url" == *"?"* ]]; then echo "$url"
    else echo "${url}?${q}"; fi
}

resolve_url() {
    local base="$1" uri="$2" base_path base_query dir
    [[ "$uri" == http* ]] && { echo "$uri"; return; }
    base_path="${base%%\?*}"
    base_query=""
    [[ "$base" == *\?* ]] && base_query="?${base#*\?}"
    dir="${base_path%/*}/"
    echo "${dir}${uri}${base_query}"
}

check_channel() {
    local url="$1" query content variant seg segurl code
    query=$(extract_query "$url")
    content=$(curl -s -L --connect-timeout 10 --max-time 20 -A "$UA" "$url" 2>/dev/null)
    [[ -z "$content" ]] && return 1
    if ! echo "$content" | head -5 | grep -qE '^#EXTM3U|^#EXT-X-'; then return 1; fi
    if echo "$content" | head -5 | grep -qE '^#EXT-X-STREAM-INF'; then
        variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
        [[ -z "$variant" ]] && return 1
        variant=$(resolve_url "$url" "$variant")
        variant=$(append_query "$variant" "$query")
        content=$(curl -s -L --connect-timeout 10 --max-time 20 -A "$UA" "$variant" 2>/dev/null)
        [[ -z "$content" ]] && return 1
        if ! echo "$content" | head -5 | grep -qE '^#EXTM3U|^#EXT-X-'; then return 1; fi
    fi
    seg=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
    [[ -z "$seg" ]] && return 1
    segurl=$(resolve_url "$url" "$seg")
    segurl=$(append_query "$segurl" "$query")
    code=$(curl -s -o /dev/null -w "%{http_code}" -L --connect-timeout 10 --max-time 20 -A "$UA" "$segurl" 2>/dev/null)
    [[ -z "$code" || "$code" -ge 400 ]] && return 1
    return 0
}

echo "#EXTM3U" > "$TMP_FILE"
EXTINF_LINE=""
CHANNEL_NUM=0
WORKING=0
FAILING=0

while IFS= read -r line; do
    [[ "$line" == "#EXTM3U" ]] && continue
    if [[ "$line" == "#EXTINF"* ]]; then
        EXTINF_LINE="$line"
        continue
    fi
    if [[ -n "$EXTINF_LINE" && -n "$line" && "$line" != "#"* ]]; then
        CHANNEL_NUM=$((CHANNEL_NUM + 1))
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')
        OK=0
        for attempt in $(seq 1 "$ATTEMPTS"); do
            if check_channel "$line"; then
                OK=1
                break
            fi
            sleep 1
        done
        if [[ "$OK" == "1" ]]; then
            echo "$EXTINF_LINE" >> "$TMP_FILE"
            echo "$line" >> "$TMP_FILE"
            WORKING=$((WORKING + 1))
            echo "[$CHANNEL_NUM] OK   - $NAME" | tee -a "$LOG_FILE"
        else
            FAILING=$((FAILING + 1))
            echo "[$CHANNEL_NUM] FAIL - $NAME" | tee -a "$LOG_FILE"
        fi
        EXTINF_LINE=""
    fi
done < "$INPUT_FILE"

echo ""
echo "========================================="
echo "Total testados:   $CHANNEL_NUM"
echo "Funcionando:      $WORKING"
echo "Nao funcionando:  $FAILING"
echo "========================================="
