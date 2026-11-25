#!/usr/bin/env python3
"""Valores que más se mueven: descarga las cotizaciones de la sesión de los valores del Ibex 35, el Euro Stoxx 50
y el S&P 500, elige los que más suben y más bajan y guarda su evolución en el día para las minigráficas.

Lo ejecuta GitHub Actions (flujo «Fuentes») y deja el resultado en la rama «datos»:
  datos/valores/<AAAA-MM-DD>.json   (fecha de Madrid de la ejecución)
  datos/valores/universo.json       (última composición de los índices que se pudo leer; respaldo)

Criterio de selección (cada columna, ordenada por variación):
  · «suben»: los 2 valores del Ibex 35 que más suben y los 3 que más suben del Euro Stoxx 50 y el S&P 500;
  · «bajan»: lo mismo con los que más bajan.
  Si un lado no tiene bastantes valores en positivo (o en negativo), se completa con el otro grupo.

Fuentes: composición de los índices, de Wikipedia (con respaldo en universo.json); cotizaciones, de Yahoo Finance.
Solo biblioteca estándar.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
      "TheDailyIvan/1.0 (+https://github.com/ivandiezb/the-daily-ivan)")
DATOS = os.environ.get("DATOS_DIR", "datos")
SALIDA = os.path.join(DATOS, "valores")
PUNTOS = 48          # puntos máximos de cada minigráfica
DIAS_GUARDADOS = 15
INDICES = {"^IBEX": "Ibex 35", "^STOXX50E": "Euro Stoxx 50", "^GSPC": "S&P 500", "^IXIC": "Nasdaq Composite",
           "^DJI": "Dow Jones", "^RUT": "Russell 2000"}

# Bolsa de cotización, tal como se muestra al lector (código de Yahoo → nombre)
BOLSAS = {"MCE": "Madrid", "NMS": "Nasdaq", "NGM": "Nasdaq", "NCM": "Nasdaq", "NAS": "Nasdaq", "NYQ": "NYSE",
          "NYS": "NYSE", "ASE": "NYSE American", "PCX": "NYSE Arca", "BTS": "Cboe", "GER": "Fráncfort",
          "FRA": "Fráncfort", "PAR": "París", "AMS": "Ámsterdam", "MIL": "Milán", "BRU": "Bruselas",
          "HEL": "Helsinki", "ISE": "Dublín", "LIS": "Lisboa", "VIE": "Viena", "LSE": "Londres", "EBS": "Zúrich",
          "STO": "Estocolmo", "CPH": "Copenhague"}
# Sufijo de Yahoo según la bolsa principal que indique Wikipedia (Euro Stoxx 50)
SUFIJOS = [("xetra", ".DE"), ("frankfurt", ".DE"), ("deutsche", ".DE"), ("paris", ".PA"), ("amsterdam", ".AS"),
           ("milan", ".MI"), ("italiana", ".MI"), ("madrid", ".MC"), ("bme", ".MC"), ("brussels", ".BR"),
           ("helsinki", ".HE"), ("dublin", ".IR"), ("lisbon", ".LS")]
# Nombres cortos para los que el limpiador automático no basta
NOMBRES = {"Industria de Diseño Textil": "Inditex", "Banco Bilbao Vizcaya Argentaria": "BBVA",
           "International Consolidated Airlines Group": "IAG", "International Airlines Group": "IAG",
           "Cellnex Telecom": "Cellnex", "Laboratorios Farmacéuticos Rovi": "Rovi", "Merlin Properties": "Merlin",
           "Compañía de Distribución Integral Logista": "Logista", "Logista Integral": "Logista",
           "Inmobiliaria Colonial": "Colonial", "Red Eléctrica": "Redeia", "Red Electrica": "Redeia",
           "ACS Group": "ACS", "Grupo ACS": "ACS", "Banco de Sabadell": "Banco Sabadell",
           "Alphabet Inc. (Class A)": "Alphabet", "Alphabet Inc. (Class C)": "Alphabet",
           "Berkshire Hathaway": "Berkshire Hathaway", "Meta Platforms": "Meta",
           "Taiwan Semiconductor": "TSMC", "LVMH Moët Hennessy Louis Vuitton": "LVMH",
           "Moët Hennessy Louis Vuitton": "LVMH", "Anheuser-Busch InBev": "AB InBev"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def leer(url, intentos=3, tiempo=25):
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=tiempo) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            ultimo = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"{url}: {ultimo}")


# ---------------------------------------------------------------- composición de los índices (Wikipedia)
class Tablas(HTMLParser):
    """Extrae las tablas «wikitable» como listas de filas de texto."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tablas, self.pila, self.fila, self.celda, self.saltar = [], [], None, None, 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.pila.append([] if "wikitable" in (a.get("class") or "") else None)
        elif not self.pila or self.pila[-1] is None:
            return
        elif tag == "tr":
            self.fila = []
        elif tag in ("td", "th") and self.fila is not None:
            self.celda = []
        elif tag in ("sup", "style", "script"):
            self.saltar += 1
        elif tag == "br" and self.celda is not None:
            self.celda.append(" ")

    def handle_endtag(self, tag):
        if tag == "table" and self.pila:
            t = self.pila.pop()
            if t:
                self.tablas.append(t)
        elif not self.pila or self.pila[-1] is None:
            return
        elif tag in ("sup", "style", "script"):
            self.saltar = max(0, self.saltar - 1)
        elif tag in ("td", "th") and self.celda is not None and self.fila is not None:
            self.fila.append(re.sub(r"\s+", " ", "".join(self.celda)).strip())
            self.celda = None
        elif tag == "tr" and self.fila is not None:
            if self.fila:
                self.pila[-1].append(self.fila)
            self.fila = None

    def handle_data(self, d):
        if self.celda is not None and not self.saltar:
            self.celda.append(d)


def tabla_con(url, claves):
    p = Tablas()
    p.feed(leer(url))
    for t in p.tablas:
        cab = [c.lower() for c in t[0]]
        if all(any(k in c for c in cab) for k in claves):
            return cab, t[1:]
    raise RuntimeError(f"sin tabla con {claves} en {url}")


def col(cab, *nombres):
    for n in nombres:
        for i, c in enumerate(cab):
            if n in c:
                return i
    return None


def ibex35():
    cab, filas = tabla_con("https://en.wikipedia.org/wiki/IBEX_35", ["ticker", "company"])
    it, ic = col(cab, "ticker"), col(cab, "company")
    out = []
    for f in filas:
        if len(f) <= max(it, ic):
            continue
        tk = re.sub(r"[^A-Z0-9.]", "", f[it].upper()).split(".")[0]
        if tk:
            out.append({"tk": tk + ".MC", "n": f[ic], "i": "ibex"})
    return out


def eurostoxx50():
    cab, filas = tabla_con("https://en.wikipedia.org/wiki/EURO_STOXX_50", ["ticker", "name"])
    it, inn, il = col(cab, "ticker"), col(cab, "name"), col(cab, "main listing", "listing", "exchange")
    out = []
    for f in filas:
        if len(f) <= max(it, inn):
            continue
        tk = f[it].strip().upper().replace(" ", "")
        if "." not in tk:
            lugar = (f[il] if il is not None and il < len(f) else "").lower()
            suf = next((s for k, s in SUFIJOS if k in lugar), None)
            if not suf:
                log("Euro Stoxx 50: sin bolsa reconocible para", f)
                continue
            tk += suf
        out.append({"tk": tk, "n": f[inn], "i": "eurostoxx"})
    return out


def sp500():
    cab, filas = tabla_con("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["symbol", "security"])
    it, inn = col(cab, "symbol"), col(cab, "security")
    out = []
    for f in filas:
        if len(f) <= max(it, inn):
            continue
        tk = f[it].strip().upper().replace(".", "-")
        if tk:
            out.append({"tk": tk, "n": f[inn], "i": "sp500"})
    return out


def universo():
    ruta = os.path.join(SALIDA, "universo.json")
    try:
        previo = json.load(open(ruta))
    except Exception:  # noqa: BLE001
        previo = {}
    datos, avisos = {}, []
    for clave, fn, minimo in (("ibex", ibex35, 30), ("eurostoxx", eurostoxx50, 45), ("sp500", sp500, 480)):
        try:
            lista = fn()
            if len(lista) < minimo:
                raise RuntimeError(f"solo {len(lista)} valores")
            datos[clave] = lista
        except Exception as e:  # noqa: BLE001
            avisos.append(f"{clave}: {e}; se usa la última composición guardada")
            datos[clave] = previo.get(clave, [])
    if all(datos.values()):
        datos["fecha"] = dt.datetime.now(MADRID).date().isoformat()
        os.makedirs(SALIDA, exist_ok=True)
        json.dump(datos, open(ruta, "w"), ensure_ascii=False, indent=0)
    return datos, avisos


# ---------------------------------------------------------------- cotizaciones (Yahoo Finance)
class Yahoo:
    """Cliente mínimo: cookie + «crumb» como la web de Yahoo, peticiones en serie y esperas ante el 429."""
    BASE = "https://query1.finance.yahoo.com"

    def __init__(self):
        import http.cookiejar
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", UA), ("Accept", "application/json,text/plain,*/*"),
                              ("Accept-Language", "es-ES,es;q=0.9,en;q=0.8")]
        self.crumb = None
        try:
            try:
                self.op.open("https://fc.yahoo.com", timeout=15).read()
            except urllib.error.HTTPError:
                pass                      # responde 404, pero deja la cookie
            c = self.op.open(self.BASE + "/v1/test/getcrumb", timeout=15).read().decode().strip()
            self.crumb = c if c and "<" not in c and len(c) < 40 else None
        except Exception as e:  # noqa: BLE001
            log("Yahoo: sin crumb:", e)
        log("Yahoo: crumb", "conseguido" if self.crumb else "NO conseguido")

    def get(self, ruta, params):
        if self.crumb:
            params = dict(params, crumb=self.crumb)
        url = self.BASE + ruta + "?" + urllib.parse.urlencode(params, safe=",^")
        for i in range(4):
            try:
                return json.loads(self.op.open(url, timeout=25).read().decode("utf-8", "replace"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and i < 3:
                    time.sleep(3 * 2 ** i)
                    continue
                raise
            except Exception:  # noqa: BLE001
                if i < 3:
                    time.sleep(2)
                    continue
                raise

    def cotizaciones(self, simbolos, lote=40):
        out = {}
        for i in range(0, len(simbolos), lote):
            parte = simbolos[i:i + lote]
            try:
                j = self.get("/v7/finance/quote", {"symbols": ",".join(parte), "lang": "es-ES", "region": "ES"})
            except Exception as e:  # noqa: BLE001
                log(f"Yahoo quote: lote {i // lote + 1} sin datos: {e}")
                continue
            for q in (j.get("quoteResponse") or {}).get("result") or []:
                d = _de_quote(q)
                if d:
                    out[q["symbol"]] = d
            time.sleep(0.7)
        return out

    def spark(self, simbolos, lote=20):
        """Respaldo: evolución en el día de varios símbolos por petición (sirve para elegir y para la gráfica)."""
        out = {}
        for i in range(0, len(simbolos), lote):
            parte = simbolos[i:i + lote]
            try:
                j = self.get("/v8/finance/spark", {"symbols": ",".join(parte), "range": "1d", "interval": "5m"})
            except Exception as e:  # noqa: BLE001
                log(f"Yahoo spark: lote {i // lote + 1} sin datos: {e}")
                continue
            items = j.items() if isinstance(j, dict) and "spark" not in j else \
                [(r.get("symbol"), (r.get("response") or [{}])[0]) for r in (j.get("spark") or {}).get("result") or []]
            for tk, r in items:
                try:
                    d = _de_serie(r)
                    if d:
                        out[tk] = d
                except Exception as e:  # noqa: BLE001
                    log("spark", tk, e)
            time.sleep(0.7)
        return out

    def grafica(self, tk):
        j = self.get("/v8/finance/chart/" + urllib.parse.quote(tk),
                     {"range": "1d", "interval": "5m", "includePrePost": "false"})
        res = (j.get("chart") or {}).get("result") or []
        if not res:
            raise RuntimeError((j.get("chart") or {}).get("error") or "sin datos")
        return _de_serie(res[0])


def _fecha(ts, tzname):
    if not ts:
        return None, None
    tz = ZoneInfo(tzname or "UTC")
    return (dt.datetime.fromtimestamp(ts, tz).date().isoformat(),
            dt.datetime.fromtimestamp(ts, MADRID).strftime("%H:%M"))


def _de_quote(q):
    precio, prev = q.get("regularMarketPrice"), q.get("regularMarketPreviousClose")
    if not precio or not prev:
        return None
    ses, hora = _fecha(q.get("regularMarketTime"), q.get("exchangeTimezoneName"))
    return {"precio": precio, "prev": prev, "c": round((precio / prev - 1) * 100, 2), "bolsa": q.get("exchange") or "",
            "moneda": q.get("currency") or "", "sesion": ses, "hora_madrid": hora,
            "abierta": q.get("marketState") == "REGULAR", "g": None}


def _de_serie(r):
    """Respuesta de chart/spark (formato completo o simplificado) → precio, cierre anterior y serie en %."""
    m = r.get("meta") or {}
    if "indicators" in r:
        ts, cl = r.get("timestamp") or [], (((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    else:
        ts, cl = r.get("timestamp") or [], r.get("close") or []
    pares = [(t, c) for t, c in zip(ts, cl) if c is not None]
    prev = m.get("chartPreviousClose") or m.get("previousClose") or r.get("chartPreviousClose") or r.get("previousClose")
    precio = m.get("regularMarketPrice") or (pares[-1][1] if pares else None)
    if not prev or not precio:
        return None
    ses, hora = _fecha(m.get("regularMarketTime") or (pares[-1][0] if pares else None),
                       m.get("exchangeTimezoneName") or r.get("exchangeTimezoneName"))
    return {"precio": precio, "prev": prev, "c": round((precio / prev - 1) * 100, 2),
            "bolsa": m.get("exchangeName") or "", "moneda": m.get("currency") or "", "sesion": ses,
            "hora_madrid": hora, "abierta": _abierta(m),
            "g": _reducir([round((c / prev - 1) * 100, 2) for _, c in pares]) or None}


def _abierta(m):
    p = (m.get("currentTradingPeriod") or {}).get("regular") or {}
    ahora = time.time()
    return bool(p.get("start") and p.get("end") and p["start"] <= ahora <= p["end"])


def _reducir(g):
    if len(g) <= PUNTOS:
        return g
    paso = (len(g) - 1) / (PUNTOS - 1)
    return [g[round(i * paso)] for i in range(PUNTOS)]


# ---------------------------------------------------------------- selección
SUFIJOS_NOMBRE = re.compile(r"(,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|plc|PLC|S\.A\.U?\.?|SA|"
                            r"N\.V\.|NV|SE|AG|S\.p\.A\.|SpA|Holdings?|Group|Ltd\.?|Limited|& Co\.?|"
                            r"\(The\)|Class [A-C]|\(Class [A-C]\)))+$")


def corto(n):
    n = html.unescape(n or "").strip()
    if n in NOMBRES:
        return NOMBRES[n]
    limpio = re.sub(r"^The\s+", "", SUFIJOS_NOMBRE.sub("", n).strip(" ,"))
    return NOMBRES.get(limpio, limpio or n)


def elegir(pool, n, sube):
    signo = (lambda x: x["c"] > 0) if sube else (lambda x: x["c"] < 0)
    orden = sorted((x for x in pool if signo(x)), key=lambda x: x["c"], reverse=sube)
    vistos, out = set(), []
    for x in orden:                      # evita las dos clases de una misma empresa (GOOG/GOOGL…)
        if x["n"] in vistos:
            continue
        vistos.add(x["n"])
        out.append(x)
        if len(out) == n:
            break
    return out


def columna(ibex, inter, sube):
    a, b = elegir(ibex, 2, sube), elegir(inter, 3, sube)
    if len(a) < 2:
        b = elegir(inter, 5 - len(a), sube)
    elif len(b) < 3:
        a = elegir(ibex, 5 - len(b), sube)
    return sorted(a + b, key=lambda x: x["c"], reverse=sube)


def main():
    ahora = dt.datetime.now(MADRID)
    os.makedirs(SALIDA, exist_ok=True)
    uni, avisos = universo()
    miembros = {}
    for clave in ("ibex", "eurostoxx", "sp500"):
        for x in uni.get(clave, []):
            miembros.setdefault(x["tk"], dict(x))
    log(f"Universo: {sum(len(uni.get(k, [])) for k in ('ibex', 'eurostoxx', 'sp500'))} valores "
        f"({len(miembros)} símbolos distintos)")
    yahoo = Yahoo()
    simbolos = list(miembros) + list(INDICES)
    cot = yahoo.cotizaciones(simbolos)
    log(f"Cotizaciones (quote): {len(cot)} de {len(simbolos)}")
    if len(cot) < 0.6 * len(simbolos):
        faltan = [t for t in simbolos if t not in cot]
        cot.update(yahoo.spark(faltan))
        log(f"Cotizaciones tras el respaldo (spark): {len(cot)} de {len(simbolos)}")
    fallos = {t: "sin datos" for t in simbolos if t not in cot}
    if fallos:
        log("Sin datos:", ", ".join(list(fallos)[:40]))

    # Sesión de referencia de cada bolsa: la más reciente que aparece entre sus valores (descarta los parados)
    ultima = {}
    for tk, d in cot.items():
        if tk in miembros and d["sesion"]:
            ultima[d["bolsa"]] = max(ultima.get(d["bolsa"], ""), d["sesion"])
    filas = []
    for tk, x in miembros.items():
        d = cot.get(tk)
        if not d or d["sesion"] != ultima.get(d["bolsa"]):
            continue
        if abs(d["c"]) > 60:            # dato anómalo (desdoblamiento, error de la fuente)
            avisos.append(f"{tk}: variación anómala {d['c']} %, descartado")
            continue
        filas.append({"n": corto(x["n"]), "tk": tk, "b": BOLSAS.get(d["bolsa"], d["bolsa"] or "—"),
                      "indice": {"ibex": "Ibex 35", "eurostoxx": "Euro Stoxx 50", "sp500": "S&P 500"}[x["i"]],
                      "c": d["c"], "v": round(d["precio"], 4), "prev": round(d["prev"], 4), "moneda": d["moneda"],
                      "sesion": d["sesion"], "hora": d["hora_madrid"], "abierta": d["abierta"], "g": d["g"],
                      "grupo": "ibex" if x["i"] == "ibex" else "inter"})
    ibex = [f for f in filas if f["grupo"] == "ibex"]
    inter = [f for f in filas if f["grupo"] == "inter" and not f["tk"].endswith(".MC")]
    suben, bajan = columna(ibex, inter, True), columna(ibex, inter, False)
    for f in suben + bajan:
        f.pop("grupo", None)
        if not f["g"]:
            try:
                d = yahoo.grafica(f["tk"])
                f["g"] = d["g"] if d else None
                if d and abs(d["c"] - f["c"]) > 0.3:
                    avisos.append(f"{f['tk']}: la gráfica da {d['c']} % y la cotización {f['c']} %")
            except Exception as e:  # noqa: BLE001
                avisos.append(f"{f['tk']}: sin gráfica ({str(e)[:80]})")
            time.sleep(0.6)

    indices = {}
    for tk, nombre in INDICES.items():
        d = cot.get(tk)
        if d:
            indices[nombre] = {"tk": tk, "v": round(d["precio"], 2), "prev": round(d["prev"], 2), "c": d["c"],
                               "sesion": d["sesion"], "hora": d["hora_madrid"], "abierta": d["abierta"]}
    salida = {
        "generado": ahora.isoformat(timespec="seconds"),
        "fuente": "Yahoo Finance (cotizaciones); Wikipedia (composición de los índices)",
        "criterio": "Por columna: los 2 valores del Ibex 35 y los 3 del Euro Stoxx 50 y el S&P 500 que más suben "
                    "(o bajan) en la última sesión; si un grupo no llega, se completa con el otro.",
        "sesiones": {BOLSAS.get(b, b): s for b, s in sorted(ultima.items())},
        "valores_con_datos": len(filas),
        "suben": suben, "bajan": bajan, "indices": indices,
        "avisos": avisos, "sin_datos": len(fallos),
    }
    destino = os.path.join(SALIDA, ahora.date().isoformat() + ".json")
    json.dump(salida, open(destino, "w"), ensure_ascii=False, indent=1)
    log(f"Guardado {destino}: suben {[(f['n'], f['c']) for f in suben]}; bajan {[(f['n'], f['c']) for f in bajan]}")
    for a in avisos:
        log("Aviso:", a)

    limite = (ahora.date() - dt.timedelta(days=DIAS_GUARDADOS)).isoformat()
    for nombre in os.listdir(SALIDA):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", nombre) and nombre[:10] < limite:
            os.remove(os.path.join(SALIDA, nombre))
    if not (suben or bajan):
        sys.exit("No se ha podido elegir ningún valor")


if __name__ == "__main__":
    main()
