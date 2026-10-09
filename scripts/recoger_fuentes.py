#!/usr/bin/env python3
"""Recoge cada mañana los titulares de muchos medios, fuentes oficiales y tendencias de búsqueda.

Lo ejecuta GitHub Actions (.github/workflows/fuentes.yml), que sí tiene acceso libre a internet.
Escribe, con la fecha de Madrid:
  datos/titulares/AAAA-MM-DD.json   titulares recientes de cada medio y fuente oficial
  datos/tendencias/AAAA-MM-DD.json  búsquedas en auge de Google por país y lo más leído en Wikipedia
y borra los archivos de más de DIAS_GUARDAR días. Solo usa la biblioteca estándar de Python.
"""
import html, json, os, re, sys, time, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MADRID = ZoneInfo("Europe/Madrid")
UA = "TheDailyIvan/1.0 (+https://ivandiezb.github.io/the-daily-ivan/; resumen de prensa personal)"
POR_FUENTE = 20
DIAS_GUARDAR = 15

# grupo: espana | economia | internacional | oficial · linea: orientación editorial habitual (solo para equilibrar)
FUENTES = [
    # España: generalistas de distintas líneas editoriales, agencias y servicio público
    ("elpais", "El País", "espana", "centroizquierda", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    ("eldiario", "elDiario.es", "espana", "izquierda", "https://www.eldiario.es/rss/"),
    ("publico", "Público", "espana", "izquierda", ["https://www.publico.es/rss", "https://www.publico.es/feed/", "https://www.publico.es/rss/portada"]),
    ("infolibre", "infoLibre", "espana", "izquierda", ["https://www.infolibre.es/rss", "https://www.infolibre.es/rss/"]),
    ("elmundo", "El Mundo", "espana", "centroderecha", "https://e00-elmundo.uecdn.es/rss/portada.xml"),
    ("abc", "ABC", "espana", "derecha", "https://www.abc.es/rss/2.0/portada/"),
    ("larazon", "La Razón", "espana", "derecha", ["https://www.larazon.es/rss/portada.xml", "https://www.larazon.es/arc/outboundfeeds/rss/?outputType=xml"]),
    ("okdiario", "OKDiario", "espana", "derecha", ["https://okdiario.com/feed", "https://okdiario.com/feed/"]),
    ("elespanol", "El Español", "espana", "centroderecha", "https://www.elespanol.com/rss/"),
    ("elconfidencial", "El Confidencial", "espana", "centro", "https://rss.elconfidencial.com/espana/"),
    ("lavanguardia", "La Vanguardia", "espana", "centro", "https://www.lavanguardia.com/rss/home.xml"),
        ("20minutos", "20minutos", "espana", "centro", "https://www.20minutos.es/rss/"),
    ("rtve", "RTVE", "espana", "publico", "https://api2.rtve.es/rss/temas_noticias.xml"),
    ("europapress", "Europa Press", "espana", "agencia", "https://www.europapress.es/rss/rss.aspx"),
    ("libertad", "Libertad Digital", "espana", "derecha", "https://www.libertaddigital.com/rss/"),
    ("newtral", "Newtral", "espana", "verificacion", "https://www.newtral.es/feed/"),
    ("telemadrid", "Telemadrid", "espana", "publico", ["https://www.telemadrid.es/rss/portada.xml", "https://www.telemadrid.es/feed/"]),
    # Economía y mercados
    ("expansion", "Expansión", "economia", "economica", "https://e00-expansion.uecdn.es/rss/portada.xml"),
    ("cincodias", "Cinco Días", "economia", "economica", "https://feeds.elpais.com/mrss-s/pages/ep/site/cincodias.elpais.com/portada"),
        ("cnbc", "CNBC", "economia", "economica", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("wsj", "Wall Street Journal (mundo)", "economia", "economica", "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    # Internacional
    ("bbc", "BBC News (mundo)", "internacional", "publico", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("bbcmundo", "BBC Mundo", "internacional", "publico", "https://feeds.bbci.co.uk/mundo/rss.xml"),
    ("guardian", "The Guardian (mundo)", "internacional", "centroizquierda", "https://www.theguardian.com/world/rss"),
    ("nyt", "The New York Times (mundo)", "internacional", "centroizquierda", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("lemonde", "Le Monde", "internacional", "centroizquierda", "https://www.lemonde.fr/rss/une.xml"),
    ("dw", "DW en español", "internacional", "publico", "https://rss.dw.com/xml/rss-sp-all"),
    ("france24", "France 24 en español", "internacional", "publico", "https://www.france24.com/es/rss"),
    ("euronews", "Euronews en español", "internacional", "centro", "https://es.euronews.com/rss"),
    ("aljazeera", "Al Jazeera", "internacional", "centro", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("politico", "Politico Europe", "internacional", "centro", "https://www.politico.eu/feed/"),
    ("npr", "NPR (mundo)", "internacional", "publico", "https://feeds.npr.org/1004/rss.xml"),
    # Fuentes oficiales y primarias
    ("bde", "Banco de España (noticias)", "oficial", "oficial", "https://www.bde.es/wbe/es/inicio/rss/rss-noticias/"),
    ("bce", "Banco Central Europeo (prensa)", "oficial", "oficial", "https://www.ecb.europa.eu/rss/press.html"),
    ("fed", "Reserva Federal (prensa)", "oficial", "oficial", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("moncloa", "La Moncloa (notas de prensa)", "oficial", "oficial", "https://www.lamoncloa.gob.es/Paginas/rss.aspx"),
]
PAISES_TENDENCIAS = ["ES", "US", "GB", "FR", "DE", "IT", "PT", "MX", "AR", "BR", "IN", "JP"]
WIKIS = ["es", "en"]
EXCLUIR_WIKI = re.compile(r"^(Main_Page|Portada|Wikipedia:|Especial:|Special:|Archivo:|File:|Ayuda:|Help:|Portal:|"
                          r"Categoría:|Category:|Usuario:|User:|Anexo:Portada$|-$)", re.I)


def get(url, accept=None, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept or "*/*",
                                                       "Accept-Language": "es-ES,es;q=0.9,en;q=0.6"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.read()
        except Exception as ex:
            last = ex
            time.sleep(2 * (i + 1))
    raise last


def local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def texto(el):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", "".join(el.itertext()) if el is not None else ""))).strip()


def hijo(el, *nombres):
    for c in el:
        if local(c.tag) in nombres:
            return c
    return None


def fecha_iso(s):
    s = (s or "").strip()
    if not s:
        return ""
    for f in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = f(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(MADRID).isoformat(timespec="minutes")
        except Exception:
            pass
    return s[:25]


def parsear(datos):
    try:
        return ET.fromstring(datos)
    except ET.ParseError:
        # canales mal formados: «&» sueltos y caracteres de control
        t = datos.decode("utf-8", "replace")
        t = re.sub(r"&(?!#?\w+;)", "&amp;", t)
        t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
        t = re.sub(r"^<\?xml[^>]*\?>", "", t.lstrip())
        return ET.fromstring(t)


def leer_feed(fuente):
    fid, nombre, grupo, linea, urls = fuente
    urls = urls if isinstance(urls, list) else [urls]
    out = {"id": fid, "nombre": nombre, "grupo": grupo, "linea": linea, "url": urls[0], "ok": False, "items": []}
    errores = []
    for url in urls:
        try:
            raiz = parsear(get(url, "application/rss+xml, application/atom+xml, application/xml, text/xml"))
            out["url"] = url
            break
        except Exception as ex:
            errores.append(f"{type(ex).__name__}: {ex}"[:120])
    else:
        out["error"] = " | ".join(errores)[:300]
        return out
    try:
        entradas = [e for e in raiz.iter() if local(e.tag) in ("item", "entry")]
        for e in entradas[:POR_FUENTE]:
            t = texto(hijo(e, "title"))
            link_el = hijo(e, "link")
            link = (link_el.get("href") or texto(link_el)) if link_el is not None else ""
            fecha = fecha_iso(texto(hijo(e, "pubdate", "published", "updated", "date")))
            resumen = texto(hijo(e, "description", "summary"))[:220]
            if t:
                out["items"].append({"t": t, "u": link, "fecha": fecha, "resumen": resumen})
        out["ok"] = bool(out["items"])
        if not out["ok"]:
            out["error"] = "sin entradas"
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def leer_boe(hoy):
    out = {"id": "boe", "nombre": "BOE (sumario del día)", "grupo": "oficial", "linea": "oficial",
           "url": f"https://www.boe.es/datosabiertos/api/boe/sumario/{hoy:%Y%m%d}", "ok": False, "items": []}
    try:
        d = json.loads(get(out["url"], "application/json"))
        sumario = d.get("data", {}).get("sumario", {})
        diarios = sumario.get("diario", [])
        diarios = diarios if isinstance(diarios, list) else [diarios]

        def lista(x):
            return x if isinstance(x, list) else ([x] if x else [])
        for diario in diarios:
            for sec in lista(diario.get("seccion")):
                if str(sec.get("codigo")) not in ("1", "2A", "3"):
                    continue  # disposiciones generales, nombramientos y otras disposiciones
                for dep in lista(sec.get("departamento")):
                    grupos = lista(dep.get("epigrafe")) or [dep]
                    for g in grupos:
                        for it in lista(g.get("item")):
                            out["items"].append({"t": f"{dep.get('nombre', '')}: {it.get('titulo', '')}"[:400],
                                                 "u": it.get("url_html") or "", "fecha": hoy.isoformat(),
                                                 "resumen": f"Sección {sec.get('codigo')} · {g.get('nombre', '')}"[:220]})
        out["items"] = out["items"][:60]
        out["ok"] = bool(out["items"])
        if not out["ok"]:
            out["error"] = "sin disposiciones (puede no haber BOE hoy)"
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def numero_trafico(s):
    s = (s or "").replace("+", "").replace(".", "").replace(",", "").strip().upper()
    m = re.match(r"(\d+)\s*([KM]?)", s)
    if not m:
        return 0
    return int(m.group(1)) * {"": 1, "K": 1000, "M": 1000000}[m.group(2)]


def leer_trends(geo):
    url = f"https://trends.google.com/trending/rss?geo={geo}"
    out = {"geo": geo, "url": url, "ok": False, "items": []}
    try:
        raiz = ET.fromstring(get(url, "application/rss+xml, application/xml"))
        for e in [x for x in raiz.iter() if local(x.tag) == "item"]:
            item = {"t": texto(hijo(e, "title")), "trafico": texto(hijo(e, "approx_traffic")),
                    "fecha": fecha_iso(texto(hijo(e, "pubdate"))), "noticias": []}
            item["n"] = numero_trafico(item["trafico"])
            for c in e:
                if local(c.tag) == "news_item":
                    item["noticias"].append({"t": texto(hijo(c, "news_item_title")), "u": texto(hijo(c, "news_item_url")),
                                             "s": texto(hijo(c, "news_item_source"))})
            if item["t"]:
                out["items"].append(item)
        out["ok"] = bool(out["items"])
        if not out["ok"]:
            out["error"] = "sin entradas"
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def leer_wiki(lang, hoy):
    """Lo más visto en Wikipedia el día anterior. Descarta lo que casi no se ve desde el móvil: suele ser
    tráfico automático (bots), no interés real de lectores."""
    out = {"lang": lang, "ok": False, "items": []}
    base = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{lang}.wikipedia/{acc}/{dia:%Y/%m/%d}"
    for atras in (1, 2):
        dia = hoy - timedelta(days=atras)
        url = base.format(lang=lang, acc="all-access", dia=dia)
        try:
            arts = json.loads(get(url, "application/json"))["items"][0]["articles"]
            movil = {a["article"]: a["views"] for a in
                     json.loads(get(base.format(lang=lang, acc="mobile-web", dia=dia), "application/json"))["items"][0]["articles"]}
            items, descartados = [], []
            for a in arts:
                t = a["article"]
                if EXCLUIR_WIKI.search(t):
                    continue
                cuota = movil.get(t, 0) / a["views"] if a["views"] else 0
                if cuota < 0.15:
                    descartados.append(t.replace("_", " "))
                    continue
                items.append({"t": t.replace("_", " "), "v": a["views"], "movil": round(cuota, 2),
                              "u": f"https://{lang}.wikipedia.org/wiki/{t}"})
                if len(items) >= 25:
                    break
            out["descartados_bots"] = descartados[:15]
            out.update(ok=bool(items), dia=dia.isoformat(), url=url, items=items)
            return out
        except Exception as ex:
            out["error"] = f"{dia}: {type(ex).__name__}: {ex}"[:200]
    return out


def limpiar(carpeta, hoy):
    if not os.path.isdir(carpeta):
        return
    for f in os.listdir(carpeta):
        m = re.match(r"(\d{4}-\d{2}-\d{2})\.json$", f)
        if m and (hoy - datetime.strptime(m.group(1), "%Y-%m-%d").date()).days > DIAS_GUARDAR:
            os.remove(os.path.join(carpeta, f))


def main():
    ahora = datetime.now(MADRID)
    hoy = ahora.date()
    with ThreadPoolExecutor(max_workers=10) as ex:
        feeds = list(ex.map(leer_feed, FUENTES))
        trends = list(ex.map(leer_trends, PAISES_TENDENCIAS))
        wikis = list(ex.map(lambda l: leer_wiki(l, hoy), WIKIS))
    feeds.append(leer_boe(hoy))

    titulares = {"fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}",
                 "fuentes_ok": sum(1 for f in feeds if f["ok"]), "fuentes_total": len(feeds), "fuentes": feeds}
    tendencias = {"fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}",
                  "google": {t["geo"]: t for t in trends}, "wikipedia": {w["lang"]: w for w in wikis}}
    for carpeta, datos in (("titulares", titulares), ("tendencias", tendencias)):
        d = os.path.join(RAIZ, "datos", carpeta)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{hoy.isoformat()}.json"), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=0)
        limpiar(d, hoy)

    print(f"Titulares: {titulares['fuentes_ok']}/{titulares['fuentes_total']} fuentes con datos")
    for f in feeds:
        print(f"  {'OK ' if f['ok'] else 'ERR'} {f['nombre']}: {len(f['items'])} {f.get('error', '')}")
    print("Tendencias Google: " + ", ".join(f"{t['geo']} {len(t['items'])}" + ("" if t["ok"] else f" ({t.get('error')})") for t in trends))
    print("Wikipedia: " + ", ".join(f"{w['lang']} {len(w['items'])} ({w.get('dia', w.get('error'))})" for w in wikis))
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Fuentes {hoy} {ahora:%H:%M}\n\n")
            f.write(f"- Titulares: {titulares['fuentes_ok']} de {titulares['fuentes_total']} fuentes\n")
            f.write("- Sin datos: " + (", ".join(x["nombre"] for x in feeds if not x["ok"]) or "ninguna") + "\n")
            f.write("- Google Trends: " + ", ".join(f"{t['geo']} {len(t['items'])}" for t in trends) + "\n")
    # falla (en rojo) solo si casi nada ha funcionado
    return 0 if titulares["fuentes_ok"] >= 8 else 1


if __name__ == "__main__":
    sys.exit(main())
