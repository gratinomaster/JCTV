#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_clean.m3u"
TIMEOUT=10
WORKING=0
FAILED=0
TOTAL=0

echo "#EXTM3U" > "$OUTPUT_FILE"

while IFS= read -r line; do
    if [[ "$line" == \#EXTINF:* ]]; then
        EXTINF="$line"
        TOTAL=$((TOTAL + 1))
        
        read -r url
        
        # Extract channel name from EXTINF line
        channel_name=$(echo "$EXTINF" | sed 's/.*,\(.*\)/\1/' | xargs)
        echo -n "Testing: $channel_name... "
        
        # Test the URL
        response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$url" 2>/dev/null)
        
        if [[ "$response" =~ ^2 ]] || [[ "$response" =~ ^3 ]]; then
            echo "OK ($response)"
            echo "$EXTINF" >> "$OUTPUT_FILE"
            echo "$url" >> "$OUTPUT_FILE"
            WORKING=$((WORKING + 1))
        else
            echo "FAILED ($response)"
            FAILED=$((FAILED + 1))
        fi
    fi
done < "$INPUT_FILE"

echo ""
echo "Results:"
echo "Total channels tested: $TOTAL"
echo "Working: $WORKING"
echo "Failed: $FAILED"

mv "$OUTPUT_FILE" "$INPUT_FILE"