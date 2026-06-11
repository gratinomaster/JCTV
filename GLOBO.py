from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import concurrent.futures
import time

# Configurações do Chrome
options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1280,720")
options.add_argument("--disable-infobars")

# URLs dos vídeos Globoplay
globoplay_urls = [
    "https://rdcanais.com/casadopatrao1",
    "https://ge.globo.com/motor/formula-1/video/formula-1-no-sportv-2026-12749215.ghtml",
    "https://globoplay.globo.com/v/4613774/",
    "https://globoplay.globo.com/ao-vivo/7689934/",
    "https://globoplay.globo.com/ao-vivo/7690141/",
    "https://globoplay.globo.com/ao-vivo/7813173/",
    "https://g1.globo.com/sp/campinas-regiao/ao-vivo/eptv-1-campinas-ao-vivo.ghtml",
    "https://globoplay.globo.com/ao-vivo/14164032",
    "https://globoplay.globo.com/ao-vivo/2134039/",
    "https://globoplay.globo.com/v/12749215/",
    "https://g1.globo.com/rr/roraima/video/ao-vivo-assista-o-jornal-de-roraima-1a-edicao-2923545-1739458038240.ghtml",
    "https://g1.globo.com/sp/ribeirao-preto-franca/ao-vivo/bom-dia-cidade-ribeirao-preto.ghtml",
    "https://g1.globo.com/sp/ribeirao-preto-franca/ao-vivo/eptv1.ghtml",
    "https://g1.globo.com/sp/ribeirao-preto-franca/ao-vivo/eptv-2-ribeirao-e-franca-ao-vivo.ghtml",
    "https://g1.globo.com/pe/petrolina-regiao/ao-vivo/ao-vivo-assista-ao-gr2.ghtml",
    "https://g1.globo.com/ap/ao-vivo/assista-ao-bdap-desta-sexta-feira-7.ghtml",
    "https://globoplay.globo.com/v/1328766/",
    "https://globoplay.globo.com/v/1467373/",
    "https://globoplay.globo.com/v/4064559/",
    "https://globoplay.globo.com/v/5472979/",
    "https://globoplay.globo.com/v/2135579/",
    "https://globoplay.globo.com/v/6120663/",
    "https://globoplay.globo.com/v/2145544/",
    "https://globoplay.globo.com/ao-vivo/10865071/",
    "https://globoplay.globo.com/v/4039160/",
    "https://globoplay.globo.com/v/6329086/",
    "https://globoplay.globo.com/v/11999480/",
    "https://g1.globo.com/al/alagoas/ao-vivo/assista-aos-telejornais-da-tv-gazeta-de-alagoas.ghtml",
    "https://globoplay.globo.com/ao-vivo/3667427/",
    "https://globoplay.globo.com/v/4218681/",
    "https://globoplay.globo.com/v/12945385/",
    "https://globoplay.globo.com/v/3065772/",
    "https://globoplay.globo.com/v/2923579/",
    "https://g1.globo.com/am/amazonas/ao-vivo/assista-aos-telejornais-da-rede-amazonica.ghtml",
    "https://globoplay.globo.com/v/2923546/",
    "https://globoplay.globo.com/v/2168377/",
    "https://globoplay.globo.com/v/992055/",
    "https://globoplay.globo.com/v/602497/",
    "https://globoplay.globo.com/v/8713568/",
    "https://globoplay.globo.com/v/10747444/",
    "https://globoplay.globo.com/v/10740500/",
]


def extract_globoplay_data(url):
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)

        wait = WebDriverWait(driver, 20)

        # tenta clicar no botão play se existir
        try:
            play_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.poster__play-wrapper"))
            )
            play_button.click()
        except:
            pass

        # aguarda o player carregar
        time.sleep(10)

        title = driver.title

        # captura requisições da página
        log_entries = driver.execute_script(
            "return window.performance.getEntriesByType('resource');"
        )

        m3u8_url = None
        thumbnail_url = None

        for entry in log_entries:
            name = entry.get("name", "")

            if ".m3u8" in name and not m3u8_url:
                m3u8_url = name

            if ".jpg" in name and not thumbnail_url:
                thumbnail_url = name

        return title, m3u8_url, thumbnail_url

    except Exception as e:
        print(f"Erro ao processar {url}: {e}")
        return None, None, None

    finally:
        if driver:
            driver.quit()


def generate_m3u():
    with open("lista1.m3u", "w", encoding="utf-8") as output_file:
        output_file.write("#EXTM3U\n")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(extract_globoplay_data, url): url
                for url in globoplay_urls
            }

            for future in concurrent.futures.as_completed(futures):
                url = futures[future]

                try:
                    title, m3u8_url, thumbnail_url = future.result()

                    if m3u8_url:
                        thumbnail_url = thumbnail_url or ""

                        output_file.write(
                            f'#EXTINF:-1 tvg-logo="{thumbnail_url}" group-title="GLOBO AO VIVO",{title}\n'
                        )
                        output_file.write(f"{m3u8_url}\n")

                        print(f"Processado: {url}")

                    else:
                        print(f"M3U8 não encontrado: {url}")

                except Exception as e:
                    print(f"Erro ao finalizar {url}: {e}")


# Executa
if __name__ == "__main__":
    generate_m3u()
