#!/bin/bash

INPUT="lista5.m3u"
OUTPUT="lista5_clean.m3u"
TIMEOUT=10
declare -A SEEN_URLS

# First pass: collect unique working channels
> /tmp/m3u_lines.txt
URL=""
EXTINF=""

while IFS= read -r line; do
    if [[ "$line" == "#EXTM3U" ]]; then
        continue
    fi
    if [[ "$line" == "#EXTINF:"* ]]; then
        # Check if previous entry needs to be flushed
        if [[ -n "$EXTINF" && -n "$URL" ]]; then
            # Skip - will process after
            :
        fi
        EXTINF="$line"
    elif [[ -n "$line" && -n "$EXTINF" ]]; then
        URL="$line"
        
        # Skip duplicates
        if [[ -n "${SEEN_URLS[$URL]}" ]]; then
            EXTINF=""
            URL=""
            continue
        fi
        SEEN_URLS["$URL"]=1
        
        # Test URL with curl
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout $TIMEOUT --max-time $TIMEOUT -L -r 0-1024 "$URL" 2>/dev/null)
        
        if [[ "$HTTP_CODE" =~ ^(200|206)$ ]]; then
            echo "$EXTINF" >> /tmp/m3u_lines.txt
            echo "$URL" >> /tmp/m3u_lines.txt
        fi
        
        EXTINF=""
        URL=""
    fi
done < "$INPUT"

# Write output
echo "#EXTM3U" > "$OUTPUT"
cat /tmp/m3u_lines.txt >> "$OUTPUT"

TOTAL_ORIG=$(grep -c "^#EXTINF:" "$INPUT" 2>/dev/null)
TOTAL_CLEAN=$(grep -c "^#EXTINF:" "$OUTPUT" 2>/dev/null)
echo "Entradas originais: $TOTAL_ORIG"
echo "Entradas limpas (funcionando + únicas): $TOTAL_CLEAN"
echo "Entradas removidas: $((TOTAL_ORIG - TOTAL_CLEAN))"
