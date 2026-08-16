#!/bin/bash
INPUT_FILE="lista5.m3u"
TMP_FILE="lista5_clean_new.m3u"
LOG_FILE="clean_lista5_now.log"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
TIMEOUT=15

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

check_channel() {
    local url="$1" tmpseg="/tmp/seg_check.bin"
    local content variant seg segurl code magic size ctype

    for attempt in 1 2; do
        content=$(curl -s -L --connect-timeout 10 --max-time "$TIMEOUT" -A "$UA" "$url" 2>/dev/null)
        [[ -z "$content" ]] && { sleep 2; continue; }

        if echo "$content" | head -10 | grep -qE '#EXT-X-STREAM-INF'; then
            variant=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
            [[ -z "$variant" ]] && { sleep 2; continue; }
            variant=$(resolve_url "$variant" "$url")
            content=$(curl -s -L --connect-timeout 10 --max-time "$TIMEOUT" -A "$UA" "$variant" 2>/dev/null)
            [[ -z "$content" ]] && { sleep 2; continue; }
        fi

        if ! echo "$content" | head -20 | grep -qE '^#EXTM3U|^#EXT-X-'; then
            { sleep 2; continue; }
        fi

        seg=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1 | tr -d '\r')
        if [[ -z "$seg" ]]; then
            return 0
        fi
        segurl=$(resolve_url "$seg" "$url")

        rm -f "$tmpseg"
        code=$(curl -s -o "$tmpseg" -w "%{http_code}" -L --connect-timeout 10 --max-time "$TIMEOUT" -A "$UA" -H 'Accept: */*' "$segurl" 2>/dev/null)
        if [[ -z "$code" || "$code" -ge 400 ]]; then
            { sleep 2; continue; }
        fi
        size=$(stat -c%s "$tmpseg" 2>/dev/null || echo 0)
        if [[ -z "$size" || "$size" -lt 100 ]]; then
            { sleep 2; continue; }
        fi
        magic=$(od -An -tx1 -N4 "$tmpseg" 2>/dev/null | tr -d ' \n')
        if [[ "$magic" == "47404d40" || "$magic" == "66747970" ]]; then
            return 0
        fi
        ctype=$(file -b --mime-type "$tmpseg" 2>/dev/null)
        case "$ctype" in
            video/*|audio/*|application/mp2t|application/octet-stream) return 0 ;;
        esac
        { sleep 2; continue; }
    done
    return 1
}

echo "#EXTM3U" > "$TMP_FILE"
: > "$LOG_FILE"

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

        if check_channel "$line"; then
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
echo "Total testados:    $CHANNEL_NUM"
echo "Funcionando:       $WORKING"
echo "Nao funcionando:   $FAILING"
echo "========================================="

if [[ "$FAILING" -eq 0 ]]; then
    echo "Nenhum canal removido."
    rm -f "$TMP_FILE"
else
    mv "$TMP_FILE" "$INPUT_FILE"
    echo "Arquivo $INPUT_FILE atualizado."
fi
