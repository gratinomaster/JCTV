#!/bin/bash

INPUT="lista5.m3u"
OUTPUT="lista5.m3u"
TEMP_FILE=$(mktemp)
> "$TEMP_FILE"

echo "#EXTM3U" > "$TEMP_FILE"

LINE_NUM=0
while IFS= read -r line; do
    LINE_NUM=$((LINE_NUM + 1))
    
    # Skip empty lines
    [[ -z "$line" ]] && continue
    
    # If this is an EXTINF line
    if [[ "$line" == "#EXTINF:"* ]]; then
        EXTINF_LINE="$line"
        
        # Read the next line (URL)
        if IFS= read -r url_line; then
            LINE_NUM=$((LINE_NUM + 1))
            
            # Skip if URL line is empty or another EXTINF
            if [[ -z "$url_line" || "$url_line" == "#EXTINF:"* || "$url_line" == "#EXTM3U" ]]; then
                continue
            fi
            
            # Test the URL
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 --max-time 10 "$url_line" 2>/dev/null)
            
            if [[ "$HTTP_CODE" == "200" ]]; then
                echo "$EXTINF_LINE" >> "$TEMP_FILE"
                echo "$url_line" >> "$TEMP_FILE"
                echo "OK ($HTTP_CODE): $(echo "$EXTINF_LINE" | grep -oP ',[^,]+$')"
            else
                echo "FAIL ($HTTP_CODE): $(echo "$EXTINF_LINE" | grep -oP ',[^,]+$')"
            fi
        fi
    fi
done < "$INPUT"

# Count results
TOTAL=$(grep -c "^#EXTINF:" "$INPUT" 2>/dev/null || echo 0)
WORKING=$(grep -c "^#EXTINF:" "$TEMP_FILE" 2>/dev/null || echo 0)
REMOVED=$((TOTAL - WORKING))

echo ""
echo "========================================="
echo "Total channels: $TOTAL"
echo "Working channels: $WORKING"
echo "Removed channels: $REMOVED"
echo "========================================="

# Overwrite original
cp "$TEMP_FILE" "$OUTPUT"
rm "$TEMP_FILE"

echo "File updated: $OUTPUT"