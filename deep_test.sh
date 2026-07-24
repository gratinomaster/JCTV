#!/bin/bash

# Ler o arquivo m3u e testar cada par EXTINF+URL
line_num=0
extinf_line=""
url_line=""
working_entries=()
broken_entries=()

while IFS= read -r line; do
    line_num=$((line_num + 1))
    
    if [[ "$line" == "#EXTM3U" ]]; then
        continue
    fi
    
    if [[ "$line" == "#EXTINF:"* ]]; then
        extinf_line="$line"
        continue
    fi
    
    # Linha de URL
    if [[ -n "$line" && -n "$extinf_line" ]]; then
        url="$line"
        
        # 1. Verificar se o m3u8 é válido (contém #EXT ou #EXT-X-)
        content=$(curl -s -L --max-time 10 "$url" 2>/dev/null)
        
        if [[ -z "$content" ]]; then
            echo "BROKEN (vazio): $extinf_line"
            echo "  URL: $url"
            broken_entries+=("${extinf_line}|${url}")
            extinf_line=""
            continue
        fi
        
        # Verificar se é HLS válido
        is_hls=false
        if echo "$content" | head -5 | grep -qE '^#EXTM3U|^#EXT-X-'; then
            is_hls=true
        fi
        
        if [[ "$is_hls" == "false" ]]; then
            # Pode ser uma lista de variantes m3u8
            if echo "$content" | grep -qE '\.m3u8|\.ts|BANDWIDTH'; then
                is_hls=true
            fi
        fi
        
        if [[ "$is_hls" == "false" ]]; then
            echo "BROKEN (não HLS): $extinf_line"
            echo "  URL: $url"
            echo "  Conteúdo: $(echo "$content" | head -1)"
            broken_entries+=("${extinf_line}|${url}")
            extinf_line=""
            continue
        fi
        
        # 2. Se for master m3u8, tentar pegar uma variante e testar
        if echo "$content" | grep -q "EXT-X-STREAM-INF"; then
            # Pegar a primeira variante
            variant_url=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
            
            if [[ -n "$variant_url" ]]; then
                # Resolver URL relativa
                if [[ "$variant_url" != http* ]]; then
                    base_url=$(echo "$url" | sed 's|/[^/]*$|/|')
                    variant_url="${base_url}${variant_url}"
                fi
                
                variant_content=$(curl -s -L --max-time 10 "$variant_url" 2>/dev/null)
                if [[ -z "$variant_content" ]] || ! echo "$variant_content" | grep -qE '#EXT-X-'; then
                    echo "BROKEN (variante inválida): $extinf_line"
                    echo "  URL: $url"
                    broken_entries+=("${extinf_line}|${url}")
                    extinf_line=""
                    continue
                fi
            fi
        fi
        
        # 3. Verificar se há segmentos .ts no m3u8 de mídia
        if echo "$content" | grep -q "#EXTINF"; then
            # Pegar um segmento .ts e testar
            segment=$(echo "$content" | grep -v '^#' | grep -v '^$' | head -1)
            if [[ -n "$segment" ]]; then
                if [[ "$segment" != http* ]]; then
                    base_url=$(echo "$url" | sed 's|/[^/]*$|/|')
                    segment="${base_url}${segment}"
                fi
                seg_status=$(curl -s -o /dev/null -w "%{http_code}" -L --max-time 10 "$segment" 2>/dev/null)
                if [[ "$seg_status" -ge 400 ]]; then
                    echo "BROKEN (segmento HTTP $seg_status): $extinf_line"
                    echo "  URL: $url"
                    broken_entries+=("${extinf_line}|${url}")
                    extinf_line=""
                    continue
                fi
            fi
        fi
        
        echo "OK: $extinf_line"
        working_entries+=("${extinf_line}|${url}")
        extinf_line=""
    fi
done < lista5.m3u

echo ""
echo "=== RESUMO ==="
echo "Funcionando: ${#working_entries[@]}"
echo "Com problema: ${#broken_entries[@]}"
