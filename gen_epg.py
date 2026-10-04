#!/usr/bin/env python3
"""Gera EPGFULL.xml.gz com APENAS os canais que existem no NEWSWORLDNOVOS.m3u.

O guia sai enxuto: so entram os tvg-ids presentes na playlist e os programas
dentro da janela de retencao (1 dia atras ate 3 dias depois). Fontes usadas,
em ordem de preferencia quando duas cobrem o mesmo canal:

  1. KORYO.TV (https://koryo.tv/schedule) para a Korean Central Television
     (KCTV). Se o endpoint do KORYO.TV estiver fora do ar, usa o snapshot
     mais recente arquivado no Internet Archive (Wayback Machine) e, se ainda
     assim nao houver dados na janela, a API diaria do Juche TV.
  2. Grade oficial da Al Jazeera (GraphQL do aljazeera.com) para a
     Al Jazeera Arabic, pois o epgshare01 costuma ficar desatualizado.
  3. Grade oficial reportv.com.ar, que publica a programacao fresca dos
     canais venezuelanos e latino-americanos (reproducao do grabber do
     iptv-org, em Python puro).
  4. Pluto TV via i.mjh.nz, para o canal "Big Brother 24/7".
   5. iptv-epg.org, guias XMLTV frescas por pais (AR, CL, MX, FR, UY, PE,
      US, IL, ...). Sao as unicas com cobertura dos canais locais de Buenos
      Aires, Santiago e Mexico na janela de hoje/amanha. Canais cujo sufixo
      de pais nao bate com o sinal sao resolvidos por IPTVEPG_ALIASES.
  6. epgshare01 (https://epgshare01.online/epgshare01/), arquivos por pais,
     usando o indice do proprio site. Quando o tvg-id da playlist nao existe
     no arquivo do pais (a playlist usa IDs curtos, o epgshare01 usa IDs
     longos no estilo "Canal.13.de.Argentina.(El.Trece).ar"), entra o mapa
     ALIASES, que aponta cada apelido para o ID real da fonte.
  7. GLOBOEPG.xml.gz local, como fonte complementar.

A mistura de fontes segue a mesma logica do add-on de EPG do Kodi (slyguy):
para cada canal entra a fonte que cobre mais programas na janela; as demais
so preenchem os horarios que ficaram sem grade (cada programa entra quando
cabe inteiro em um vao da grade), o que evita programas duplicados ou
sobrepostos. Cada fonte grava o horario de parede do pais dela, e quando
duas fontes do mesmo canal discordam do fuso, a que dominou a mistura dita o
fuso: um canal com parte da grade num fuso e parte em outro mostra um salto de
horas no meio da semana no TiviMate. Se EPGFULL.xml.gz ja existir, ele e
sobrescrito. O resultado
e XMLTV valido e compativel com TiviMate (todo <programme> referencia um
<channel> que existe no guia, os tvg-ids casam com a playlist e os programas
saem em ordem cronologica, com o fuso de cada um declarado no atributo).
"""
import gzip
import html
import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import xml.sax.saxutils as sax
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

M3U_URL = "https://github.com/gratinomaster/JCTV/raw/refs/heads/main/NEWSWORLDNOVOS.m3u"
OUTPUT = "EPGFULL.xml.gz"
GLOBO_EPG = "GLOBOEPG.xml.gz"

# Janela de retencao: nao deixar o guia maior do que o necessario. Um dia
# atras (para o usuario ainda ver o que ja passou) e tres dias a frente (o
# suficiente para a grade da semana no TiviMate, sem inflar o arquivo).
KEEP_BEFORE = timedelta(days=1)
KEEP_AFTER = timedelta(days=3)

PYONGYANG = timezone(timedelta(hours=9))
CARACAS = timezone(timedelta(hours=-4))

# Fuso IANA de cada pais que aparece no sufixo do tvg-id. O guide mostra o
# horario no fuso do pais, com a hora de verao ja embutida pelo zoneinfo (o
# Chile, por exemplo, esta em -0300 agora e em -0400 no inverno).
TZ_BY_SUFFIX = {
    "ar": "America/Argentina/Buenos_Aires",
    "br": "America/Sao_Paulo",
    "cl": "America/Santiago",
    "cn": "Asia/Shanghai",
    "es": "Europe/Madrid",
    "fr": "Europe/Paris",
    "il": "Asia/Jerusalem",
    "ir": "Asia/Tehran",
    "mx": "America/Mexico_City",
    "net": "Asia/Riyadh",       # Al Jazeera Arabic
    "pe": "America/Lima",
    "pt": "Europe/Lisbon",
    "py": "America/Asuncion",
    "uy": "America/Montevideo",
    "us": "America/New_York",   # os guias .us do iptv-epg sao do horario de Nova York
    "ve": "America/Caracas",
}
# Fuso em que a grade deste canal e publicada, quando o pais do tvg-id nao for o
# pais que emite o sinal (vale tambem para quem so existe na fonte por apelido).
# Usado na conferencia final: cada fonte grava o horario de parede do pais dela
# (ver wall_clock), e aqui fica o fuso com que o guia deve aparecer.
TZ_BY_ID = {
    "HispanTV.ir": "America/Argentina/Buenos_Aires",   # guia argentino
    "CGTNSpanish.cn": "America/Montevideo",             # guia uruguayo
    "DePelícula.mx": "America/New_York",                # guia dos EUA
    "AztecaInternacional.us": "America/Mexico_City",    # guia mexicano
}

KORYO_EPG_URL = "https://koryo.tv/api/epg/b2ad0bb59619601b6dd7069a.dat"
KORYO_HEADER = {
    "X-Koryo-Epg": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Referer": "https://koryo.tv/schedule",
}

EPGSHARE01_INDEX = "https://epgshare01.online/epgshare01/"
EPGSHARE01_URL = "https://epgshare01.online/epgshare01/{}"

# iptv-epg.org: guia XMLTV por pais, atualizada varias vezes ao dia, com a
# programacao completa dos canais locais (ao contrario do epgshare01, que so
# traz os canais abertos de cada pais). Os canais vem com o mesmo tvg-id da
# playlist, entao nao precisa de apelido.
IPTVEPG_URL = "https://iptv-epg.org/files/epg-{}.xml.gz"

# reportv.com.ar: grade oficial dos canais latino-americanos, muito usada por
# provedores da regiao. O endpoint e um POST que devolve o HTML de uma janela
# de dias seguidos, entao fetch_reportv corta o trecho do dia pedido.
REPORTV_PROGRAM_URL = "https://www.reportv.com.ar/buscador/ProgXSenial.php"
REPORTV_ALIGN = "2694"
REPORTV_CHANNELS_URL = (
    "https://raw.githubusercontent.com/iptv-org/epg/master/sites/"
    "reportv.com.ar/reportv.com.ar.channels.xml"
)
# Mapa de reserva (tvg-id -> site_id) para o caso de a lista de canais do
# iptv-org estar indisponivel na hora da geracao.
REPORTV_SITE_IDS = {
    "ANTV.ve": "2187",
    "AvilaTV.ve": "3300",
    "CanalI.ve": "967",
    "Colombeia.ve": "2626",
    "ConCienciaTV.ve": "2831",
    "Globovision.ve": "309",
    "IVC.ve": "3315",
    "LaTeleTuya.ve": "3530",
    "MeridianoTV.ve": "934",
    "Televen.ve": "408",
    "Telesur.ve": "388",
    "TVes.ve": "2186",
    "TVFANB.ve": "3313",
    "ValeTV.ve": "3357",
    "VepacoTV.ve": "3352",
    "VenezolanadeTelevision.ve": "420",
    "Venevision.ve": "2138",
    "Vive.ve": "407",
}
# A fonte so publica poucos dias a frente; nao adianta pedir mais que isso.
REPORTV_DAYS = 3

# Pluto TV: o canal "Big Brother 24/7" (tvg-id BigBrother.us) tem guia real
# publicado no i.mjh.nz com o site_id 6661f11a41af6400080e90d8.
PLUTO_BB_ID = "BigBrother.us"
PLUTO_BB_SRC_ID = "6661f11a41af6400080e90d8"

# i.mjh.nz: guias XMLTV por plataforma. Os canais usam um id interno na fonte,
# entao tudo e remapeado para o tvg-id da playlist antes de entrar no guia.
IMJHNZ_BASE = "https://raw.githubusercontent.com/matthuisman/i.mjh.nz/master"
# tvg-id da playlist -> (feed do guia no i.mjh.nz, id interno do canal).
IMJHNZ_CHANNELS = {
    PLUTO_BB_ID: ("PlutoTV/all", PLUTO_BB_SRC_ID),
    "VenevisionInternacional.ve": ("Roku/all", "cc04d77fd589a818cd036c850b6be867"),
}

# Lista de canais ao vivo do proprio reportv.com.ar. Serve para pegar canais
# que o iptv-org ainda nao mapeou (o "SHOWVEN TV", por exemplo), comparando o
# nome do canal com o tvg-id sem o sufixo de pais.
REPORTV_LIST_URL = "https://www.reportv.com.ar/buscador/Buscador.php?aid=2694"
# Abaixo desse tamanho o nome fica curto demais para casar com seguranca
# ("AMC", "Vive" e afins existem em varios paises).
REPORTV_NAME_MIN = 6

# Canais cujo tvg-id da playlist carrega um pais que nao e o do sinal (o
# sufixo e do anotador, nao do emissor). O canal e procurado no guia do pais
# real e o id e remapeado para o da playlist.
IPTVEPG_ALIASES = {
    "HispanTV.ir": "HispanTV.ar",
    "CGTNSpanish.cn": "CGTNESPAÑOL.uy",
}

JUCHE_API = "https://juche-tv-epg-api.vercel.app/api/bloxyplaytv?ch=KCTV&date={}"

# Dados diarios de KCTV publicados no repo Bloxyplay/JucheTV-EPG-API (mesma
# fonte que o site Juche TV exibe), usados quando o KORYO.TV esta fora do ar.
JUCHE_GITHUB_URL = "https://raw.githubusercontent.com/Bloxyplay/JucheTV-EPG-API/main/epg/KCTV/{}.json"

# Al Jazeera Arabic: a grade oficial (GraphQL do aljazeera.com) cobre 7 dias,
# enquanto o arquivo ALJAZEERA1 do epgshare01 costuma ficar dias desatualizado
# para este canal. Os horarios do site sao de Meca (UTC+3).
ALJAZEERA_AR_ID = "AlJazeera.Arabic.net"
# Duracao maxima aceita da grade oficial da Al Jazeera. O site publica um item
# noticioso de 23:59:59 (ver fetch_aljazeera_arabic) que e preenchimento de
# madrugada, nao um programa; o limite separa um do outro.
ALJAZEERA_MAX_ITEM = timedelta(hours=6)
AJA_GRAPHQL_URL = (
    "https://www.aljazeera.com/graphql?wp-site=aja"
    "&operationName=ArchipelagoSchedulePageQuery"
    "&variables=%7B%22postName%22%3A%22schedule%22%2C%22preview%22%3A%22%22%7D"
    "&extensions=%7B%7D"
)

# Sufixos de tvg-id que devem consultar mais de um arquivo (ou um arquivo
# especial) do epgshare01, alem do arquivo padrao do pais. Chaves em
# minusculas, iguais as chaves do indice.
EXTRA_FILES_BY_SUFFIX = {
    "br": ["br2"],        # Rede Vida usa IDs exatos que so existem no BR2
    "net": ["aljazeera"], # Al Jazeera Arabic tem arquivo proprio
}

# tvg-ids da playlist que nao existem com o mesmo nome nas fontes.
# Formato: tvg-id -> [(chave do arquivo no indice, id real na fonte), ...].
# A ordem define a preferencia. So use apelidos confirmados (mesmo canal),
# nunca canais apenas parecidos.
ALIASES = {
    # Argentina
    "TVPublica.ar": [("ar", "Canal.Televisión.Pública.(Argentina).ar")],
    "ELTrece.ar": [("ar", "Canal.13.de.Argentina.(El.Trece).ar")],
    "AmericaTV.ar": [("ar", "Canal.America.TV.(Argentina).ar")],
    "TyCSports.ar": [("ar", "Canal.TyC.Sports.ar")],
    "ElGourmet.ar": [("ar", "Canal.Elgourmet.ar")],
    "DisneyChannel.ar": [("ar", "Canal.Disney.Channel.(Argentina).ar")],
    "DisneyJunior.ar": [("ar", "Canal.Disney.Junior.(Argentina).ar")],
    "MTV.ar": [("ar", "Canal.MTV.(Argentina).ar")],
    "Sony.ar": [("ar", "Canal.Sony.(Argentina).ar")],
    "AMC.ar": [("cl", "Canal.AMC.(Chile).cl")],  # sinal pan-regional, sem AR1
    "TelemundoInternacional.ar": [("mx", "Canal.Telemundo.(México).mx")],
    "Telefe.ar": [("mx", "Canal.Telefe.Internacional.mx")],
    # Chile
    "Chilevision.cl": [("cl", "Canal.Chilevisión.(CHV).cl")],
    "TVN.cl": [("cl", "Canal.TVN.(Chile).cl")],
    "LaRed.cl": [("cl", "Canal.La.Red.(Chile).cl")],
    "Mega.cl": [("cl", "Canal.Mega.(Chile).cl")],
    "Canal13.cl": [("cl", "Canal.13.de.Chile.cl")],
    "TVChile.cl": [("cl", "TV.Chile.cl")],
    "ViaX.cl": [("cl", "Canal.Vía.X.cl")],
    "ZonaLatina.cl": [("cl", "Canal.Zona.Latina.cl")],
    # Mexico
    "AztecaUno.mx": [("mx", "Canal.Azteca.Uno.-1.Hora.mx")],
    "MilenioTV.mx": [("mx", "Canal.Milenio.TV.mx")],
    "TVUNAM.mx": [("mx", "Canal.TVUNAM.mx")],
    "CanalMexiquense.mx": [("mx", "Canal.Mexiquense.TV.mx")],
    "TeleFormula.mx": [("mx", "Teleformula.mx")],
    "Sony.mx": [("mx", "Canal.Sony.(México).mx")],
    "TLNovelas.mx": [("mx", "Canal.TLNovelas.(México).mx")],
    "Telemundo.mx": [("mx", "Canal.Telemundo.(México).mx")],
    "EWTN.mx": [("mx", "Canal.EWTN.en.Español.mx")],
    "DePelícula.mx": [("us", "De.Pelicula.us2")],
    "Canal5.mx": [("mx", "Canal.5.de.México.(XHGC).mx")],
    "Canal14.mx": [("mx", "Canal.14.de.México.mx")],
    "Canal22.mx": [("mx", "Canal.22.de.México.mx")],
    "Univision.mx": [("cl", "Canal.Univision.(Chile).cl")],
    # EUA
    "EstrellaTV.us": [("us", "ESTRELLA.NEWS.us2")],
    "AztecaInternacional.us": [("mx", "Azteca.(XHOR).mx")],
}

# Desempate na mistura: quando duas fontes cobrem a mesma quantidade de
# programas, vale a da fonte oficial (grade do proprio emissor).
SOURCE_RANK = {
    "koryo": 0,
    "aljazeera": 1,
    "reportv": 2,
    "pluto": 3,
    "iptv-epg": 4,
    "epgshare01": 5,
    "globo": 6,
}

# Fuentes que gravam horario de parede (os digitos do programa sao a hora
# local do canal, e o atributo de fuso e reescrito para o pais do tvg-id).
WALL_CLOCK_SOURCES = {"iptv-epg", "epgshare01"}

# De qual fonte saiu cada <programme> que entrou no arquivo, para a conferencia
# de fuso saber o que eh horario local e o que ja vem em UTC.
BLOCK_SOURCE = {}

# reportv.com.ar rotula os dias em portugues ("29 Septiembre 2026").
SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def http_get(url, headers=None, timeout=90, retries=1, delay=5):
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                print(f"      Tentativa {attempt+1}/{retries} falhou ({e}); aguardando {delay}s...")
                time.sleep(delay)
    raise last_err


def http_post_form(url, fields, headers=None, timeout=90):
    body = urllib.parse.urlencode(fields).encode()
    hdrs = {"Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_m3u(data):
    channels = {}
    for line in data.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        tvg_id = re.search(r'tvg-id="([^"]*)"', line)
        tvg_name = re.search(r'tvg-name="([^"]*)"', line)
        tvg_logo = re.search(r'tvg-logo="([^"]*)"', line)
        cid = tvg_id.group(1) if tvg_id else ""
        if cid and cid not in channels:
            channels[cid] = {
                "name": tvg_name.group(1) if tvg_name else cid,
                "logo": tvg_logo.group(1) if tvg_logo else "",
            }
    return channels


def country_of(cid):
    """Pais do tvg-id, pelo sufixo: "...ar" -> "ar", "...us2" -> "us"."""
    last = cid.rsplit(".", 1)[-1]
    return re.sub(r"\d+$", "", last).lower()


def channel_tz(cid):
    """Fuso IANA do canal, ou None se o pais do tvg-id nao for conhecido."""
    name = TZ_BY_ID.get(cid) or TZ_BY_SUFFIX.get(country_of(cid))
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except Exception:
        return None


def local_offset_str(digits, tz):
    """Offset (+/-HHMM) de um horario de parede do canal, com verao incluido.

    "20261003160000" em Santiago, dentro do horario de verao, devolve "-0300";
    o mesmo horario no inverno devolveria "-0400".
    """
    local = datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=tz)
    return local.strftime("%z")


def relabel_local_clock(block, tz):
    """Corrige o fuso dos horarios de um <programme> de parede local.

    O iptv-epg.org grava o horario do pais com "+0000" e o epgshare01 com
    "-0500" fixo, entao o TiviMate converte o programa para o fuso do aparelho
    e a grade aparece adiantada (no Chile e na Argentina, 2 a 3 horas). Os
    digitos ja sao o horario de parede do canal, entao a correcao e apenas
    reescrever o atributo de fuso com o valor certo para aquela data.
    """
    if tz is None:
        return block

    def fix(match):
        attr, digits = match.group(1), match.group(2)
        return '{}="{} {}"'.format(attr, digits, local_offset_str(digits, tz))

    return re.sub(r'\b(start|stop)="(\d{14})[ ]?[+-]\d{4}"', fix, block)


def restamp_instant(block, tz):
    """Reescreve no fuso do canal um <programme> que ja veio em instante.

    As fontes de horario de parede (iptv-epg, epgshare01) dominam a mistura de
    um canal; quando a outra fonte entrega o horario ja convertido (a grade
    oficial da Al Jazeera, o reportv), os digitos ficam em outro fuso e o
    TiviMate mostra um salto de horas no meio da semana. Reescrever os digitos
    no fuso que dominou mantem o mesmo instante - o TiviMate converte a partir
    do atributo, entao a exibicao nao muda - e deixa o canal inteiro com um fuso
    so.
    """
    def fix(match):
        attr, stamp = match.group(1), match.group(2)
        try:
            instant = datetime.strptime(stamp, "%Y%m%d%H%M%S %z")
        except ValueError:
            return match.group(0)
        return '{}="{}"'.format(
            attr, instant.astimezone(tz).strftime("%Y%m%d%H%M%S %z"))

    return re.sub(r'\b(start|stop)="(\d{14} [+-]\d{4})"', fix, block)


def wall_clock(blocks, cid):
    """Rotula os horarios como horario de parede do canal da fonte.

    O iptv-epg.org e o epgshare01 gravam o horario local do pais com um
    atributo de fuso fixo, e o TiviMate converte o programa para o fuso do
    aparelho a partir desse atributo: se o fuso gravado nao for o do canal, a
    grade aparece adiantada ou atrasada. O fuso vem do id do canal na fonte
    (e nao do tvg-id da playlist), porque um canal que so aparece na fonte por
    apelido - De.Pelicula.us2 servindo DePelícula.mx, por exemplo - tem
    horario de parede do pais da fonte, nao do pais do apelido.

    Devolve (blocos, fuso) para o merge saber qual fuso a fonte gravou.
    """
    tz = channel_tz(cid)
    if tz is None:
        return blocks, None
    return [relabel_local_clock(b, tz) for b in blocks], tz


def wayback_latest(url):
    today = datetime.now(timezone.utc).date()
    for cand in (url.split("://", 1)[-1], url):
        for ts in (today, today + timedelta(days=1)):
            api = "http://archive.org/wayback/available?url={}&timestamp={}".format(
                urllib.parse.quote(cand, safe=""), ts.strftime("%Y%m%d")
            )
            try:
                info = json.loads(http_get(api, timeout=30).decode("utf-8", errors="ignore"))
            except Exception:
                continue
            snap = (info.get("archived_snapshots") or {}).get("closest") or {}
            if snap.get("available") and snap.get("status") == "200":
                return snap["url"]
    return None


def fetch_koryo():
    live = True
    source = "KORYO.TV (ao vivo)"
    try:
        raw = http_get(KORYO_EPG_URL, headers=KORYO_HEADER)
    except Exception as e:
        print(f"    ERRO no endpoint koryo ({e}); procurando snapshot no Wayback Machine...")
        raw = None
        try:
            snap_url = wayback_latest(KORYO_EPG_URL)
            if snap_url:
                print(f"    Snapshot encontrado: {snap_url}")
                # O sufixo "id_" faz o Wayback Machine servir o arquivo bruto
                # (sem a pagina HTML de confirmacao).
                snap_url = re.sub(r"/web/(\d+)/", r"/web/\1id_/", snap_url)
                raw = http_get(snap_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
                source = "Internet Archive (Wayback Machine)"
                live = False
        except Exception as e2:
            print(f"    ERRO ao consultar o Wayback Machine: {e2}")
    if not raw:
        raise RuntimeError("Nao foi possivel baixar o EPG do KORYO.TV (fonte e snapshot indisponiveis)")
    data = gzip.decompress(raw).decode("utf-8", errors="ignore")
    events = json.loads(data).get("events", [])
    return events, source, live


def fetch_aljazeera_arabic(tvg_id, oldest_ok, newest_ok):
    """EPG oficial da Al Jazeera Arabic (GraphQL do aljazeera.com).

    Cada item traz showTimeslot (HH:mm) e duration ("H:M:S", as vezes com
    numeros de um so digito) relativos ao dia em startDate (meia-noite UTC).
    Os horarios do site sao de Meca (UTC+3) - confirmado comparando o bloco
    "يعرض الآن" renderizado pelo servidor com a hora atual.
    """
    raw = http_get(AJA_GRAPHQL_URL,
                   headers={"wp-site": "aja", "User-Agent": "Mozilla/5.0"},
                   timeout=60)
    schedule = json.loads(raw.decode("utf-8", errors="ignore"))
    schedule = (schedule.get("data") or {}).get("post") or {}
    schedule = schedule.get("schedule") or []
    mecca = timezone(timedelta(hours=3))
    blocks = []
    skipped = 0
    for item in schedule:
        try:
            day0 = datetime.fromtimestamp(int(item["startDate"]), tz=timezone.utc)
            hh, mm = str(item["showTimeslot"]).split(":")[:2]
            start = day0.replace(hour=int(hh), minute=int(mm),
                                 second=0, microsecond=0,
                                 tzinfo=mecca).astimezone(timezone.utc)
        except Exception:
            continue
        m = re.match(r"(\d+):(\d+)(?::(\d+))?", str(item.get("duration") or ""))
        if m:
            dur = timedelta(hours=int(m.group(1)), minutes=int(m.group(2)),
                            seconds=int(m.group(3) or 0))
        else:
            dur = timedelta(hours=1)
        if dur > ALJAZEERA_MAX_ITEM:
            # O site usa um item "nشرة الأخبار" de 23:59:59 as 23:00 como
            # preenchimento da madrugada: ele vai das 23:00 de um dia ate a
            # meia-noite do dia seguinte, ou seja, cobre o dia inteiro que vem.
            # Esse dia e o dia de hoje, que o epgshare01 ja publica cortado de
            # hora em hora; manter o item de 24h aqui esconderia a grade real
            # de hoje (o TiviMate mostraria so "نشرة الأخبار" o dia todo).
            skipped += 1
            continue
        stop = start + dur
        if start < oldest_ok or start > newest_ok:
            continue
        title = (item.get("showName") or "").strip() or "Sem titulo"
        desc = (item.get("showDescription") or "").strip()
        parts = [
            f'  <programme start="{start.strftime("%Y%m%d%H%M%S")} +0000" '
            f'stop="{stop.strftime("%Y%m%d%H%M%S")} +0000" '
            f'channel="{sax.escape(tvg_id)}">',
            f'    <title lang="ar">{sax.escape(title)}</title>',
        ]
        if desc:
            parts.append(f'    <desc lang="ar">{sax.escape(desc)}</desc>')
        parts.append("  </programme>")
        blocks.append("\n".join(parts))
    if skipped:
        print(f"      {skipped} item(ns) de preenchimento (24h) do site ignorados")
    return blocks


def fetch_juche(koryo_id, oldest_ok, newest_ok):
    """Fallback para KCTV: programacao diaria do Juche TV (API independente)."""
    programmes = []
    seen = set()
    day = oldest_ok.date()
    end_day = newest_ok.date()
    while day <= end_day:
        iso_day = day.strftime("%Y-%m-%d")
        try:
            data = json.loads(http_get(JUCHE_API.format(iso_day), timeout=60)
                              .decode("utf-8", errors="ignore"))
        except Exception:
            data = {}
        for prog in data.get("programs", []):
            try:
                start = datetime.fromisoformat(f"{iso_day}T{prog['start']}:00+09:00")
                end = datetime.fromisoformat(f"{iso_day}T{prog['end']}:00+09:00")
            except Exception:
                continue
            if end <= start:
                end += timedelta(days=1)
            if start < oldest_ok or start > newest_ok:
                continue
            title = prog.get("title") or {}
            category = prog.get("category") or {}
            ev = {
                "startUtc": start.isoformat(),
                "endUtc": end.isoformat(),
                "title": title.get("ko"),
                "titleEn": title.get("en"),
                "category": category.get("en") or category.get("ko"),
            }
            block = build_programme(ev, koryo_id)
            key = (koryo_id, block)
            if key not in seen:
                seen.add(key)
                programmes.append(block)
        day += timedelta(days=1)
    return programmes


def fetch_juche_github(koryo_id, oldest_ok, newest_ok):
    """Fallback para KCTV: arquivos diarios do Bloxyplay/JucheTV-EPG-API.

    Os arquivos (epg/KCTV/YYYY-MM-DD.json) contem a mesma programacao que o
    site Juche TV exibe; horarios em Pyongyang, sem depender do KORYO.TV.
    """
    programmes = []
    seen = set()
    day = oldest_ok.date()
    end_day = newest_ok.date()
    while day <= end_day:
        iso_day = day.strftime("%Y-%m-%d")
        try:
            data = json.loads(http_get(JUCHE_GITHUB_URL.format(iso_day), timeout=60)
                              .decode("utf-8", errors="ignore"))
        except Exception:
            day += timedelta(days=1)
            continue
        for prog in data.get("programs", []):
            try:
                start = datetime.strptime(f"{iso_day}T{prog['start']}:00+09:00",
                                          "%Y-%m-%dT%H:%M:%S%z")
                end = datetime.strptime(f"{iso_day}T{prog['end']}:00+09:00",
                                        "%Y-%m-%dT%H:%M:%S%z")
            except Exception:
                continue
            if end <= start:
                end += timedelta(days=1)
            if start < oldest_ok or start > newest_ok:
                continue
            title = prog.get("title") or {}
            ev = {
                "startUtc": start.isoformat(),
                "endUtc": end.isoformat(),
                "title": title.get("ko"),
                "titleEn": title.get("en"),
            }
            block = build_programme(ev, koryo_id)
            key = (koryo_id, block)
            if key not in seen:
                seen.add(key)
                programmes.append(block)
        day += timedelta(days=1)
    return programmes


def koryo_target_id(channels):
    for cid in channels:
        low = cid.lower()
        if "koreancentral" in low or "kctv" in low or low.endswith(".kp"):
            return cid
    return None


def iso_to_xmltv(iso_str):
    dt = datetime.fromisoformat(iso_str).astimezone(PYONGYANG)
    return dt.strftime("%Y%m%d%H%M%S") + " +0900"


def build_programme(ev, tvg_id):
    title = ev.get("titleEn") or ev.get("title") or "Sem titulo"
    lang = "en" if ev.get("titleEn") else "ko"
    parts = [f'  <programme start="{iso_to_xmltv(ev["startUtc"])}" '
             f'stop="{iso_to_xmltv(ev["endUtc"])}" channel="{tvg_id}">']
    parts.append(f'    <title lang="{lang}">{sax.escape(title)}</title>')
    if ev.get("category"):
        parts.append(f'    <category lang="en">{sax.escape(ev["category"])}</category>')
    if ev.get("title") and ev.get("titleEn"):
        parts.append(f'    <sub-title lang="ko">{sax.escape(ev["title"])}</sub-title>')
    parts.append("  </programme>")
    return "\n".join(parts)


def parse_xmltv_time(s):
    s = s.strip()
    try:
        return datetime.strptime(s, "%Y%m%d%H%M%S %z")
    except ValueError:
        try:
            return datetime.strptime(s[:8], "%Y%m%d").replace(tzinfo=PYONGYANG)
        except Exception:
            return None


def block_start(block):
    m = re.search(r'start="(\d{8}\d{6}\s+[+-]\d{4})"', block)
    return parse_xmltv_time(m.group(1)) if m else None


def block_stop(block):
    m = re.search(r'stop="(\d{8}\d{6}\s+[+-]\d{4})"', block)
    return parse_xmltv_time(m.group(1)) if m else None


def list_epgshare01_files():
    """Indice do epgshare01: chave de pais -> lista de arquivos disponiveis."""
    html_page = http_get(EPGSHARE01_INDEX, timeout=60).decode("utf-8", errors="ignore")
    mapping = {}
    for fn in re.findall(r'href="(epg_ripper_[A-Za-z0-9]+\.xml\.gz)"', html_page):
        m = re.match(r"epg_ripper_([A-Za-z]+?)\d*\.xml\.gz", fn)
        if m:
            mapping.setdefault(m.group(1).lower(), []).append(fn)
    return mapping


def epgshare01_files_for(cid, index):
    """Arquivos do epgshare01 onde o tvg-id pode existir (pais + extras)."""
    keys = [country_of(cid)]
    for extra in EXTRA_FILES_BY_SUFFIX.get(country_of(cid), []):
        if extra not in keys:
            keys.append(extra)
    files = []
    for key in keys:
        files.extend(f for f in index.get(key, []) if f not in files)
    return files


def remap_channel_ref(block, src_id, dst_id):
    return block.replace('channel="{}"'.format(src_id),
                         'channel="{}"'.format(dst_id))


def remap_channel_block(block, src_id, dst_id):
    return block.replace('id="{}"'.format(src_id), 'id="{}"'.format(dst_id))


def extract_xmltv(url, wanted, oldest_ok, newest_ok, retries=1, delay=5):
    """Baixa um XMLTV .gz e extrai apenas os canais desejados.

    Retorna (channels, programmes): dicts de tvg-id -> lista de blocos XML.
    Os horarios sao entregues como vieram da fonte; quem grava o horario de
    parede do canal e o coletor, com o fuso do tvg-id da playlist
    (ver relabel_local_clock).
    """
    channels = {}
    programmes = {}
    raw = http_get(url, timeout=240, retries=retries, delay=delay)
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        tmp.write(raw)
        tmp.close()
        with gzip.open(tmp.name, "rb") as f:
            for _event, elem in ET.iterparse(f, events=("end",)):
                if elem.tag == "channel":
                    cid = elem.get("id")
                    if cid in wanted:
                        channels.setdefault(cid, ET.tostring(elem, encoding="unicode"))
                    elem.clear()
                elif elem.tag == "programme":
                    cid = elem.get("channel")
                    if cid in wanted:
                        start = parse_xmltv_time(elem.get("start", ""))
                        if start is not None and oldest_ok <= start <= newest_ok:
                            block = ET.tostring(elem, encoding="unicode")
                            programmes.setdefault(cid, []).append(block)
                    elem.clear()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    return channels, programmes


def remap_imjhnz(channels, programmes, src_id, dst_id):
    """Troca o id interno do i.mjh.nz pelo tvg-id da playlist, no bloco do
    canal e no de cada programa."""
    out_channels = {}
    for _cid, block in channels.items():
        out_channels[dst_id] = remap_channel_block(block, src_id, dst_id)
    out_programmes = {}
    for blocks in programmes.values():
        for b in blocks:
            out_programmes.setdefault(dst_id, []).append(
                remap_channel_ref(b, src_id, dst_id)
            )
    return out_channels, out_programmes


def normalize_name(text):
    """Nome de canal sem acento, caixa e pontuacao, para comparar dois nomes."""
    folded = unicodedata.normalize("NFKD", text)
    folded = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", folded.lower())


def reportv_site_ids(wanted_ids):
    """tvg-id -> site_id do reportv.com.ar, só para canais da Venezuela.

O reportv publica a grade no horario de Caracas e a lista do iptv-org
    (que traz o xmltv_id de cada canal) e a via principal; para o que ficar
    de fora, a lista ao vivo do proprio site entra como segunda via, casada
    pelo nome. Esse casamento por nome e perigoso fora da Venezuela: o site
    tem um unico "CANAL 13" (o do Mexico) e um unico "EL GOURMET" (o do
    Mexico tambem), entao um canal chileno ou argentino passaria a exibir a
    grade de outro emissor. Por isso o casamento por nome fica restrito a ".ve".
    """
    mapping = {k: v for k, v in REPORTV_SITE_IDS.items()
               if country_of(k) == "ve"}
    try:
        raw = http_get(REPORTV_CHANNELS_URL, timeout=60).decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"    ERRO ao ler a lista de canais do reportv ({e}); usando o mapa de reserva")
        return mapping
    for m in re.finditer(r'<channel\b[^>]*>', raw):
        tag = m.group(0)
        sid = re.search(r'site_id="(\d+)"', tag)
        xid = re.search(r'xmltv_id="([^"]*)"', tag)
        if not sid or not xid or not xid.group(1):
            continue
        # O iptv-org anota o feed depois do "@" (ex.: "Globovision.ve@SD").
        cid = xid.group(1).split("@")[0]
        if country_of(cid) == "ve":
            mapping.setdefault(cid, sid.group(1))

    pending = [cid for cid in wanted_ids
               if cid not in mapping and country_of(cid) == "ve"]
    if not pending:
        return mapping
    try:
        page = http_get(REPORTV_LIST_URL, timeout=60).decode("utf-8", errors="replace")
    except Exception as e:
        print(f"    ERRO ao ler a lista ao vivo do reportv ({e})")
        return mapping
    by_name = {}
    for sid, name in re.findall(r"<option value='(\d+)'[^>]*>([^<]*)</option>", page):
        by_name.setdefault(normalize_name(html.unescape(name)), set()).add(sid)
    for cid in pending:
        key = normalize_name(re.sub(r"\.[a-z]+\d*$", "", cid))
        if len(key) < REPORTV_NAME_MIN:
            continue
        found = by_name.get(key)
        # So aceita quando o nome do site e inequivoco: um unico id para o nome.
        if found and len(found) == 1:
            mapping[cid] = found.pop()
            print(f"      {cid}: casado com '{cid}' pelo nome no reportv")
    return mapping


def reportv_day_tag(day):
    """Cabecalho de dia usado pelo site (ex.: "Jueves 01 Octubre 2026").

    O dia vem com dois digitos; casar so com o numero solto faria "1 Octubre
    2026" bater tambem com "11 Octubre 2026", o que duplica programas.
    """
    return "{} {} {}".format(f"{day.day:02d}",
                             SPANISH_MONTHS[day.month - 1].capitalize(), day.year)


def reportv_day_sections(page):
    """Quebra a grade do reportv em (cabecalho do dia, linhas do dia).

    A resposta traz sempre uma janela de ~11 dias seguidos; e preciso cortar
    pelo cabecalho de cada dia para nao atribuir a data errada.
    """
    parts = re.split(r'<div\s+id="[^"]*"\s+style="[^"]*"\s+class="trFecha"[^>]*>',
                     page)
    sections = []
    for part in parts[1:]:
        # O trecho comeca pelo texto do cabecalho e depois vem o </div> de
        # fechamento mais as linhas do dia.
        head = re.split(r"<", part, 1)[0]
        header = html.unescape(head).strip()
        body = part[len(head):]
        sections.append((header, body))
    return sections


def reportv_programme_block(tvg_id, title, genre, category, start, stop):
    parts = [
        '  <programme start="{}" stop="{}" channel="{}">'.format(
            start.strftime("%Y%m%d%H%M%S") + " -0400",
            stop.strftime("%Y%m%d%H%M%S") + " -0400",
            sax.escape(tvg_id),
        ),
        "    <title>{}</title>".format(sax.escape(title)),
    ]
    if genre:
        parts.append("    <class>{}</class>".format(sax.escape(genre)))
    if category:
        parts.append("    <category>{}</category>".format(sax.escape(category)))
    parts.append("  </programme>")
    return "\n".join(parts)


def fetch_reportv(tvg_id, site_id, days):
    """Grade de um canal no reportv.com.ar (um POST por dia).

    Cada bloco do site tem o formato:
      <div id="trProg_123" title=" - Martes 29 Septiembre 2026 00:00:00"
           class="trProg" ...>
        <div ...><span>00:00 - Iglesia universal</span></div>  <- hora - titulo
        <div ...><span>Variedades</span></div>                <- genero
        <div ...><span>Religioso</span></div>                  <- categoria
        <div ...><span>00:45:00</span></div>                   <- duracao
      </div>
    Os horarios sao de Caracas (UTC-4).
    """
    blocks = []
    for day in days:
        try:
            page = http_post_form(REPORTV_PROGRAM_URL, {
                "idSenial": site_id,
                "Alineacion": REPORTV_ALIGN,
                "DiaDesde": day.strftime("%Y/%m/%d"),
                "HoraDesde": "00:00:00",
            })
        except Exception as e:
            print(f"    reportv {tvg_id} {day:%Y-%m-%d}: ERRO ({e})")
            continue
        tag = reportv_day_tag(day)
        for header, body in reportv_day_sections(page):
            # O cabecalho traz o dia da semana na frente; a comparacao e pela
            # data. Terminar a string evita casar 01 con 11.
            if not header.endswith(tag):
                continue
            chunks = re.split(r'<div\s+id="trProg_', body)[1:]
            cells_for = lambda chunk: [
                html.unescape(re.sub("<[^>]+>", "", s)).strip()
                for s in re.findall(r"<span>(.*?)</span>", chunk, re.S)
            ]
            for chunk in chunks:
                cells = cells_for(chunk)
                if len(cells) < 4 or not re.match(r"^\d{2}:\d{2} - ", cells[0]):
                    continue
                dm = re.match(r"^(\d{2}):(\d{2}):(\d{2})$", cells[3])
                if not dm:
                    continue
                hh, mm = cells[0][:5].split(":")
                start = datetime(day.year, day.month, day.day,
                                 int(hh), int(mm), tzinfo=CARACAS)
                stop = start + timedelta(hours=int(dm.group(1)),
                                        minutes=int(dm.group(2)),
                                        seconds=int(dm.group(3)))
                title = cells[0][5:].strip() or "Sem titulo"
                blocks.append(reportv_programme_block(tvg_id, title, cells[1],
                                                      cells[2], start, stop))
    return blocks


# Ordem dos filhos que o DTD do XMLTV exige (xmltv.dtd do projeto XMLTV). As
# fontes gravam o <programme> na ordem em que serializaram os elementos e usam
# tags que nao existem no XMLTV (ex.: <class>), alem de repetir <title>. O
# TiviMate e o add-on do kodi que mistura EPGs leem por nome e nao quebram, mas
# um guia dentro do padrao evita que o arquivo seja recusado por validador
# estrito e descarta o que nao interessa para a grade exibida.
XMLTV_PROGRAMME_ORDER = (
    "title", "sub-title", "desc", "credits", "date", "category", "keyword",
    "language", "orig-language", "length", "icon", "url", "country",
    "episode-num", "video", "audio", "previously-shown", "premiere",
    "last-chance", "new", "subtitles", "rating", "star-rating", "review",
    "image",
)
# Elementos que o DTD aceita no maximo uma vez dentro de <programme>.
XMLTV_PROGRAMME_SINGLE = frozenset({
    "credits", "date", "video", "audio", "previously-shown", "premiere",
    "last-chance", "new", "review", "language", "orig-language", "length",
})
XMLTV_CHANNEL_ORDER = ("display-name", "icon", "url")
XMLTV_CREDITS_ORDER = (
    "director", "actor", "writer", "adapter", "producer", "composer",
    "editor", "presenter", "commentator", "guest",
)
XMLTV_NESTED_ORDER = {
    "video": ("present", "colour", "aspect", "quality"),
    "audio": ("present", "stereo"),
    "subtitles": ("language",),
    "rating": ("value", "icon"),
    "star-rating": ("value", "icon"),
}


def order_children(elem, order, single=()):
    """Deixa os filhos de `elem` na ordem do DTD, sem tag fora dele nem repetida."""
    index = {tag: i for i, tag in enumerate(order)}
    kept = [c for c in elem if c.tag in index]
    kept.sort(key=lambda c: index[c.tag])
    seen = set()
    final = []
    for c in kept:
        if c.tag in single:
            if c.tag in seen:
                continue
            seen.add(c.tag)
        final.append(c)
    elem[:] = final


def normalize_block(block):
    """Reescreve um <channel>/<programme> isolado dentro do padrao XMLTV.

    Devolve o bloco indentado e pronto para gravar. Bloco que o ElementTree
    nao conseguir ler volta sem alteracao, para nunca perder parte da grade.
    """
    if not block:
        return block
    try:
        elem = ET.fromstring(block.strip())
    except ET.ParseError:
        return block
    if elem.tag == "channel":
        order_children(elem, XMLTV_CHANNEL_ORDER)
    elif elem.tag == "programme":
        order_children(elem, XMLTV_PROGRAMME_ORDER, XMLTV_PROGRAMME_SINGLE)
        for child in list(elem):
            nested = XMLTV_NESTED_ORDER.get(child.tag)
            if nested:
                order_children(child, nested)
            elif child.tag == "credits":
                order_children(child, XMLTV_CREDITS_ORDER)
            # <rating> sem <value> nao existe no DTD e nao aparece na grade.
            if child.tag in ("rating", "star-rating") and child.find("value") is None:
                elem.remove(child)
    else:
        return block
    ET.indent(elem, space="  ")
    return ET.tostring(elem, encoding="unicode")


def channel_block_from_m3u(cid, info):
    parts = [f'  <channel id="{sax.escape(cid)}">']
    parts.append(f'    <display-name>{sax.escape(info["name"])}</display-name>')
    if info.get("logo"):
        parts.append(f'    <icon src="{sax.escape(info["logo"])}"/>')
    parts.append("  </channel>")
    return "\n".join(parts)


def ensure_icon(channel_block, info):
    """Se o <channel> da fonte veio sem <icon>, usa o logo da playlist."""
    if not channel_block or "<icon" in channel_block or not info.get("logo"):
        return channel_block
    return channel_block.replace(
        "</channel>", f'    <icon src="{sax.escape(info["logo"])}"/>\n</channel>'
    )


def add_candidate(candidates, cid, source, channel_block, blocks, tz=None):
    """Guarda uma opcao de fonte para o canal (so entra se tiver programa).

    tz e o fuso de que a fonte gravou os horarios (None quando a fonte entrega
    o horario ja convertido); o merge usa isso para nao misturar fusos.
    """
    if not blocks:
        return
    for b in blocks:
        BLOCK_SOURCE.setdefault(b, source)
    candidates.setdefault(cid, []).append((source, channel_block, blocks, tz))


def dedupe_icons(channel_block):
    """Deixa um <icon> por src dentro do <channel>.

    Algumas fontes (epgshare01) repetem a mesma imagem, e o TiviMate fica
    mostrando o logo duas vezes na lista de canais.
    """
    if not channel_block:
        return channel_block
    seen = set()
    kept = []
    for line in channel_block.splitlines():
        m = re.search(r'<icon\s+src="([^"]*)"', line)
        if m:
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
        kept.append(line)
    return "\n".join(kept)


def free_spans(blocks, oldest_ok, newest_ok):
    """Intervalos sem nenhum programa dentro da janela de retencao.

    Sao os horarios em que o TiviMate mostraria "sem informacao" para o canal,
    porque nenhum <programme> os cobre. Os limites vem da janela, e nao do
    primeiro e do ultimo programa, para que um dia inteiro sem cobertura ainda
    conte como um vao preenchivel.
    """
    items = sorted((block_start(b), block_stop(b) or block_start(b))
                   for b in blocks if block_start(b) is not None)
    covered = []
    for start, stop in items:
        if covered and start <= covered[-1][1]:
            covered[-1][1] = max(covered[-1][1], stop)
        else:
            covered.append([start, stop])
    spans = []
    cursor = oldest_ok
    for start, stop in covered:
        if start > cursor:
            spans.append((cursor, start))
        cursor = max(cursor, stop)
    if cursor < newest_ok:
        spans.append((cursor, newest_ok))
    return spans


def fill_gaps(blocks, extra, oldest_ok, newest_ok, rounds=8):
    """Preenche os vaos da grade com os programas de outra fonte.

    A regra antiga so aceitava a outra fonte quando ela cobria um dia que ainda
    nao tinha nenhum programa. Um dia pela metade ficava com buraco: e o que
    acontecia com o Telemundo Internacional, que ficava 11 horas sem programa
    porque a outra fonte tinha a noite e a manha enquanto a fonte que dominou
    a mistura tinha o dia. Aqui cada programa da outra fonte entra quando cabe
    inteiro em um vao da grade, e a operacao repete porque um vao longo pode
    receber varios programas seguidos. O que nao cabe (programa que invade a
    grade existente) fica de fora, para nao criar sobreposicao.
    """
    kept = list(dict.fromkeys(blocks))
    for _ in range(rounds):
        spans = free_spans(kept, oldest_ok, newest_ok)
        if not spans:
            break
        added = []
        for b in sort_blocks(extra):
            if b in kept:
                continue
            start, stop = block_start(b), block_stop(b)
            if start is None or stop is None:
                continue
            if any(start >= g_start and stop <= g_stop for g_start, g_stop in spans):
                added.append(b)
        if not added:
            break
        kept.extend(added)
    return kept


def merge_candidates(entries, oldest_ok, newest_ok):
    """Mistura as fontes de um canal no estilo do add-on do kodi (slyguy).

    Entra a fonte que cobre mais programas na janela; as demais so preenchem os
    horarios que ficaram sem grade (fill_gaps). Assim nao ha programa duplicado
    nem sobreposto, que e o que faz o TiviMate exibir a grade embaralhada.

    Cada fonte entra com o fuso de que ela grava (ver wall_clock). Quando duas
    fontes do mesmo canal discordam do fuso, a que dominou a mistura dita o
    fuso e a outra e reescrita: um canal com parte da grade num fuso e parte em
    outro mostra um salto de horas no meio da semana no TiviMate.
    """
    ordered = sorted(entries, key=lambda e: (-len(e[2]), SOURCE_RANK.get(e[0], 99)))
    channel_block = next((e[1] for e in ordered if e[1]), None)
    channel_block = dedupe_icons(channel_block)
    blocks = list(ordered[0][2])
    used = [ordered[0][0]]
    dom_tz = ordered[0][3]
    for src, _chb, extra, tz in ordered[1:]:
        if dom_tz is not None and tz is not None and str(tz) != str(dom_tz):
            extra = [relabel_local_clock(b, dom_tz) for b in extra]
        elif dom_tz is not None and tz is None:
            extra = [restamp_instant(b, dom_tz) for b in extra]
        before = len(blocks)
        blocks = fill_gaps(blocks, extra, oldest_ok, newest_ok)
        if len(blocks) > before:
            used.append(src)
    unique = sort_blocks(dict.fromkeys(blocks))
    return channel_block, drop_overlaps(unique), used


def drop_overlaps(blocks):
    """Remove programas que comecam antes do fim do programa anterior.

    A janela de retencao e montada dia a dia e cada fonte usa o proprio fuso,
    entao o mesmo programa pode aparecer duas vezes com horarios diferentes
    (o reportv grava em -0400 e o iptv-epg em +0000) ou vir repetido dentro
    de uma fonte. Como o TiviMate desenha a grade em ordem cronologica, o
    primeiro que comeca e o que fica; o sobreposto e descartado.
    """
    kept = []
    last_stop = None
    for b in blocks:
        start = block_start(b)
        if start is None:
            continue
        if last_stop is not None and start < last_stop:
            continue
        kept.append(b)
        stop = block_stop(b)
        if stop is not None:
            last_stop = stop
    return kept


def drop_expired(blocks, oldest_ok):
    """Tira o que ja acabou antes da janela de retencao.

    As fontes filtram o passado pelo dia local, nao pelo instante: a primeira
    programacao da Venezuela de ontem, por exemplo, entra como "ontem" e cai
    horas antes do limite da janela. Sao bloques que ja terminaram, entao nao
    servem para nada e so aumentam o arquivo. Quem ainda esta no ar fica,
    porque o TiviMate precisa dele para saber o que esta passando agora.
    """
    kept = []
    for b in blocks:
        stop = block_stop(b)
        if stop is not None and stop <= oldest_ok:
            continue
        kept.append(b)
    return kept


def sort_blocks(blocks):
    """Ordena os <programme> pelo horario real de inicio.

    Algumas fontes (a grade oficial do Al Jazeera, por exemplo) devolvem os
    dias em paginas separadas e nao em ordem cronologica. O TiviMate e o
    add-on do kodi que mistura EPGs esperam os programas em ordem, senao a
    grade exibida sai embaralhada. A comparacao e feita sobre o datetime
    (com o fuso de cada horario), nunca sobre o texto, porque canais de
    paises diferentes usam offsets como -0300, -0500 e +0000.
    """
    return sorted(blocks, key=lambda b: block_start(b) or datetime.max.replace(
        tzinfo=timezone.utc))


def extend_last_programme(blocks, stop_time):
    """Estende o stop do programa mais recente para cobrir a janela de retencao.

    Usado para canais 24/7 (ex.: Pluto TV "Big Brother") cuja fonte so publica
    a programacao ate o fim do dia atual: o programa em exibicao continua ao
    vivo, entao estendemos o stop ate o fim da janela sem inventar titulos.

    O fuso do stop estendido e o mesmo que a fonte usou no start daquele
    programa. Gravar outro fuso (o +0900 do KST, por exemplo) deixa o canal
    com parte da grade em um fuso e parte em outro, que e o salto de horas no
    meio da semana que o TiviMate mostra ao usuario.
    """
    if not blocks:
        return blocks
    latest = None
    latest_idx = -1
    for i, b in enumerate(blocks):
        start = block_start(b)
        if start is None:
            continue
        if latest is None or start > latest:
            latest = start
            latest_idx = i
    if latest_idx < 0:
        return blocks
    offset = re.search(r'start="\d{14}\s+([+-]\d{4})"',
                       blocks[latest_idx])
    stop_str = "{} {}".format(stop_time.strftime("%Y%m%d%H%M%S"),
                              offset.group(1) if offset else "+0000")
    blocks[latest_idx] = re.sub(
        r'stop="\d{8}\d{6}\s+[+-]\d{4}"',
        'stop="{}"'.format(stop_str),
        blocks[latest_idx],
        count=1,
    )
    return blocks


def collect_iptv_epg(candidates, wanted_ids, oldest_ok, newest_ok):
    """Guias XMLTV do iptv-epg.org, uma por pais.

    Alem dos tvg-ids da playlist, o extrator procura os ids do mapa
    IPTVEPG_ALIASES (canais cujo sufixo de pais nao bate com o sinal) e
    remapeia o resultado para o tvg-id da playlist.
    """
    watch_ids = set(wanted_ids) | set(IPTVEPG_ALIASES.values())
    countries = {c for c in (country_of(cid) for cid in watch_ids) if c.isalpha()}
    print(f"    paises necessarios = {sorted(countries)}")
    for country in sorted(countries):
        url = IPTVEPG_URL.format(country)
        print(f"    baixando guia do pais '{country}': {url}")
        try:
            channels, programmes = extract_xmltv(
                url, watch_ids, oldest_ok, newest_ok, retries=2, delay=8,
            )
        except Exception as e:
            print(f"    ERRO ao baixar/ler o guia de '{country}': {e}")
            continue
        for cid, blocks in programmes.items():
            wall, tz = wall_clock(blocks, cid)
            add_candidate(candidates, cid, "iptv-epg", channels.get(cid), wall, tz)
            for dst_id, src_id in IPTVEPG_ALIASES.items():
                if src_id != cid:
                    continue
                wall, tz = wall_clock(
                    [remap_channel_ref(b, src_id, dst_id) for b in blocks], src_id)
                add_candidate(
                    candidates, dst_id, "iptv-epg",
                    remap_channel_block(channels[cid], src_id, dst_id)
                    if cid in channels else None,
                    wall, tz,
                )
                print(f"      {dst_id}: {len(blocks)} programas "
                      f"(iptv-epg, apelido de {src_id})")
        print(f"      {country}: {len(channels)} canais, "
              f"{sum(len(b) for b in programmes.values())} programas")


def collect_reportv(candidates, wanted_ids, oldest_ok, newest_ok):
    """Grade oficial do reportv.com.ar para os canais da playlist que ele cobre."""
    site_ids = reportv_site_ids(wanted_ids)
    targets = [(cid, site_ids[cid]) for cid in wanted_ids if cid in site_ids]
    if not targets:
        return
    first_day = max(oldest_ok.astimezone(CARACAS).date(),
                    datetime.now(CARACAS).date() - timedelta(days=1))
    last_day = min(newest_ok.astimezone(CARACAS).date(),
                   datetime.now(CARACAS).date() + timedelta(days=REPORTV_DAYS - 1))
    days = []
    day = first_day
    while day <= last_day:
        days.append(day)
        day += timedelta(days=1)
    print(f"    {len(targets)} canais, dias {[d.isoformat() for d in days]}")

    def work(item):
        cid, sid = item
        return cid, fetch_reportv(cid, sid, days)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for cid, blocks in pool.map(work, targets):
            add_candidate(candidates, cid, "reportv", None, blocks)
            print(f"      {cid}: {len(blocks)} programas (reportv.com.ar)")


def collect_epgshare01(candidates, wanted_ids, epg_files, oldest_ok, newest_ok):
    """Arquivos do epgshare01, escolhidos pelo pais do sufixo do tvg-id."""
    files_cache = {}
    alias_ids = {src_id for pairs in ALIASES.values() for _, src_id in pairs}
    watch_ids = set(wanted_ids) | alias_ids

    def load(filename):
        if filename not in files_cache:
            print(f"    baixando {filename}")
            files_cache[filename] = extract_xmltv(
                epgshare01_url(filename), watch_ids, oldest_ok, newest_ok,
            )
        return files_cache[filename]

    for cid in wanted_ids:
        filenames = epgshare01_files_for(cid, epg_files)
        if not filenames:
            print(f"    {cid}: sem fonte epgshare01 para o pais '{country_of(cid)}'")
        for filename in filenames:
            try:
                channels, programmes = load(filename)
            except Exception as e:
                print(f"    ERRO ao baixar/ler {filename}: {e}")
                continue
            blocks = programmes.get(cid)
            if blocks:
                wall, tz = wall_clock(blocks, cid)
                add_candidate(candidates, cid, "epgshare01", channels.get(cid),
                              wall, tz)
                break
        else:
            # O tvg-id da playlist nao existe na fonte; tenta os apelidos.
            for key, src_id in ALIASES.get(cid, []):
                for filename in epg_files.get(key, []):
                    try:
                        channels, programmes = load(filename)
                    except Exception as e:
                        print(f"    ERRO ao baixar/ler {filename}: {e}")
                        continue
                    blocks = programmes.get(src_id)
                    if blocks:
                        wall, tz = wall_clock(
                            [remap_channel_ref(b, src_id, cid) for b in blocks],
                            src_id)
                        add_candidate(
                            candidates, cid, "epgshare01",
                            remap_channel_block(channels[src_id], src_id, cid)
                            if src_id in channels else None,
                            wall, tz,
                        )
                        break
                else:
                    continue
                break


def epgshare01_url(filename):
    """URL com cache-busting: o Cloudflare do epgshare01 costuma servir 404
    em cache (max-age=4h) durante a regeneracao diaria dos arquivos; um
    parametro unico na query força busca na origem."""
    return "{}?nocache={}".format(EPGSHARE01_URL.format(filename), int(time.time()))


def collect_globo(candidates, wanted_ids):
    """GLOBOEPG.xml.gz local como fonte complementar."""
    if not os.path.exists(GLOBO_EPG):
        return
    try:
        print(f"    Lendo EPG local: {GLOBO_EPG}")
        with gzip.open(GLOBO_EPG, "rt", encoding="utf-8") as f:
            globo = f.read()
    except Exception as e:
        print(f"    ERRO: {e}")
        return
    for cid in wanted_ids:
        pat = re.compile(
            rf'<programme\s+[^>]*channel="{re.escape(cid)}"[^>]*>.*?</programme>',
            re.DOTALL,
        )
        blocks = pat.findall(globo)
        if blocks:
            add_candidate(candidates, cid, "globo", None, blocks)
            print(f"      {cid}: {len(blocks)} programas (Globo)")


def collect_koryo(candidates, channels, oldest_ok, newest_ok):
    """KCTV: KORYO.TV ao vivo, Wayback Machine ou Juche TV."""
    koryo_id = koryo_target_id(channels)
    if not koryo_id:
        print("  KCTV nao esta na playlist; pulando KORYO.TV.")
        return
    print(f"  KCTV detectado: {koryo_id}")
    print(f"  Baixando KORYO.TV: {KORYO_EPG_URL}")
    try:
        events, source, _live = fetch_koryo()
        print(f"    Fonte: {source} ({len(events)} eventos)")
        blocks = []
        for ev in events:
            if ev.get("channel") != "kctv":
                continue
            try:
                start = datetime.fromisoformat(ev["startUtc"]).astimezone(PYONGYANG)
            except Exception:
                continue
            if start < oldest_ok or start > newest_ok:
                continue
            blocks.append(build_programme(ev, koryo_id))
        add_candidate(candidates, koryo_id, "koryo", None, blocks)
        print(f"    Programas na janela ({oldest_ok:%Y-%m-%d} a {newest_ok:%Y-%m-%d}): {len(blocks)}")
    except Exception as e:
        print(f"    ERRO: {e}")
    for label, fetcher in (("GitHub Bloxyplay", fetch_juche_github),
                           ("Juche TV", fetch_juche)):
        if candidates.get(koryo_id):
            break
        try:
            blocks = fetcher(koryo_id, oldest_ok, newest_ok)
            add_candidate(candidates, koryo_id, "koryo", None, blocks)
            print(f"    fallback {label}: {len(blocks)} programas")
        except Exception as e:
            print(f"    ERRO no fallback {label}: {e}")


def collect_aljazeera(candidates, wanted_ids, oldest_ok, newest_ok):
    """Grade oficial da Al Jazeera Arabic; epgshare01 so se ela falhar."""
    if ALJAZEERA_AR_ID not in wanted_ids:
        return
    print(f"    {ALJAZEERA_AR_ID}: grade oficial (GraphQL aljazeera.com)")
    try:
        blocks = fetch_aljazeera_arabic(ALJAZEERA_AR_ID, oldest_ok, newest_ok)
    except Exception as e:
        print(f"      ERRO na fonte oficial ({e}); tentando epgshare01")
        blocks = []
    if blocks:
        add_candidate(candidates, ALJAZEERA_AR_ID, "aljazeera", None, blocks)
        print(f"      {ALJAZEERA_AR_ID}: {len(blocks)} programas (aljazeera.com)")


def collect_imjhnz(candidates, wanted_ids, oldest_ok, newest_ok):
    """Guias do i.mjh.nz (Pluto TV, Roku, ...).

    Os canais usam um id interno na fonte, entao tudo e remapeado para o
    tvg-id da playlist antes de entrar no guia.
    """
    # Agrupa por feed: um download serve a todos os canais daquela plataforma.
    feeds = {}
    for cid, (feed, src_id) in IMJHNZ_CHANNELS.items():
        feeds.setdefault(feed, []).append((cid, src_id))
    for feed, entries in feeds.items():
        url = "{}/{}.xml.gz".format(IMJHNZ_BASE, feed)
        print(f"    {feed}: {url}")
        wanted = [src_id for _cid, src_id in entries if _cid in wanted_ids]
        if not wanted:
            continue
        try:
            src_channels, src_programmes = extract_xmltv(
                url, wanted, oldest_ok, newest_ok, retries=3, delay=10,
            )
        except Exception as e:
            print(f"    ERRO ao baixar/ler {url}: {e}")
            continue
        for cid, src_id in entries:
            if cid not in wanted_ids or src_id not in src_programmes:
                continue
            channels, programmes = remap_imjhnz(src_channels, src_programmes,
                                                src_id, cid)
            blocks = programmes.get(cid, [])
            if blocks and cid == PLUTO_BB_ID:
                # O Big Brother e 24/7 e a fonte so publica ate o fim do dia;
                # o programa em exibicao continua ao vivo.
                blocks = extend_last_programme(blocks, newest_ok)
            add_candidate(candidates, cid, "imjhnz", channels.get(cid), blocks)
            print(f"      {cid}: {len(blocks)} programas (i.mjh.nz)")


def main():
    now = datetime.now(timezone.utc)
    oldest_ok = now - KEEP_BEFORE
    newest_ok = now + KEEP_AFTER
    print(f"Janela de retencao (UTC): {oldest_ok:%Y-%m-%d %H:%M} .. {newest_ok:%Y-%m-%d %H:%M}")

    print("=== ETAPA 1: Baixar M3U ===")
    m3u_data = None
    if os.path.exists("NEWSWORLDNOVOS.m3u"):
        with open("NEWSWORLDNOVOS.m3u", "r", encoding="utf-8") as f:
            m3u_data = f.read()
        if parse_m3u(m3u_data):
            print("  M3U lido do arquivo local: NEWSWORLDNOVOS.m3u")
    if not m3u_data or not parse_m3u(m3u_data):
        try:
            m3u_data = http_get(M3U_URL).decode("utf-8", errors="ignore")
            print(f"  M3U baixado de: {M3U_URL}")
        except Exception as e:
            print(f"  ERRO ao baixar M3U remoto ({e})")
            if not m3u_data:
                print("  Nenhum M3U disponivel!")
                return
    channels = parse_m3u(m3u_data)
    wanted_ids = list(channels.keys())
    wanted_set = set(wanted_ids)
    print(f"  Canais na playlist: {len(wanted_ids)}")

    print("\n=== ETAPA 2: Baixar EPGs ===")
    candidates = {}

    collect_koryo(candidates, channels, oldest_ok, newest_ok)
    collect_aljazeera(candidates, wanted_set, oldest_ok, newest_ok)
    collect_imjhnz(candidates, wanted_set, oldest_ok, newest_ok)
    collect_reportv(candidates, wanted_set, oldest_ok, newest_ok)
    collect_iptv_epg(candidates, wanted_set, oldest_ok, newest_ok)

    try:
        epg_files = list_epgshare01_files()
    except Exception as e:
        print(f"  ERRO ao listar indice do epgshare01: {e}")
        epg_files = {}
    collect_epgshare01(candidates, wanted_set, epg_files, oldest_ok, newest_ok)
    collect_globo(candidates, wanted_set)

    print("\n=== ETAPA 3: Montar EPGFULL.xml.gz ===")
    xml_parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<tv generator-info-name="JCTV EPG Generator" '
                 'generator-info-url="https://github.com/gratinomaster/JCTV">']
    channel_parts = []
    programme_parts = []
    final_progs = {}
    for cid in wanted_ids:
        entries = candidates.get(cid)
        if entries:
            channel_xml, blocks, used = merge_candidates(entries, oldest_ok, newest_ok)
            blocks = drop_expired(blocks, oldest_ok)
            final_progs[cid] = blocks
            print(f"    {cid}: {len(blocks)} programas ({' + '.join(used)})")
        else:
            channel_xml, blocks = None, []
            print(f"    {cid}: SEM PROGRAMACAO em nenhuma fonte")
        channel_parts.append(normalize_block(
            ensure_icon(channel_xml, channels[cid])
            or channel_block_from_m3u(cid, channels[cid])))
        # O DTD do XMLTV pede todos os <channel> antes dos <programme>, e cada
        # programa dentro do padrao, para o guia nao ser recusado por validador
        # estrito. A ordem cronologica por canal ja vem de sort_blocks.
        programme_parts.extend(normalize_block(b) for b in blocks)
    xml_parts.extend(channel_parts)
    xml_parts.extend(programme_parts)
    xml_parts.append("</tv>")
    full_xml = "\n".join(xml_parts) + "\n"

    with gzip.open(OUTPUT, "wt", encoding="utf-8") as f:
        f.write(full_xml)
    print(f"  Arquivo gravado: {OUTPUT} ({os.path.getsize(OUTPUT):,} bytes)")

    print("\n=== ETAPA 4: Validar ===")
    root = ET.fromstring(full_xml)
    defined = {ch.get("id") for ch in root.findall("channel")}
    programmes = root.findall("programme")
    print("  XML valido (ElementTree OK)")
    print(f"  Canais: {len(defined)} (na playlist: {len(wanted_ids)})")
    print(f"  Programas: {len(programmes)}")

    orphan = sorted({p.get("channel") for p in programmes if p.get("channel") not in defined})
    missing = [cid for cid in wanted_ids if cid not in defined]
    extra = sorted(defined - wanted_set)
    print(f"  Programas sem canal correspondente: {len(orphan)}")
    print(f"  Canais do M3U ausentes no guia: {len(missing)}")
    print(f"  Canais no guia que NAO estao no M3U: {len(extra)}"
          + (f" -> {extra}" if extra else ""))

    # TiviMate e os add-ons do Kodi casam canal e programa pelo tvg-id; um
    # unico <programme> por vez e o horario em ordem evitam guia embaralhado.
    unsorted_ct = 0
    for cid in wanted_ids:
        starts = [block_start(b) for b in final_progs.get(cid, [])]
        starts = [s for s in starts if s]
        if starts != sorted(starts):
            unsorted_ct += 1
    print(f"  Canais com programas fora de ordem: {unsorted_ct}")

    # O TiviMate converte cada programa para o fuso do aparelho usando o
    # atributo do horario. Fuso errado = guia adiantado, entao confere se os
    # digitos que entraram continuam batendo com o pais do canal. A conferencia
    # vale para as fontes de horario de parede (os digitos sao a hora local do
    # canal); as fontes de instante absoluto ja vem em UTC, que e o horario
    # certo para qualquer fuso do aparelho, entao entram fora da conta.
    wrong_tz = []
    utc_blocks = 0
    for cid in wanted_ids:
        tz = channel_tz(cid)
        if tz is None:
            continue
        blocks = final_progs.get(cid) or []
        if not blocks:
            continue
        ok = 0
        for b in blocks:
            start = block_start(b)
            stop = block_stop(b)
            if start is None or stop is None:
                continue
            if BLOCK_SOURCE.get(b) not in WALL_CLOCK_SOURCES:
                utc_blocks += 1
                continue
            digits_s = start.strftime("%Y%m%d%H%M%S")
            digits_e = stop.strftime("%Y%m%d%H%M%S")
            naively_s = datetime.strptime(digits_s, "%Y%m%d%H%M%S")
            naively_e = datetime.strptime(digits_e, "%Y%m%d%H%M%S")
            if (start.utcoffset() == naively_s.replace(tzinfo=tz).utcoffset()
                    and stop.utcoffset() == naively_e.replace(tzinfo=tz).utcoffset()):
                ok += 1
        if ok < len(blocks) - sum(
                1 for b in blocks if BLOCK_SOURCE.get(b) not in WALL_CLOCK_SOURCES):
            wrong_tz.append((cid, len(blocks) - ok, len(blocks)))
    print(f"  Programas de fonte UTC (ja convertem para o fuso do aparelho): "
          f"{utc_blocks}")
    print(f"  Programas com fuso fora do pais do canal: "
          f"{sum(w[1] for w in wrong_tz)}"
          + (f" -> {[w[0] for w in wrong_tz]}" if wrong_tz else ""))

    today = now.date()
    tomorrow = today + timedelta(days=1)

    def day_overlaps(date_s):
        day_start = datetime.strptime(date_s, "%Y%m%d").replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = 0
        for p in programmes:
            s = parse_xmltv_time(p.get("start", ""))
            e = parse_xmltv_time(p.get("stop", ""))
            if s is None:
                continue
            if e is None or e <= s:
                e = s + timedelta(hours=1)
            if s < day_end and e > day_start:
                count += 1
        return count

    def channels_with(date_s):
        day_start = datetime.strptime(date_s, "%Y%m%d").replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        got = set()
        for p in programmes:
            s = parse_xmltv_time(p.get("start", ""))
            e = parse_xmltv_time(p.get("stop", ""))
            if s is None:
                continue
            if e is None or e <= s:
                e = s + timedelta(hours=1)
            if s < day_end and e > day_start:
                got.add(p.get("channel"))
        return got

    today_s, tomorrow_s = today.strftime("%Y%m%d"), tomorrow.strftime("%Y%m%d")
    today_ct = day_overlaps(today_s)
    tomorrow_ct = day_overlaps(tomorrow_s)
    with_today = channels_with(today_s)
    with_tomorrow = channels_with(tomorrow_s)
    print(f"  Programas de HOJE   ({today_s}, UTC): {today_ct} em {len(with_today)} canais")
    print(f"  Programas de AMANHA ({tomorrow_s}, UTC): {tomorrow_ct} em {len(with_tomorrow)} canais")
    print(f"  Teste hoje: {'OK' if today_ct else 'FALHOU'}")
    print(f"  Teste amanha: {'OK' if tomorrow_ct else 'FALHOU'}")

    empty = [cid for cid in wanted_ids if not final_progs.get(cid)]
    covered = len(wanted_ids) - len(empty)
    print(f"  Canais com programacao: {covered}/{len(wanted_ids)}")
    if empty:
        print(f"  Canais sem nenhuma fonte de EPG ({len(empty)}): {empty}")

    print("\n=== CONCLUIDO ===")


if __name__ == "__main__":
    main()
