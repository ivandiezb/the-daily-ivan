#!/usr/bin/env python3
"""Recoge cada mañana los titulares de las fuentes del catálogo, el radar amplio y las tendencias de búsqueda.

Lo ejecuta GitHub Actions (.github/workflows/fuentes.yml), que sí tiene acceso libre a internet. Las fuentes, sus
tipos y los criterios de selección están en fuentes_catalogo.py. Escribe, con la fecha de Madrid, en DATOS_DIR
(por defecto datos/; en GitHub, la rama «datos», que no se publica en la web):
  titulares/AAAA-MM-DD.json   titulares recientes de cada fuente del catálogo y del radar de Google News
  tendencias/AAAA-MM-DD.json  búsquedas en auge de Google por país y lo más leído en Wikipedia
y borra los archivos de más de DIAS_GUARDAR días. Solo usa la biblioteca estándar de Python.
"""
import html, json, math, os, re, sys, threading, time, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fuentes_catalogo import BOE, FUENTES, RADAR  # noqa: E402

MADRID = ZoneInfo("Europe/Madrid")
UA = "TheDailyIvan/1.0 (+https://ivandiezb.github.io/the-daily-ivan/; resumen de prensa personal)"
POR_FUENTE = 20       # titulares que se guardan por fuente (salvo «max» en el catálogo)
HORAS = 36            # antigüedad máxima por defecto (salvo «horas» en el catálogo)
POR_RADAR = 40
DIAS_GUARDAR = 15
DATOS = os.environ.get("DATOS_DIR") or os.path.join(RAIZ, "datos")
GOOGLE = threading.Semaphore(3)  # pocas peticiones a la vez a Google News
GN_IDIOMA = {"es": ("es", "ES"), "en": ("en-US", "US"), "fr": ("fr", "FR"), "de": ("de", "DE"), "it": ("it", "IT"),
             "pt": ("pt-BR", "BR")}
BASURA = re.compile(r"^(untitled|welcome to|observación:|hoy y últimos días|predicción|oposiciones|auxiliares de|"
                    r"\d+ (casas|pisos|chalets)|página no encontrada|404)", re.I)
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
            if "news.google.com" in url:
                with GOOGLE:
                    with urllib.request.urlopen(req, timeout=25) as r:
                        datos = r.read()
                    time.sleep(0.5)
                return datos
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


def url_google(site, idioma, horas):
    hl, gl = GN_IDIOMA.get(idioma, ("es", "ES"))
    q = quote(f"site:{site} when:{max(1, math.ceil(horas / 24))}d")
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"


def entradas(raiz):
    """Entradas de un RSS/Atom: título, enlace, fecha, medio (en Google News) y el XML de la descripción."""
    out = []
    for e in [x for x in raiz.iter() if local(x.tag) in ("item", "entry")]:
        t = texto(hijo(e, "title"))
        link_el = hijo(e, "link")
        link = (link_el.get("href") or texto(link_el)) if link_el is not None else ""
        src = hijo(e, "source")
        medio = texto(src) if src is not None else ""
        if medio and t.endswith(" - " + medio):
            t = t[: -len(medio) - 3].strip()
        desc = hijo(e, "description", "summary")
        out.append({"t": t, "u": link, "fecha": fecha_iso(texto(hijo(e, "pubdate", "published", "updated", "date"))),
                    "medio": medio, "web": (src.get("url") or "") if src is not None else "",
                    "_desc": (desc.text or "") if desc is not None else ""})
    return out


def recientes(items, horas, ahora, maximo):
    """Quita títulos vacíos o de relleno y lo antiguo; ordena del más reciente al más antiguo."""
    limite = ahora - timedelta(hours=horas)
    vistos, out = set(), []
    for it in items:
        if not it["t"] or BASURA.search(it["t"]) or it["t"].lower() in vistos:
            continue
        try:
            if it["fecha"] and datetime.fromisoformat(it["fecha"]) < limite:
                continue
        except ValueError:
            pass
        vistos.add(it["t"].lower())
        out.append(it)
    out.sort(key=lambda i: i["fecha"] or "", reverse=True)
    return out[:maximo]


def leer_feed(fuente, ahora):
    horas = fuente.get("horas") or HORAS
    urls = list(fuente["url"]) if isinstance(fuente.get("url"), list) else ([fuente["url"]] if fuente.get("url") else [])
    if fuente.get("site"):
        urls.append(url_google(fuente["site"], fuente.get("idioma", "es"), horas))
    out = {k: fuente.get(k) for k in ("id", "nombre", "medio", "tipo", "bloques", "linea", "dominio", "idioma")}
    out.update(url=urls[0], via="", ok=False, items=[])
    errores = []
    for url in urls:  # el RSS propio primero; si falla o no trae nada reciente, la búsqueda de Google News
        try:
            brutos = entradas(parsear(get(url, "application/rss+xml, application/atom+xml, application/xml, text/xml")))
        except Exception as ex:
            errores.append(f"{type(ex).__name__}: {ex}"[:120])
            continue
        items = recientes(brutos, horas, ahora, fuente.get("max") or POR_FUENTE)
        if items:
            out.update(url=url, via="google-news" if "news.google.com" in url else "rss", ok=True,
                       items=[{"t": i["t"], "u": i["u"], "fecha": i["fecha"]} for i in items])
            return out
        errores.append("sin entradas recientes" if brutos else "sin entradas")
    out["error"] = " | ".join(errores)[:300]
    return out


RELACIONADA = re.compile(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>(?:&nbsp;|\s)*<font[^>]*>(.*?)</font>', re.S)


def leer_radar(r, ahora):
    """Portadas de Google News: cada historia trae varios medios que la cuentan (la agrupación es de Google)."""
    out = {"id": r["id"], "nombre": r["nombre"], "url": r["url"], "ok": False, "items": []}
    try:
        brutos = entradas(parsear(get(r["url"], "application/rss+xml, application/xml")))
        for i in recientes(brutos, 48, ahora, POR_RADAR):
            rel = [{"t": html.unescape(re.sub(r"<[^>]+>", "", t)).strip(), "medio": html.unescape(m).strip()}
                   for _, t, m in RELACIONADA.findall(i["_desc"])]
            out["items"].append({"t": i["t"], "medio": i["medio"], "web": i["web"], "fecha": i["fecha"],
                                 "relacionadas": rel[:8]})
        out["ok"] = bool(out["items"])
        if not out["ok"]:
            out["error"] = "sin entradas"
    except Exception as ex:
        out["error"] = f"{type(ex).__name__}: {ex}"[:200]
    return out


def leer_boe(hoy):
    out = dict(BOE, url=f"https://www.boe.es/datosabiertos/api/boe/sumario/{hoy:%Y%m%d}", via="api", ok=False, items=[])
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
            try:
                movil = {a["article"]: a["views"] for a in
                         json.loads(get(base.format(lang=lang, acc="mobile-web", dia=dia), "application/json", 3))["items"][0]["articles"]}
            except Exception as ex:  # sin datos de móvil no se puede filtrar: se usa la lista tal cual y se avisa
                movil = None
                out["aviso"] = f"sin filtro de bots ({type(ex).__name__})"
            items, descartados = [], []
            for a in arts:
                t = a["article"]
                if EXCLUIR_WIKI.search(t):
                    continue
                cuota = (movil.get(t, 0) / a["views"] if a["views"] else 0) if movil is not None else None
                if cuota is not None and cuota < 0.15:
                    descartados.append(t.replace("_", " "))
                    continue
                items.append({"t": t.replace("_", " "), "v": a["views"], "movil": None if cuota is None else round(cuota, 2),
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
    with ThreadPoolExecutor(max_workers=12) as ex:
        feeds = list(ex.map(lambda f: leer_feed(f, ahora), FUENTES))
        radar = list(ex.map(lambda r: leer_radar(r, ahora), RADAR))
        trends = list(ex.map(leer_trends, PAISES_TENDENCIAS))
        wikis = list(ex.map(lambda l: leer_wiki(l, hoy), WIKIS))
    feeds.append(leer_boe(hoy))

    titulares = {"fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}", "version": 2,
                 "fuentes_ok": sum(1 for f in feeds if f["ok"]), "fuentes_total": len(feeds), "fuentes": feeds,
                 "radar": radar}
    tendencias = {"fecha": hoy.isoformat(), "hora": f"{ahora:%H:%M}",
                  "google": {t["geo"]: t for t in trends}, "wikipedia": {w["lang"]: w for w in wikis}}
    for carpeta, datos in (("titulares", titulares), ("tendencias", tendencias)):
        d = os.path.join(DATOS, carpeta)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{hoy.isoformat()}.json"), "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=0)
        limpiar(d, hoy)

    fallan = [f for f in feeds if not f["ok"]]
    print(f"Titulares: {titulares['fuentes_ok']}/{titulares['fuentes_total']} fuentes con datos")
    for f in feeds:
        print(f"  {'OK ' if f['ok'] else 'ERR'} [{f['tipo']}] {f['nombre']}: {len(f['items'])} {f.get('error', '')}")
    print("Radar: " + ", ".join(f"{r['nombre']} {len(r['items'])}" + ("" if r["ok"] else f" ({r.get('error')})") for r in radar))
    print("Tendencias Google: " + ", ".join(f"{t['geo']} {len(t['items'])}" + ("" if t["ok"] else f" ({t.get('error')})") for t in trends))
    print("Wikipedia: " + ", ".join(f"{w['lang']} {len(w['items'])} ({w.get('dia', w.get('error'))})" for w in wikis))
    resumen = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumen:
        with open(resumen, "a", encoding="utf-8") as f:
            f.write(f"### Fuentes {hoy} {ahora:%H:%M}\n\n")
            f.write(f"- Titulares: {titulares['fuentes_ok']} de {titulares['fuentes_total']} fuentes\n")
            f.write("- Sin datos: " + (", ".join(f"{x['nombre']} ({x.get('error', '')[:60]})" for x in fallan) or "ninguna") + "\n")
            f.write("- Radar: " + ", ".join(f"{r['nombre']} {len(r['items'])}" for r in radar) + "\n")
            f.write("- Google Trends: " + ", ".join(f"{t['geo']} {len(t['items'])}" for t in trends) + "\n")
    # falla (en rojo) solo si casi nada ha funcionado
    return 0 if titulares["fuentes_ok"] >= 40 else 1


if __name__ == "__main__":
    sys.exit(main())
