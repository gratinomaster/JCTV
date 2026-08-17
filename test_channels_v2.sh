#!/bin/bash

# Script to test M3U channels and keep only unique working ones
INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_working.m3u"
TIMEOUT=15

# Create temporary files
WORKING_FILE=$(mktemp)
UNIQUE_FILE=$(mktemp)

# Parse M3U file and extract entries
while IFS= read -r line; do
    if [[ "$line" == "#EXTINF:"* ]]; then
        # This is an EXTINF line
        EXTINF_LINE="$line"
    elif [[ "$line" != "#EXTM3U" && "$line" != "" && "$line" != "#EXTM3U"* ]]; then
        # This is a URL line
        URL="$line"
        if [[ -n "$EXTINF_LINE" && -n "$URL" ]]; then
            # Test the URL with more detailed check
            HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT -L "$URL" 2>/dev/null)
            
            if [[ "$HTTP_CODE" == "200" ]]; then
                echo "$EXTINF_LINE" >> "$WORKING_FILE"
                echo "$URL" >> "$WORKING_FILE"
            fi
            EXTINF_LINE=""
        fi
    fi
done < "$INPUT_FILE"

# Remove duplicates - keep first occurrence of each URL
awk '
    /^#EXTINF:/ { 
        if ($0 != prev_extinf || prev_url == "") {
            print
        }
    }
    !/^#/ && !/^$/ {
        if ($0 != prev_url) {
            print
            prev_url = $0
        }
        prev_extinf = $0
    }
    /^#EXTINF:/ { prev_extinf = $0 }
' "$WORKING_FILE" > "$UNIQUE_FILE"

# Add header and write to output
echo "#EXTM3U" > "$OUTPUT_FILE"
cat "$UNIQUE_FILE" >> "$OUTPUT_FILE"

# Count results
TOTAL=$(grep -c "^#EXTINF:" "$INPUT_FILE")
WORKING=$(grep -c "^#EXTINF:" "$WORKING_FILE")
UNIQUE=$(grep -c "^#EXTINF:" "$OUTPUT_FILE")
echo "Total channels: $TOTAL"
echo "Working channels: $WORKING"
echo "Unique working channels: $UNIQUE"
echo "Removed duplicates: $((WORKING - UNIQUE))"

# Cleanup
rm "$WORKING_FILE" "$UNIQUE_FILE"
