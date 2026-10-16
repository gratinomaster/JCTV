import requests
from bs4 import BeautifulSoup
import re

SEARCH_URL = "https://www.google.com/search?q=rtp&sca_esv=4c56c920eaf0b657&udm=vids&biw=1528&bih=732&tbs=qdr%3Ad&sxsrf=APpeQns5pe_IkcCACzvPHgkdmwaASNtHaA%3A1791776213601&ei=1VXMasufJPqj1sQPgM-S8Qo&ved=2ahUKEwiL3unFxrOXAxX6kZUCHYCnJK4Q4dUDegQIBRAM&uact=5&oq=rtp&gs_lp=EhZnd3Mtd2l6LW1vZGVsZXNzLXZpZGVvIgNydHAyChAAGIAEGIoFGEMyCBAAGIAEGLEDMgoQABiABBiKBRhDMgoQABiABBiKBRhDMgUQABiABDIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIKEAAYgAQYigUYQzIFEAAYgAQyBRAAGIAESNkQUPwIWPIOcAN4AJABAJgBb6ABpgOqAQMwLjS4AQPIAQD4AQGYAgagAsQDqAIAwgINEAAYgAQYigUYQxixA8ICBhAAGAcYHsICCxAAGIAEGLEDGIMBwgIOEAAYgAQYigUYsQMYgwGYAwKIBgGSBwMyLjSgB74SsgcDMC40uAe5A8IHBTAuMi40yAcTgAgB&sclient=gws-wiz-modeless-video"

headers = {
  'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
  'Accept-Language': 'pt-PT,pt;q=0.9,en;q=0.8'
}

r = requests.get(SEARCH_URL, headers=headers, timeout=60)
print(r.status_code)
soup = BeautifulSoup(r.text, 'html.parser')
urls = []
for a in soup.find_all('a', href=True):
  href = a['href']
  if '/url?q=' in href:
    m = re.search(r'/url\?q=([^&]+)', href)
    if m: href = m.group(1)
  if href.startswith('http') and 'google.com' not in href and 'youtube.com' not in href:
    urls.append(href)
# dedup
seen=set(); res=[]
for u in urls:
  if u not in seen: res.append(u); seen.add(u)
for u in res[:10]: print(u)
with open('/tmp/links.txt','w') as f:
  for u in res: f.write(u+'\n')
