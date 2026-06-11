#!/usr/bin/env python3
import time
import json
from seleniumwire import webdriver  # Importa do selenium-wire
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================
# ESTADOS DO BRASIL
# =========================
ESTADOS_BRASIL = [
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma",
    "mt", "ms", "mg", "pa", "pb", "pr", "pe", "pi", "rj", "rn",
    "rs", "ro", "rr", "sc", "sp", "se", "to"
]

# =========================
# DRIVER
# =========================
def criar_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Opções do Selenium-Wire
    seleniumwire_options = {
        'disable_encoding': True,  # Desativa a decodificação automática de respostas
        'ignore_http_methods': ['OPTIONS', 'HEAD'] # Ignora requisições desnecessárias
    }

    # Usa o webdriver do selenium-wire
    driver = webdriver.Chrome(
        service=Service( ), 
        options=options, 
        seleniumwire_options=seleniumwire_options
    )
    driver.set_page_load_timeout(60)
    return driver

# =========================
# BUSCA LINKS AO VIVO
# =========================
def buscar_links_ao_vivo(driver, url):
    links = []
    try:
        driver.get(url)
        # Espera um pouco para os elementos da página carregarem
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except Exception as e:
        print(f"⚠ Não foi possível abrir {url}: {e}")
        return links

    spans = driver.find_elements(By.CLASS_NAME, "bstn-aovivo-label")

    for span in spans:
        try:
            # Sobe na árvore DOM para encontrar o link pai
            a = span.find_element(By.XPATH, "./ancestor::a[@href]")
            href = a.get_attribute("href")

            if "/ao-vivo/" in href and href.endswith(".ghtml"):
                links.append(href)
        except:
            # Ignora spans que não estão dentro de um link
            pass

    return list(set(links)) # Retorna apenas links únicos

# =========================
# CLICA PLAY (SE EXISTIR)
# =========================
def clicar_play(driver):
    # Seletores CSS para diferentes botões de play
    seletores = [
        "button.poster__play-wrapper",
        ".play-button",
        "[aria-label='Play']",
        ".video-player__play-button",
        ".vjs-big-play-button" # Seletor comum em players de vídeo
    ]

    for seletor in seletores:
        try:
            # Espera até 10 segundos para o botão ser clicável
            wait = WebDriverWait(driver, 10)
            btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, seletor)))
            
            # Usa JavaScript para clicar, é mais robusto
            driver.execute_script("arguments[0].click();", btn)
            print("   ✓ Botão de play clicado.")
            return True
        except:
            # Continua para o próximo seletor se este falhar
            pass
    
    print("   - Nenhum botão de play encontrado ou clicável.")
    return False

# =========================
# CAPTURA M3U8 + THUMBNAIL
# =========================
def capturar_streams(driver, tempo_max_espera=30):
    m3u8_url = None
    thumbnail_url = None
    inicio = time.time()

    print("   ... Aguardando captura do stream .m3u8")
    while time.time() - inicio < tempo_max_espera:
        # Itera sobre as requisições capturadas pelo Selenium-Wire
        for request in driver.requests:
            if request.response:
                url = request.url.lower()

                # ===== M3U8 =====
                if ".m3u8" in url and not m3u8_url:
                    m3u8_url = request.url # Salva a URL original com case correto
                    print(f"   ✓ Stream M3U8 encontrado: {m3u8_url}")

                # ===== THUMBNAIL (SOMENTE GLOBO) =====
                if (
                    not thumbnail_url
                    and ("video.glbimg.com" in url)
                    and (url.endswith(".jpg") or url.endswith(".jpeg"))
                ):
                    thumbnail_url = request.url
                    print(f"   ✓ Thumbnail encontrado: {thumbnail_url}")

        # Se já encontrou o m3u8, pode sair do loop
        if m3u8_url:
            break

        time.sleep(1)

    return m3u8_url, thumbnail_url


# =========================
# MAIN
# =========================
def main():
    driver = criar_driver()
    links_ao_vivo = []
    resultados = []

    try:
        print("\n🔎 COLETANDO LINKS AO VIVO DOS PORTAIS G1\n")

        for estado in ESTADOS_BRASIL:
            url = f"https://g1.globo.com/{estado}"
            links = buscar_links_ao_vivo(driver, url )

            if links:
                print(f"  {estado.upper()}: {len(links)} link(s) encontrado(s).")
                links_ao_vivo.extend(links)
            else:
                print(f"  {estado.upper()}: Nenhum link 'AO VIVO' encontrado.")
        
        # Remove duplicados de toda a lista
        links_ao_vivo = sorted(list(set(links_ao_vivo)))

        if not links_ao_vivo:
            print("\n⚠ Nenhum link 'AO VIVO' encontrado em nenhum estado.")
            return

        print(f"\n🎥 EXTRAINDO STREAMS (.m3u8) DE {len(links_ao_vivo)} LINKS\n")

        for link in links_ao_vivo:
            print(f"➡ Abrindo: {link}")
            
            # Limpa as requisições anteriores antes de carregar uma nova página
            del driver.requests

            try:
                driver.get(link)
                # Espera o player de vídeo carregar
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div[id*='video'], div[class*='video']"))
                )
            except Exception as e:
                print(f"  ⚠ Não foi possível abrir ou encontrar player em {link}: {e}")
                continue

            clicar_play(driver)
            
            m3u8, thumbnail = capturar_streams(driver)

            if m3u8:
                titulo = driver.title.split(" | ")[0].strip() # Limpa o título
                print(f"   ✅ SUCESSO! Título: {titulo}")
                resultados.append({
                    "titulo": titulo,
                    "m3u8": m3u8,
                    "thumbnail": thumbnail,
                    "grupo": "GLOBO AO VIVO"
                })
            else:
                print("   ❌ Falha ao capturar o stream M3U8.")

    finally:
        driver.quit()

    if not resultados:
        print("\nNenhum stream foi extraído com sucesso.")
        return

    # Gera o arquivo .m3u no final
    with open("lista2.m3u", "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for item in resultados:
            extinf = f'#EXTINF:-1 group-title="{item["grupo"]}"'
            if item["thumbnail"]:
                extinf += f' tvg-logo="{item["thumbnail"]}"'
            
            extinf += f',{item["titulo"]}\n'
            f.write(extinf)
            f.write(f'{item["m3u8"]}\n')

    print(f"\n✅ Arquivo gerado com sucesso: lista_canais.m3u ({len(resultados)} canais)")


# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    main()


#!/usr/bin/env python3
import time
import json
import re
from seleniumwire import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# =========================
# DRIVER
# =========================
def criar_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--autoplay-policy=no-user-gesture-required")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    
    # Opções do Selenium-Wire
    seleniumwire_options = {
        'disable_encoding': True,
        'ignore_http_methods': ['OPTIONS', 'HEAD']
    }

    driver = webdriver.Chrome(
        service=Service(),
        options=options,
        seleniumwire_options=seleniumwire_options
    )
    driver.set_page_load_timeout(60)
    return driver


# =========================
# EXTRAIR URLs DO GOOGLE SEARCH
# =========================
def extrair_urls_google_videos(driver, url_google):
    """
    Acessa a página de busca do Google e extrai os URLs dos vídeos do Globoplay
    que aparecerem na página no momento da abertura.
    """
    urls_videos = []
    
    try:
        print(f"\n🔎 Acessando página de busca do Google: {url_google}")
        driver.get(url_google)
        
        # Espera a página carregar
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(3)  # Aguarda carregamento adicional
        
        # Procura por links que apontam para globoplay.globo.com
        # Geralmente estão em tags <a> dentro de divs de resultado
        links = driver.find_elements(By.TAG_NAME, "a")
        
        print(f"   ... Encontrados {len(links)} links na página")
        
        for link in links:
            try:
                href = link.get_attribute("href")
                if href and "globoplay.globo.com" in href and "/v/" in href:
                    # Extrai apenas a URL do vídeo (remove parâmetros extras)
                    match = re.search(r'(https?://globoplay\.globo\.com/v/\d+)', href)
                    if match:
                        video_url = match.group(1)
                        if video_url not in urls_videos:
                            urls_videos.append(video_url)
                            print(f"   ✓ Vídeo encontrado: {video_url}")
            except:
                pass
        
        if not urls_videos:
            print("   ⚠ Nenhum vídeo do Globoplay encontrado na página")
        else:
            print(f"\n✅ Total de vídeos extraídos: {len(urls_videos)}")
        
        return urls_videos
        
    except Exception as e:
        print(f"❌ Erro ao acessar página de busca: {e}")
        return []


# =========================
# CLICA PLAY (SE EXISTIR)
# =========================
def clicar_play(driver):
    """Tenta clicar no botão de play do vídeo"""
    seletores = [
        "button.poster__play-wrapper",
        ".play-button",
        "[aria-label='Play']",
        ".video-player__play-button",
        ".vjs-big-play-button",
        "button[aria-label*='play']",
        "div[class*='play']"
    ]

    for seletor in seletores:
        try:
            wait = WebDriverWait(driver, 10)
            btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, seletor)))
            driver.execute_script("arguments[0].click();", btn)
            print("   ✓ Botão de play clicado.")
            return True
        except:
            pass
    
    print("   - Nenhum botão de play encontrado ou clicável.")
    return False


# =========================
# CAPTURA M3U8 + THUMBNAIL
# =========================
def capturar_streams(driver, tempo_max_espera=30):
    """Captura a URL do stream M3U8 e thumbnail do vídeo"""
    m3u8_url = None
    thumbnail_url = None
    inicio = time.time()

    print("   ... Aguardando captura do stream .m3u8")
    while time.time() - inicio < tempo_max_espera:
        for request in driver.requests:
            if request.response:
                url = request.url.lower()

                # ===== M3U8 =====
                if ".m3u8" in url and not m3u8_url:
                    m3u8_url = request.url
                    print(f"   ✓ Stream M3U8 encontrado: {m3u8_url}")

                # ===== THUMBNAIL =====
                if (
                    not thumbnail_url
                    and ("video.glbimg.com" in url)
                    and (url.endswith(".jpg") or url.endswith(".jpeg"))
                ):
                    thumbnail_url = request.url
                    print(f"   ✓ Thumbnail encontrado: {thumbnail_url}")

        if m3u8_url:
            break

        time.sleep(1)

    return m3u8_url, thumbnail_url


# =========================
# PROCESSAR VÍDEOS
# =========================
def processar_videos(driver, urls_videos):
    """Processa cada vídeo para extrair o stream M3U8"""
    resultados = []

    print(f"\n🎥 EXTRAINDO STREAMS (.m3u8) DE {len(urls_videos)} VÍDEOS\n")

    for i, url_video in enumerate(urls_videos, 1):
        print(f"➡ [{i}/{len(urls_videos)}] Abrindo: {url_video}")
        
        # Limpa as requisições anteriores
        del driver.requests

        try:
            driver.get(url_video)
            
            # Espera o player de vídeo carregar
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div[id*='video'], div[class*='video'], div[class*='player']"))
            )
            
            time.sleep(2)
            
        except Exception as e:
            print(f"  ⚠ Não foi possível abrir {url_video}: {e}")
            continue

        clicar_play(driver)
        
        m3u8, thumbnail = capturar_streams(driver)

        if m3u8:
            try:
                titulo = driver.title.split(" | ")[0].strip()
            except:
                titulo = f"Vídeo {i}"
            
            print(f"   ✅ SUCESSO! Título: {titulo}")
            resultados.append({
                "titulo": titulo,
                "m3u8": m3u8,
                "thumbnail": thumbnail,
                "url_original": url_video,
                "grupo": "GLOBOPLAY VIDEOS"
            })
        else:
            print("   ❌ Falha ao capturar o stream M3U8.")

    return resultados


# =========================
# GERAR ARQUIVO M3U
# =========================
def gerar_arquivo_m3u(resultados, nome_arquivo="lista_videos.m3u"):
    """Gera arquivo M3U com os streams capturados"""
    if not resultados:
        print("\n⚠ Nenhum stream foi extraído com sucesso.")
        return

    with open(nome_arquivo, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n")
        for item in resultados:
            extinf = f'#EXTINF:-1 group-title="{item["grupo"]}"'
            if item["thumbnail"]:
                extinf += f' tvg-logo="{item["thumbnail"]}"'
            
            extinf += f',{item["titulo"]}\n'
            f.write(extinf)
            f.write(f'{item["m3u8"]}\n')

    print(f"\n✅ Arquivo gerado com sucesso: {nome_arquivo} ({len(resultados)} vídeos)")


# =========================
# MAIN
# =========================
def main():
    """Função principal"""
    driver = criar_driver()
    
    try:
        # URL da busca do Google (pode ser customizada)
        url_google_search = "https://www.google.com/search?q=3+fevereiro&udm=7"
        
        # Extrai URLs dos vídeos da página de busca
        urls_videos = extrair_urls_google_videos(driver, url_google_search)
        
        if not urls_videos:
            print("\n⚠ Nenhum vídeo foi encontrado na página de busca.")
            return
        
        # Processa cada vídeo para extrair o stream M3U8
        resultados = processar_videos(driver, urls_videos)
        
        # Gera arquivo M3U
        gerar_arquivo_m3u(resultados)
        
    finally:
        driver.quit()


# =========================
# EXECUÇÃO
# =========================
if __name__ == "__main__":
    main()
