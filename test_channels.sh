#!/bin/bash

INPUT_FILE="lista5.m3u"
OUTPUT_FILE="lista5_cleaned.m3u"
LOG_FILE="channel_test.log"

> "$LOG_FILE"

echo "Testando canais da lista M3U..."

while IFS= read -r line; do
    if [[ "$line" == "#EXTINF"* ]]; then
        channel_info="$line"
        continue
    fi
    
    if [[ "$line" =~ ^https?:// ]]; then
        url="$line"
        
        response=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 --max-time 15 "$url" 2>/dev/null)
        
        if [[ "$response" -ge 200 && "$response" -lt 400 ]]; then
            echo "OK|$channel_info|$url" >> "$LOG_FILE"
        else
            echo "FAIL|$channel_info|$url|$response" >> "$LOG_FILE"
        fi
    fi
done < "$INPUT_FILE"

echo "#EXTM3U" > "$OUTPUT_FILE"

grep "^OK|" "$LOG_FILE" | while IFS='|' read -r status info url; do
    echo "$info" >> "$OUTPUT_FILE"
    echo "$url" >> "$OUTPUT_FILE"
done

ok_count=$(grep -c "^OK|" "$LOG_FILE")
fail_count=$(grep -c "^FAIL|" "$LOG_FILE")

echo "Teste concluído!"
echo "Canais funcionando: $ok_count"
echo "Canais com problema: $fail_count"

cp "$OUTPUT_FILE" "$INPUT_FILE"

echo "Arquivo atualizado: $INPUT_FILE"