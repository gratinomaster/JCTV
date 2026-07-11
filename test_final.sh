#!/bin/bash

INPUT_FILE="lista5.m3u"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0
WORKING=0
FAILING=0

echo "========================================="
echo "VALIDACAO FINAL - TODOS OS CANAIS"
echo "========================================="

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
        HAS_TARGETDURATION=$(echo "$RESPONSE" | grep -c "#EXT-X-TARGETDURATION")
        HAS_VERSION=$(echo "$RESPONSE" | grep -c "#EXT-X-VERSION")
        
        # Check for actual error messages (whole words, not substrings of numbers)
        HAS_ACTUAL_ERROR=$(echo "$RESPONSE" | grep -ciw "error\|expired\|unauthorized\|forbidden\|denied")
        HAS_NOT_FOUND=$(echo "$RESPONSE" | grep -ci "not.found\|404 not\|403 forbidden")
        
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        if [[ "$HTTP_CODE" == "200" && "$HAS_HLS" -gt 0 && "$HAS_TARGETDURATION" -gt 0 && "$HAS_ACTUAL_ERROR" == "0" && "$HAS_NOT_FOUND" == "0" ]]; then
            STATUS="OK"
            WORKING=$((WORKING + 1))
        else
            STATUS="FAIL"
            FAILING=$((FAILING + 1))
            echo "  [$CHANNEL_NUM] FAIL - HTTP=$HTTP_CODE HLS=$HAS_HLS TD=$HAS_TARGETDURATION VER=$HAS_VERSION ERR=$HAS_ACTUAL_ERROR NF=$HAS_NOT_FOUND - $NAME"
        fi

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

echo "========================================="
echo "Total: $CHANNEL_NUM | OK: $WORKING | FAIL: $FAILING"
echo "========================================="
