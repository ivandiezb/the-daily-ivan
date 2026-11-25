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

Uso en la edición (lo ejecuta la tarea diaria o la actualización, con los datos traídos de la rama «datos»):
  python3 scripts/valores.py edicion <datos/valores/AAAA-MM-DD.json> <page.html> [--sin-panel]
  Escribe el bloque «valores» en el JSON de la edición, pone o actualiza el Russell 2000 en el panel de mercados
  (detrás del Dow Jones) y avisa si los índices del panel no cuadran con las cotizaciones.

Fuentes: composición de los índices, de Wikipedia (con respaldo en universo.json); cotizaciones y evolución en el
día, del servicio de datos de la web de CNBC (Yahoo Finance bloquea las peticiones desde GitHub).
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

# Sufijo del símbolo (convención .DE, .PA…) según la bolsa principal que indique Wikipedia (Euro Stoxx 50)
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
        tk = f[it].strip().upper()
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


# ---------------------------------------------------------------- cotizaciones (servicio de datos de CNBC)
# Yahoo Finance bloquea las peticiones desde GitHub Actions (HTTP 429); el servicio de cotizaciones que usa la web
# de CNBC responde para Madrid, el resto de Europa, EE. UU. y los índices.
QUOTE = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol?symbols={}"
         "&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json&events=1")
CHART = "https://ts-api.cnbc.com/harmony/app/charts/1D.json?symbol={}"
SUF_CNBC = {".MC": "-ES", ".DE": "-DE", ".PA": "-FR", ".AS": "-NL", ".MI": "-IT", ".BR": "-BE", ".HE": "-FI",
            ".IR": "-IE", ".LS": "-PT"}
IDX_CNBC = {"^IBEX": ".IBEX", "^STOXX50E": ".STOXX50E", "^GSPC": ".SPX", "^IXIC": ".IXIC", "^DJI": ".DJI",
            "^RUT": ".RUT"}
ZONAS = {"CET": "Europe/Madrid", "CEST": "Europe/Madrid", "EET": "Europe/Helsinki", "EEST": "Europe/Helsinki",
         "EST": "America/New_York", "EDT": "America/New_York", "GMT": "Europe/London", "BST": "Europe/London"}
# Sesión regular (hora local de cada bolsa) para quedarse solo con ella en las gráficas
SESION = {"America/New_York": ("09:30", "16:00"), "Europe/Helsinki": ("10:00", "18:35"),
          "Europe/London": ("08:00", "16:35")}
SESION_EU = ("09:00", "17:40")
BOLSAS_CNBC = [("mercado continuo", "Madrid"), ("madrid", "Madrid"), ("xetra", "Fráncfort"),
               ("frankfurt", "Fráncfort"), ("paris", "París"), ("amsterdam", "Ámsterdam"), ("milan", "Milán"),
               ("brussels", "Bruselas"), ("helsinki", "Helsinki"), ("irish", "Dublín"), ("dublin", "Dublín"),
               ("lisbon", "Lisboa"), ("nasdaq", "Nasdaq"), ("nyse", "NYSE"), ("new york", "NYSE")]


def a_cnbc(tk):
    if tk in IDX_CNBC:
        return IDX_CNBC[tk]
    for suf, nuevo in SUF_CNBC.items():
        if tk.endswith(suf):
            return tk[:-len(suf)] + nuevo
    return tk


def _num(x):
    try:
        return float(str(x).replace(",", "").replace("%", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def bolsa_de(nombre, tk):
    n = (nombre or "").lower()
    for k, v in BOLSAS_CNBC:
        if k in n:
            return v
    return {"-ES": "Madrid", "-DE": "Fráncfort", "-FR": "París", "-NL": "Ámsterdam", "-IT": "Milán",
            "-BE": "Bruselas", "-FI": "Helsinki", "-IE": "Dublín"}.get(a_cnbc(tk)[-3:], nombre or "—")


class Cotizaciones:
    def cotizaciones(self, simbolos, lote=40):
        out = {}
        for i in range(0, len(simbolos), lote):
            parte = simbolos[i:i + lote]
            mapa = {a_cnbc(t): t for t in parte}
            try:
                j = json.loads(leer(QUOTE.format(urllib.parse.quote("|".join(mapa), safe="|."))))
            except Exception as e:  # noqa: BLE001
                log(f"Cotizaciones: lote {i // lote + 1} sin datos: {e}")
                continue
            for q in ((j.get("FormattedQuoteResult") or {}).get("FormattedQuote") or []):
                tk = mapa.get(q.get("symbol"))
                precio, prev = _num(q.get("last")), _num(q.get("previous_day_closing"))
                if not tk or q.get("code") not in (0, "0") or not precio or not prev:
                    continue
                zona = ZONAS.get(q.get("timeZone") or "", "Europe/Madrid")
                try:
                    t = dt.datetime.fromisoformat(q.get("last_time"))
                except (TypeError, ValueError):
                    t = None
                c_pub = _num(q.get("change_pct"))
                # la variación publicada se calcula con el precio sin redondear: es más exacta en valores baratos
                c_calc = round((precio / prev - 1) * 100, 2)
                out[tk] = {"precio": precio, "prev": prev,
                           "c": c_pub if c_pub is not None and abs(c_pub - c_calc) < 1 else c_calc,
                           "c_fuente": c_pub, "c_calc": c_calc, "bolsa": bolsa_de(q.get("exchange"), tk),
                           "moneda": q.get("currencyCode") or "", "zona": zona,
                           "sesion": t.astimezone(ZoneInfo(zona)).date().isoformat() if t else None,
                           "hora_madrid": t.astimezone(MADRID).strftime("%H:%M") if t else None,
                           "abierta": abierta(zona), "g": None}
            time.sleep(0.5)
        return out

    def grafica(self, tk, prev, zona):
        """Evolución de la última sesión regular, en % sobre el cierre anterior."""
        j = json.loads(leer(CHART.format(urllib.parse.quote(a_cnbc(tk))), intentos=2, tiempo=20))
        barras = ((j.get("barData") or {}).get("priceBars") or [])
        z = ZoneInfo(zona)
        pts = []
        for b in barras:
            c, ms = _num(b.get("close")), b.get("tradeTimeinMills")
            if c is None or not ms:
                continue
            pts.append((dt.datetime.fromtimestamp(int(ms) / 1000, z), c))
        if not pts:
            raise RuntimeError("sin barras")
        dia = pts[-1][0].date()
        ini, fin = SESION.get(zona, SESION_EU)
        hoy = [c for t, c in pts if t.date() == dia and ini <= t.strftime("%H:%M") <= fin]
        if len(hoy) < 2:
            raise RuntimeError("sesión sin barras suficientes")
        return {"c": round((hoy[-1] / prev - 1) * 100, 2), "g": _reducir([round((c / prev - 1) * 100, 2) for c in hoy]),
                "sesion": dia.isoformat()}


def abierta(zona):
    """¿Está la bolsa en sesión regular ahora mismo? (por horario; no cuenta festivos)"""
    ahora = dt.datetime.now(ZoneInfo(zona))
    ini, fin = SESION.get(zona, SESION_EU)
    return ahora.weekday() < 5 and ini <= ahora.strftime("%H:%M") <= fin


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
    fuente = Cotizaciones()
    simbolos = list(miembros) + list(INDICES)
    cot = fuente.cotizaciones(simbolos)
    log(f"Cotizaciones: {len(cot)} de {len(simbolos)}")
    raras = [t for t, d in cot.items() if d["c_fuente"] is not None and abs(d["c_fuente"] - d["c_calc"]) >= 1]
    if raras:
        log("Variación publicada muy distinta de la calculada (se usa la calculada):", raras[:20])
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
        filas.append({"n": corto(x["n"]), "tk": tk, "b": d["bolsa"],
                      "indice": {"ibex": "Ibex 35", "eurostoxx": "Euro Stoxx 50", "sp500": "S&P 500"}[x["i"]],
                      "c": d["c"], "v": round(d["precio"], 4), "prev": round(d["prev"], 4), "moneda": d["moneda"],
                      "sesion": d["sesion"], "hora": d["hora_madrid"], "abierta": d["abierta"], "g": d["g"],
                      "zona": d["zona"],
                      "grupo": "ibex" if x["i"] == "ibex" else "inter"})
    ibex = [f for f in filas if f["grupo"] == "ibex"]
    inter = [f for f in filas if f["grupo"] == "inter" and not f["tk"].endswith(".MC")]
    suben, bajan = columna(ibex, inter, True), columna(ibex, inter, False)
    for f in suben + bajan:
        f.pop("grupo", None)
        if not f.get("g"):
            try:
                d = fuente.grafica(f["tk"], f["prev"], f.pop("zona"))
                f["g"] = d["g"]
                if d and abs(d["c"] - f["c"]) > 0.3:
                    avisos.append(f"{f['tk']}: la gráfica da {d['c']} % y la cotización {f['c']} %")
            except Exception as e:  # noqa: BLE001
                avisos.append(f"{f['tk']}: sin gráfica ({str(e)[:80]})")
            time.sleep(0.6)
        f.pop("zona", None)

    indices = {}
    for tk, nombre in INDICES.items():
        d = cot.get(tk)
        if d:
            indices[nombre] = {"tk": tk, "v": round(d["precio"], 2), "prev": round(d["prev"], 2), "c": d["c"],
                               "sesion": d["sesion"], "hora": d["hora_madrid"], "abierta": d["abierta"]}
    salida = {
        "generado": ahora.isoformat(timespec="seconds"),
        "fuente": "CNBC (cotizaciones y gráficas); Wikipedia (composición de los índices)",
        "criterio": "Por columna: los 2 valores del Ibex 35 y los 3 del Euro Stoxx 50 y el S&P 500 que más suben "
                    "(o bajan) en la última sesión; si un grupo no llega, se completa con el otro.",
        "sesiones": dict(sorted(ultima.items())),
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


# ---------------------------------------------------------------- volcado en la edición
MESES = "ene feb mar abr may jun jul ago sep oct nov dic".split()
EEUU = {"Nasdaq", "NYSE", "NYSE American", "NYSE Arca", "CBOE", "Cboe"}
RE_ED = re.compile(r'(<script type="application/json" id="edition">)(.*?)(</script>)', re.S)


def _dia(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1]}"


def cabecera(filas, generado):
    """«cierre del 24 nov», «en sesión · 16:47» o la mezcla por zonas (Europa / EE. UU.)."""
    hora = dt.datetime.fromisoformat(generado).astimezone(MADRID).strftime("%H:%M")
    zonas = {}
    for f in filas:
        z = "EE. UU." if f.get("b") in EEUU else "Europa"
        zonas.setdefault(z, []).append(f)
    estado = {z: (any(f.get("abierta") for f in fs), max(f.get("sesion") or "" for f in fs)) for z, fs in zonas.items()}
    if all(a for a, _ in estado.values()):
        return f"en sesión · {hora}"
    if not any(a for a, _ in estado.values()):
        return "cierre del " + _dia(max(d for _, d in estado.values()))
    return " · ".join(f"{z} {hora}" if a else f"{z} al cierre" for z, (a, d) in sorted(estado.items(), key=lambda x: x[0] != "Europa"))


def cmd_edicion(args):
    import argparse
    ap = argparse.ArgumentParser(prog="valores.py edicion")
    ap.add_argument("datos"); ap.add_argument("pagina"); ap.add_argument("--sin-panel", action="store_true")
    a = ap.parse_args(args)
    d = json.load(open(a.datos))
    src = open(a.pagina).read()
    m = RE_ED.search(src)
    if not m:
        sys.exit("No encuentro el JSON de la edición en " + a.pagina)
    ed = json.loads(m.group(2))
    gen = dt.datetime.fromisoformat(d["generado"])
    edad = (dt.datetime.now(MADRID) - gen).total_seconds() / 3600
    if edad > 20:
        sys.exit(f"VALORES_VIEJOS: los datos son de {d['generado']} (hace {edad:.0f} h); no se tocan los valores")
    filas = (d.get("suben") or []) + (d.get("bajan") or [])
    if len(filas) < 4:
        sys.exit("VALORES_INSUFICIENTES: menos de 4 valores en los datos; no se tocan los valores")
    limpia = lambda f: {"n": f["n"], "b": f["b"], "c": f["c"], "tk": f["tk"], **({"g": f["g"]} if f.get("g") else {})}
    ed["valores"] = {"s": cabecera(filas, d["generado"]), "fuente": "CNBC",
                     "suben": [limpia(f) for f in d.get("suben") or []],
                     "bajan": [limpia(f) for f in d.get("bajan") or []]}
    print(f"Valores: {ed['valores']['s']} · suben " + ", ".join(f"{f['n']} {f['c']:+.2f} %" for f in ed['valores']['suben'])
          + " · bajan " + ", ".join(f"{f['n']} {f['c']:+.2f} %" for f in ed['valores']['bajan']))
    sin_g = [f["n"] for f in filas if not f.get("g")]
    if sin_g:
        print("AVISO: sin gráfica:", ", ".join(sin_g))

    idx = d.get("indices") or {}
    panel = ed.get("mercados") or []
    if not a.sin_panel and idx.get("Russell 2000"):
        r = idx["Russell 2000"]
        momento = f"{r['hora']}" if r.get("abierta") else f"cierre {_dia(r['sesion'])}"
        fila = {"n": "Russell 2000", "tipo": "indice", "v": r["v"], "c": round((r["v"] / r["prev"] - 1) * 100, 2),
                "prev": r["prev"], "dec": 2, "s": f"{momento} · CNBC", "u": "https://www.cnbc.com/quotes/.RUT"}
        nombres = [x.get("n") for x in panel]
        if "Russell 2000" in nombres:
            panel[nombres.index("Russell 2000")] = fila
        else:
            pos = nombres.index("Dow Jones") + 1 if "Dow Jones" in nombres else len([x for x in panel if x.get("tipo") == "indice"])
            panel.insert(pos, fila)
        ed["mercados"] = panel
        print(f"Panel: Russell 2000 {fila['v']} ({fila['c']:+.2f} %, {fila['s']})")
    # Contraste de los índices del panel con las cotizaciones (mismo instrumento, distinta fuente)
    for x in panel:
        r = idx.get(x.get("n"))
        if r and isinstance(x.get("v"), (int, float)) and x.get("n") != "Russell 2000":
            dif = abs(x["v"] / r["v"] - 1) * 100
            if dif > 0.15 and abs(x["v"] / r["prev"] - 1) * 100 > 0.15:
                print(f"AVISO: panel/{x['n']} = {x['v']}, pero las cotizaciones dan {r['v']} "
                      f"({'en sesión' if r.get('abierta') else 'cierre ' + _dia(r['sesion'])}) y cierre anterior {r['prev']}")
    nuevo = json.dumps(ed, ensure_ascii=False, indent=1).replace("</", "<\\/")
    open(a.pagina, "w").write(src[:m.start(2)] + nuevo + src[m.end(2):])
    print("VALORES_OK")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "edicion":
        cmd_edicion(sys.argv[2:])
    else:
        main()
