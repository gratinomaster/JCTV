#!/bin/bash
INPUT_FILE="lista5.m3u"
TMP_FILE="lista5_new.m3u"
LOG_FILE="test_lista5.log"

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36"

resolve_url() {
    local sub="$1" base="$2"
    if [[ "$sub" == http* ]]; then
        echo "$sub"
    else
        local dir
        dir=$(echo "$base" | sed 's|/[^/]*$|/|')
        echo "${dir}${sub}"
    fi
}

append_query() {
    local url="$1" q="$2"
    if [[ -z "$q" ]]; then
        echo "$url"
    elif [[ "$url" == *"?"* ]]; then
        echo "$url"
    else
        echo "${url}?${q}"
    fi
}

extract_query() {
    echo "$1" | grep -o '?.*$' | sed 's/^?//'
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
        QUERY=$(extract_query "$URL_LINE")

        HTTP_CODE=$(curl -s -o /tmp/ch_content.$$ -w "%{http_code}" --connect-timeout 10 --max-time 15 -L -H "User-Agent: $UA" "$URL_LINE" 2>/dev/null)
        CONTENT=$(cat /tmp/ch_content.$$ 2>/dev/null)
        PLAYLIST_URL="$URL_LINE"

        OK="false"
        REASON=""

        if [[ "$HTTP_CODE" == "200" || "$HTTP_CODE" == "206" ]]; then
            if echo "$CONTENT" | head -5 | grep -qE '#EXTM3U|#EXT-X-'; then
                OK="true"
            else
                REASON="content-not-hls (HTTP $HTTP_CODE)"
            fi
        else
            REASON="HTTP $HTTP_CODE"
        fi

        if [[ "$OK" == "true" ]]; then
            if echo "$CONTENT" | grep -q "EXT-X-STREAM-INF"; then
                VARIANT=$(echo "$CONTENT" | grep -v '^#' | grep -v '^$' | head -1)
                if [[ -n "$VARIANT" ]]; then
                    VARIANT=$(resolve_url "$VARIANT" "$PLAYLIST_URL")
                    VARIANT=$(append_query "$VARIANT" "$QUERY")
                    VHTTP=$(curl -s -o /tmp/ch_variant.$$ -w "%{http_code}" --connect-timeout 10 --max-time 15 -L -H "User-Agent: $UA" "$VARIANT" 2>/dev/null)
                    VCONTENT=$(cat /tmp/ch_variant.$$ 2>/dev/null)
                    if [[ "$VHTTP" != "200" && "$VHTTP" != "206" ]] || ! echo "$VCONTENT" | grep -qE '#EXT-X-'; then
                        OK="false"
                        REASON="bad-variant HTTP $VHTTP"
                    else
                        CONTENT="$VCONTENT"
                        PLAYLIST_URL="$VARIANT"
                    fi
                fi
            fi
        fi

        if [[ "$OK" == "true" ]]; then
            SEGMENT=$(echo "$CONTENT" | grep -v '^#' | grep -v '^$' | head -1)
            if [[ -n "$SEGMENT" ]]; then
                SEGMENT=$(resolve_url "$SEGMENT" "$PLAYLIST_URL")
                SEGMENT=$(append_query "$SEGMENT" "$QUERY")
                SHTTP=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 -L -H "User-Agent: $UA" "$SEGMENT" 2>/dev/null)
                if [[ "$SHTTP" != "200" && "$SHTTP" != "206" ]]; then
                    OK="false"
                    REASON="bad-segment HTTP $SHTTP"
                fi
            fi
        fi

        if [[ "$OK" == "true" ]]; then
            echo "$EXTINF_LINE" >> "$TMP_FILE"
            echo "$URL_LINE" >> "$TMP_FILE"
            WORKING=$((WORKING + 1))
            echo "[$CHANNEL_NUM] WORKING - $NAME" | tee -a "$LOG_FILE"
        else
            FAILING=$((FAILING + 1))
            echo "[$CHANNEL_NUM] FAIL ($REASON) - $NAME" | tee -a "$LOG_FILE"
        fi

        rm -f /tmp/ch_content.$$ /tmp/ch_variant.$$
        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

mv "$TMP_FILE" "$INPUT_FILE"

echo ""
echo "========================================="
echo "LIMPEZA CONCLUIDA"
echo "========================================="
echo "Total testados: $CHANNEL_NUM"
echo "Funcionando:    $WORKING"
echo "Nao funcionando: $FAILING"
echo "========================================="
