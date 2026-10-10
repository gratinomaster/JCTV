from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import concurrent.futures
import json
import time
import subprocess

# Configuração do Chrome
options = Options()
options.add_argument("--headless=new")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--window-size=1280,720")

# ativar logs de rede
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

globoplay_urls = [
    "https://www.foxnews.com/video/5614615980001",
    "https://www.foxnews.com/video/5614626175001",
    "https://abcnews.com/Live",
    "https://abcnews.com/live/video/special-live-5/",
    "https://abcnews.com/live/video/special-live-10/",
    "https://www.cbsnews.com/live/",
    "https://www.nbcnews.com/watch"
]

def extract_stream(url):
    driver = webdriver.Chrome(options=options)

    try:
        driver.get(url)
        wait = WebDriverWait(driver, 20)

        # tentar clicar play OU imagem da ABC
        try:
            # 1️⃣ botão genérico
            play = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button"))
            )
            play.click()
        except:
            try:
                # 2️⃣ imagem da ABC (streamprovider)
                img = wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, 'img[src*="streamprovider"]')
                    )
                )

                driver.execute_script("arguments[0].scrollIntoView(true);", img)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", img)

            except:
                pass

        time.sleep(12)

        title = driver.title
        m3u8_list = []
        thumbnail = None

        logs = driver.get_log("performance")

        for entry in logs:
            log = json.loads(entry["message"])["message"]

            if log["method"] == "Network.responseReceived":
                response = log["params"]["response"]
                url_response = response["url"]

                # ignorar tracking
                if url_response.startswith("https://ping.chartbeat.net/ping"):
                    continue

                if ".m3u8" in url_response:
                    m3u8_list.append(url_response)

                if ".jpg" in url_response and thumbnail is None:
                    thumbnail = url_response

        return title, m3u8_list, thumbnail

    except Exception as e:
        print("Erro:", e)
        return None, [], None

    finally:
        driver.quit()


def generate_playlist():
    with open("lista5.m3u", "w", encoding="utf-8") as file:
        file.write("#EXTM3U\n")

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(extract_stream, url): url
                for url in globoplay_urls
            }

            for future in concurrent.futures.as_completed(futures):
                url = futures[future]
                title, m3u8_list, thumb = future.result()

                if m3u8_list:
                    thumb = thumb if thumb else ""

                    for m3u8 in m3u8_list:
                        if m3u8.startswith("https://ping.chartbeat.net/ping"):
                            continue

                        file.write(
                            f'#EXTINF:-1 tvg-logo="{thumb}" group-title="NEWS WORLD",{title}\n'
                        )
                        file.write(f"{m3u8}\n")

                        print("M3U8 encontrado:", m3u8)

                    print("OK:", url)
                else:
                    print("Stream não encontrado:", url)


def testar_url(url):
    try:
        resultado = subprocess.run(
            ["curl", "-Is", "--max-time", "10", url],
            capture_output=True,
            text=True
        )

        if "200" in resultado.stdout:
            return True
    except:
        pass

    return False


if __name__ == "__main__":
    generate_playlist()

    arquivo = "lista5.m3u"

    with open(arquivo, "r", encoding="utf-8") as f:
        linhas = f.readlines()

    saida = []
    saida.append("#EXTM3U\n")

    i = 0
    while i < len(linhas):
        linha = linhas[i].strip()

        if linha.startswith("#EXTINF"):
            info = linha
            url = linhas[i + 1].strip()

            print(f"Testando: {url}")

            if testar_url(url):
                print("OK\n")
                saida.append(info + "\n")
                saida.append(url + "\n")
            else:
                print("OFFLINE\n")

            i += 2
        else:
            i += 1

    with open(arquivo, "w", encoding="utf-8") as f:
        f.writelines(saida)

    print("Lista atualizada!")
