#!/bin/bash
INPUT_FILE="lista5.m3u"
LOG_FILE="/tmp/lista5_deep.log"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"

: > "$LOG_FILE"

resolve_url() {
    local uri="$1" base="$2"
    uri="${uri%$'\r'}"
    base="${base%$'\r'}"
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

deep_check() {
    local url="$1"
    local content variant seg segfile ftype
    segfile=$(mktemp /tmp/seg.XXXXXX)

    content=$(curl -s -L --connect-timeout 10 --max-time 20 -A "$UA" "$url" 2>/dev/null)
    [[ -z "$content" ]] && { rm -f "$segfile"; return 1; }

    if echo "$content" | head -5 | grep -qE '#EXT-X-STREAM-INF'; then
        variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
        [[ -z "$variant" ]] && { rm -f "$segfile"; return 1; }
        variant=$(resolve_url "$variant" "$url")
        content=$(curl -s -L --connect-timeout 10 --max-time 20 -A "$UA" "$variant" 2>/dev/null)
        [[ -z "$content" ]] && { rm -f "$segfile"; return 1; }
    fi

    if ! echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
        rm -f "$segfile"; return 1
    fi

    seg=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
    [[ -z "$seg" ]] && { rm -f "$segfile"; return 1; }
    seg=$(resolve_url "$seg" "$url")

    curl -s -L --connect-timeout 10 --max-time 25 -A "$UA" -o "$segfile" "$seg" 2>/dev/null
    if [[ ! -f "$segfile" ]]; then
        rm -f "$segfile"; return 1
    fi
    local size
    size=$(stat -c %s "$segfile" 2>/dev/null || echo 0)
    if [[ "$size" -lt 200 ]]; then
        rm -f "$segfile"; return 1
    fi
    ftype=$(head -c 16 "$segfile" | tr -d '\0')
    if echo "$ftype" | grep -qiE 'html|<html|error|doctype|<!doctype|json'; then
        rm -f "$segfile"; return 1
    fi
    rm -f "$segfile"
    return 0
}

CHANNEL_NUM=0
WORKING=0
FAILING=0
EXTINF_LINE=""
while IFS= read -r line; do
    if [[ "$line" == "#EXTINF"* ]]; then
        EXTINF_LINE="$line"
        continue
    fi
    if [[ -n "$EXTINF_LINE" && -n "$line" && "$line" != "#"* && "$line" != "#EXTM3U" ]]; then
        CHANNEL_NUM=$((CHANNEL_NUM + 1))
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//' | cut -c1-60)
        if deep_check "$line"; then
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
