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
import urllib.request
from concurrent.futures import ThreadPoolExecutor
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
def serie_chart(tk):
    """Sesión más reciente de un símbolo: precio, cierre anterior, bolsa y evolución en el día."""
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(tk) +
           "?range=1d&interval=5m&includePrePost=false")
    j = json.loads(leer(url, intentos=2, tiempo=15))
    res = (j.get("chart") or {}).get("result") or []
    if not res:
        raise RuntimeError((j.get("chart") or {}).get("error") or "sin datos")
    r = res[0]
    m = r.get("meta") or {}
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    ts, cl = r.get("timestamp") or [], q.get("close") or []
    pares = [(t, c) for t, c in zip(ts, cl) if c is not None]
    prev = m.get("chartPreviousClose") or m.get("previousClose")
    precio = m.get("regularMarketPrice") or (pares[-1][1] if pares else None)
    if not prev or not precio:
        raise RuntimeError("sin precio o sin cierre anterior")
    hora = m.get("regularMarketTime") or (pares[-1][0] if pares else None)
    tz = ZoneInfo(m.get("exchangeTimezoneName") or "UTC")
    return {
        "precio": precio, "prev": prev, "c": round((precio / prev - 1) * 100, 2),
        "bolsa": m.get("exchangeName") or "", "moneda": m.get("currency") or "",
        "nombre_yahoo": m.get("shortName") or m.get("longName") or "",
        "sesion": dt.datetime.fromtimestamp(hora, tz).date().isoformat() if hora else None,
        "hora_madrid": dt.datetime.fromtimestamp(hora, MADRID).strftime("%H:%M") if hora else None,
        "abierta": _abierta(m),
        "g": _reducir([round((c / prev - 1) * 100, 2) for _, c in pares]),
    }


def _abierta(m):
    p = (m.get("currentTradingPeriod") or {}).get("regular") or {}
    ahora = time.time()
    return bool(p.get("start") and p.get("end") and p["start"] <= ahora <= p["end"])


def _reducir(g):
    if len(g) <= PUNTOS:
        return g
    paso = (len(g) - 1) / (PUNTOS - 1)
    return [g[round(i * paso)] for i in range(PUNTOS)]


def cotizar(simbolos):
    datos, fallos = {}, {}

    def uno(tk):
        try:
            return tk, serie_chart(tk), None
        except Exception as e:  # noqa: BLE001
            return tk, None, str(e)[:160]

    with ThreadPoolExecutor(max_workers=6) as ex:
        for tk, d, err in ex.map(uno, simbolos):
            if d:
                datos[tk] = d
            else:
                fallos[tk] = err
    return datos, fallos


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
    cot, fallos = cotizar(list(miembros) + list(INDICES))
    log(f"Cotizaciones: {len(cot)} con datos, {len(fallos)} sin datos")
    if fallos:
        log("Sin datos:", json.dumps(dict(list(fallos.items())[:25]), ensure_ascii=False))

    # Sesión de referencia de cada bolsa: la más reciente que aparece entre sus valores (descarta los parados)
    ultima = {}
    for tk, d in cot.items():
        if tk in miembros and d["sesion"]:
            ultima[d["bolsa"]] = max(ultima.get(d["bolsa"], ""), d["sesion"])
    filas = []
    for tk, x in miembros.items():
        d = cot.get(tk)
        if not d or not d["g"] or d["sesion"] != ultima.get(d["bolsa"]):
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
