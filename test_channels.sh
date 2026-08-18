#!/bin/bash
INPUT="lista5.m3u"
OUTPUT="lista5_clean.m3u"
TIMEOUT=10

echo "#EXTM3U" > "$OUTPUT"

# Read file line by line
extinf=""
url=""
while IFS= read -r line; do
    # Skip empty lines and header
    [[ -z "$line" || "$line" == "#EXTM3U" ]] && continue
    
    if [[ "$line" == \#EXTINF* ]]; then
        extinf="$line"
    elif [[ "$line" == http* ]]; then
        url="$line"
        # Test URL
        response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" --max-time "$TIMEOUT" -L "$url" 2>/dev/null)
        http_code="${response:0:3}"
        
        if [[ "$http_code" =~ ^2[0-9]{2}$ ]]; then
            echo "$extinf" >> "$OUTPUT"
            echo "$url" >> "$OUTPUT"
            echo "OK: $http_code - $url" >> /tmp/test_results.txt
        else
            echo "FAIL: $http_code - $url" >> /tmp/test_results.txt
        fi
    fi
done < "$INPUT"

echo "Done. Results saved."
