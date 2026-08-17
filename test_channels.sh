#!/bin/bash

# Script to test M3U channels and keep only working ones
INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_working.m3u"
TIMEOUT=10

# Create temporary files
TEMP_FILE=$(mktemp)
WORKING_FILE=$(mktemp)

# Parse M3U file and extract entries
while IFS= read -r line; do
    if [[ "$line" == "#EXTINF:"* ]]; then
        # This is an EXTINF line
        EXTINF_LINE="$line"
    elif [[ "$line" != "#EXTM3U" && "$line" != "" && "$line" != "#EXTM3U"* ]]; then
        # This is a URL line
        URL="$line"
        if [[ -n "$EXTINF_LINE" && -n "$URL" ]]; then
            # Test the URL
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT -L "$URL" 2>/dev/null)
            
            if [[ "$HTTP_CODE" == "200" ]]; then
                echo "$EXTINF_LINE" >> "$WORKING_FILE"
                echo "$URL" >> "$WORKING_FILE"
            fi
            EXTINF_LINE=""
        fi
    fi
done < "$INPUT_FILE"

# Add header and write to output
echo "#EXTM3U" > "$OUTPUT_FILE"
cat "$WORKING_FILE" >> "$OUTPUT_FILE"

# Count results
TOTAL=$(grep -c "^#EXTINF:" "$INPUT_FILE")
WORKING=$(grep -c "^#EXTINF:" "$OUTPUT_FILE")
echo "Total channels: $TOTAL"
echo "Working channels: $WORKING"
echo "Removed channels: $((TOTAL - WORKING))"

# Cleanup
rm "$TEMP_FILE" "$WORKING_FILE"
