#!/bin/bash

INPUT="lista5.m3u"
OUTPUT="lista5_clean.m3u"
LOG="test_results.log"

> "$LOG"
> "$OUTPUT"

echo "#EXTM3U" >> "$OUTPUT"

line_num=0
skip_next=false

while IFS= read -r line; do
    line_num=$((line_num + 1))
    
    if [ "$skip_next" = true ]; then
        skip_next=false
        continue
    fi
    
    if [[ "$line" == "#EXTINF:"* ]]; then
        extinf="$line"
        channel_name=$(echo "$line" | sed 's/.*,\(.*\)/\1/')
        read -r url
        line_num=$((line_num + 1))
        
        echo -n "Testing $channel_name... " | tee -a "$LOG"
        
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 -L "$url" 2>/dev/null)
        
        if [ "$http_code" = "200" ] || [ "$http_code" = "206" ] || [ "$http_code" = "302" ]; then
            echo "OK (HTTP $http_code)" | tee -a "$LOG"
            echo "$extinf" >> "$OUTPUT"
            echo "$url" >> "$OUTPUT"
        else
            echo "FAILED (HTTP $http_code)" | tee -a "$LOG"
        fi
    fi
done < "$INPUT"

echo ""
echo "Results saved to $OUTPUT"
echo "Log saved to $LOG"
echo "Working channels: $(grep -c "#EXTINF:" "$OUTPUT")"
echo "Removed channels: $(( ($(grep -c "#EXTINF:" "$INPUT") - $(grep -c "#EXTINF:" "$OUTPUT")) ))"