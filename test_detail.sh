#!/bin/bash

INPUT_FILE="lista5.m3u"
RESULTS_FILE="/tmp/channel_detail.txt"

> "$RESULTS_FILE"

EXTINF_LINE=""
URL_LINE=""
CHANNEL_NUM=0

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
        ERROR_LINES=$(echo "$RESPONSE" | grep -i "error\|expired\|unauthorized\|forbidden\|not found\|403\|404" | head -3)
        NAME=$(echo "$EXTINF_LINE" | grep -oP ',[^,]+$' | sed 's/^,//')

        if [[ "$HTTP_CODE" == "200" && ("$HAS_HLS" -gt 0) ]]; then
            if [[ -n "$ERROR_LINES" ]]; then
                STATUS="HLS_WITH_ERROR"
            else
                STATUS="WORKING"
            fi
        elif [[ "$HTTP_CODE" == "200" && "$HAS_HLS" == "0" ]]; then
            STATUS="NO_HLS"
        else
            STATUS="FAIL_HTTP"
        fi

        echo "=== Channel $CHANNEL_NUM ===" >> "$RESULTS_FILE"
        echo "Status: $STATUS" >> "$RESULTS_FILE"
        echo "HTTP: $HTTP_CODE" >> "$RESULTS_FILE"
        echo "HLS tags: $HAS_HLS" >> "$RESULTS_FILE"
        echo "Name: $NAME" >> "$RESULTS_FILE"
        if [[ -n "$ERROR_LINES" ]]; then
            echo "Error content:" >> "$RESULTS_FILE"
            echo "$ERROR_LINES" >> "$RESULTS_FILE"
        fi
        echo "" >> "$RESULTS_FILE"

        EXTINF_LINE=""
        URL_LINE=""
    fi
done < "$INPUT_FILE"

grep -A10 "HLS_WITH_ERROR\|NO_HLS\|FAIL_HTTP" "$RESULTS_FILE"
