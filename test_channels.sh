#!/bin/bash

# Extrair URLs únicas do arquivo m3u
grep -v '^#' lista5.m3u | grep -v '^$' | sort -u > /tmp/unique_urls.txt

echo "=== Testando $(wc -l < /tmp/unique_urls.txt) URLs únicas ==="

# Testar cada URL
while IFS= read -r url; do
    if [ -n "$url" ]; then
        # Testar com curl, timeout de 10 segundos, seguir redirecionamentos
        status=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 10 "$url" 2>/dev/null)
        echo "HTTP $status: $url"
    fi
done < /tmp/unique_urls.txt
