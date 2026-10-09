#!/usr/bin/env python3
"""Valida el JSON de una edición de «The Daily Iván» antes de publicarla.

Uso: python3 scripts/validar_edicion.py trabajo/page.html [--anterior trabajo/page_prev.html] [--temas trabajo/temas.json]

Imprime ERRORES (impiden publicar: corrígelos) y AVISOS (revísalos; pueden estar justificados) y termina con
código 1 si hay algún error. Comprueba las reglas editoriales del encargo diario que se pueden comprobar de forma
mecánica; no sustituye a leer la edición.
"""
import argparse, json, os, re, sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fuentes_catalogo import EXCLUIDOS, clasificar_dominio, dominio_de  # noqa: E402

CONF = {"confirmado", "una-fuente", "en-desarrollo", "seguimiento", "agenda"}
TIPOS_MERCADO = {"indice", "usd", "divisa", "rent"}
SECCIONES = set("""index home portada inicio noticias news ultima-hora ultimas-noticias economia mercados bolsa internacional
mundo world espana politica sociedad opinion deportes cultura tecnologia ciencia salud vivienda empleo europa
""".split())
LINEAS_METODO = ("«Cobertura» indica", "«Profundizar · copiar prompt»", "«Tendencias de la sociedad» resume")

errores, avisos = [], []


def err(m):
    errores.append(m)


def aviso(m):
    avisos.append(m)


def leer(pagina):
    src = open(pagina, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="edition">(.*?)</script>', src, re.S)
    if not m:
        raise SystemExit(f"ERROR {pagina}: no encuentro el bloque JSON de la edición")
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise SystemExit(f"ERROR {pagina}: el JSON no es válido ({e})")


def portada(u):
    """True si la URL parece una portada o una página de sección, no un artículo concreto."""
    p = urlparse(u)
    if p.scheme not in ("http", "https") or not p.netloc:
        return True
    ruta = p.path.strip("/")
    if not ruta:
        return not p.query  # una consulta (…/?id=123) puede ser un documento concreto
    partes = [re.sub(r"\.(html?|php|aspx?)$", "", x) for x in ruta.split("/")]
    if partes[-1].lower() in SECCIONES:
        return True  # p. ej. …/es/noticias/, /mercados.html
    if len(partes) == 1 and not re.search(r"\d", partes[0]) and "-" not in partes[0] and "." not in partes[0] \
            and len(partes[0]) < 25:
        return True  # p. ej. /economia, /internacional
    return False


def texto(it):
    return " ".join(str(it.get(k, "")) for k in ("titulo", "hecho", "importa", "vigilar", "nota"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pagina")
    ap.add_argument("--anterior")
    ap.add_argument("--temas")
    a = ap.parse_args()
    ed = leer(a.pagina)
    prev = leer(a.anterior) if a.anterior else None
    leidos = None
    if a.temas:
        try:
            t = json.load(open(a.temas, encoding="utf-8"))
            leidos = t.get("generalistas_leidos", t.get("medios_leidos"))
        except (OSError, json.JSONDecodeError) as e:
            aviso(f"no he podido leer {a.temas} ({e}); no compruebo el total de medios de la cobertura")

    for k in ("fechaISO", "fechaTexto", "cierre", "lede", "claves", "secciones", "mercados", "metodo", "radar", "agenda"):
        if not ed.get(k):
            err(f"falta o está vacío «{k}»")
    if ed.get("tipo", "") != "":
        err("«tipo» debe ser una cadena vacía")
    if ed.get("fechaISO") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", ed["fechaISO"]):
        err(f"fechaISO con formato raro: {ed['fechaISO']}")
    if ed.get("cierre") and not re.fullmatch(r"\d{2}:\d{2}", ed["cierre"]):
        err(f"cierre debe ser HH:MM: {ed['cierre']}")
    if prev and ed.get("fechaISO") and ed["fechaISO"] == prev.get("fechaISO"):
        aviso(f"la fecha ({ed['fechaISO']}) es la misma que la de la edición anterior")

    codigos = {}
    secciones = ed.get("secciones") or []
    if prev:
        esquema = lambda e: [(s.get("id"), s.get("titulo"), s.get("corto"), s.get("tipo")) for s in e.get("secciones", [])]
        if esquema(ed) != esquema(prev):
            err("las secciones (id, titulo, corto, tipo) no coinciden con las de la edición anterior")
    prefijos_prev = {}
    if prev:
        for s in prev.get("secciones", []):
            if s.get("items"):
                prefijos_prev[s["id"]] = re.sub(r"\d+$", "", s["items"][0].get("code", ""))
    for s in secciones:
        its = s.get("items") or []
        if len(its) < 2 or len(its) > 4:
            err(f"sección {s.get('id')}: {len(its)} noticias (deben ser 3–4; 2 como mínimo absoluto)")
        elif len(its) == 2:
            aviso(f"sección {s.get('id')}: solo 2 noticias")
        for j, it in enumerate(its):
            c = it.get("code", "")
            donde = f"{s.get('id')}/{c or j}"
            if not c:
                err(f"{donde}: falta «code»")
            elif c in codigos:
                err(f"código repetido: {c}")
            codigos[c] = it
            pre = prefijos_prev.get(s.get("id"))
            if pre and c and not re.fullmatch(re.escape(pre) + r"\d+", c):
                err(f"{donde}: el código debería empezar por {pre} como en la edición anterior")
            for k in ("titulo", "hecho", "importa"):
                if not str(it.get(k, "")).strip():
                    err(f"{donde}: falta «{k}»")
            if j == 0:
                if it.get("breve"):
                    err(f"{donde}: la noticia principal no puede ser breve")
                if not it.get("vigilar"):
                    aviso(f"{donde}: la noticia principal no tiene «vigilar»")
            elif not it.get("breve"):
                aviso(f"{donde}: no es la principal y no está marcada como breve")
            if it.get("conf") not in CONF:
                err(f"{donde}: conf «{it.get('conf')}» no es válido ({', '.join(sorted(CONF))})")
            fs = it.get("fuentes") or []
            minimo = 2 if it.get("breve") else 3
            if not fs:
                err(f"{donde}: sin fuentes")
            elif len(fs) < minimo and it.get("conf") not in ("una-fuente", "agenda"):
                aviso(f"{donde}: {len(fs)} fuente(s); lo pedido es al menos {minimo}")
            hosts = set()
            for f in fs:
                u = f.get("u", "")
                if not f.get("t"):
                    err(f"{donde}: una fuente no tiene nombre («t»)")
                if not u or portada(u):
                    err(f"{donde}: URL que no parece un artículo concreto: {u!r}")
                elif "news.google.com" in u:
                    err(f"{donde}: enlace de Google News; usa la URL original del artículo: {u[:80]}")
                else:
                    tipo = clasificar_dominio(u)
                    if tipo == "excluido":
                        err(f"{donde}: {dominio_de(u)} está excluido del catálogo ({EXCLUIDOS.get(dominio_de(u), '')[:60]}…)")
                    elif tipo == "otro":
                        aviso(f"{donde}: {dominio_de(u)} no está en el catálogo de referencia ni es oficial. Sustitúyela "
                              "por un medio de referencia, la agencia original o la fuente primaria; déjala solo si es "
                              "la fuente primaria (p. ej., la propia empresa u organismo) o el único origen serio")
                hosts.add(urlparse(u).netloc.removeprefix("www."))
            if len(fs) >= 2 and len(hosts) < 2:
                aviso(f"{donde}: todas las fuentes son del mismo sitio ({', '.join(hosts)})")
            cob = it.get("cobertura")
            if cob is not None:
                n, de, esp, medios = cob.get("n"), cob.get("de"), cob.get("esp", 0), cob.get("medios") or []
                if not isinstance(n, int) or not isinstance(de, int) or not isinstance(esp, int) or n < 0 or n > de \
                        or n + esp < 1:
                    err(f"{donde}: cobertura incoherente (n={n}, de={de}, esp={esp})")
                elif medios and len(set(medios)) != n + esp:
                    err(f"{donde}: cobertura n={n} + esp={esp} pero lista {len(set(medios))} medios distintos")
                if leidos and de != leidos:
                    err(f"{donde}: cobertura de={de}, pero los medios leídos hoy son {leidos}")
    claves = ed.get("claves") or []
    if len(claves) != 5:
        err(f"claves: {len(claves)} (deben ser exactamente 5)")
    for k in claves:
        if k.get("ref") not in codigos:
            err(f"clave con ref inexistente: {k.get('ref')!r}")

    for m in ed.get("mercados") or []:
        if m.get("tipo") not in TIPOS_MERCADO:
            err(f"mercados/{m.get('n')}: tipo «{m.get('tipo')}» no válido")
        if not isinstance(m.get("v"), (int, float)):
            err(f"mercados/{m.get('n')}: falta el valor numérico «v»")
        if m.get("u") and portada(m["u"]):
            aviso(f"mercados/{m.get('n')}: la URL parece una portada: {m['u']}")
        elif m.get("u") and clasificar_dominio(m["u"]) in ("otro", "excluido"):
            aviso(f"mercados/{m.get('n')}: {dominio_de(m['u'])} no es un medio de referencia ni una fuente oficial")
        if isinstance(m.get("v"), (int, float)) and isinstance(m.get("prev"), (int, float)) and isinstance(m.get("c"), (int, float)) and m["prev"]:
            calc = (m["v"] / m["prev"] - 1) * 100
            if abs(calc - m["c"]) > 0.06:
                err(f"mercados/{m.get('n')}: c={m['c']} % pero v/prev da {calc:.2f} %")
    if prev:
        nombres = lambda e: [m.get("n") for m in e.get("mercados", [])]
        if nombres(ed) != nombres(prev):
            aviso("el panel de mercados no tiene los mismos instrumentos que la edición anterior")

    for r in ed.get("radar") or []:
        if r.get("u") and portada(r["u"]):
            err(f"radar: URL que no parece un artículo: {r['u']}")
        elif r.get("u") and clasificar_dominio(r["u"]) == "excluido":
            err(f"radar: {dominio_de(r['u'])} está excluido del catálogo")
        elif r.get("u") and clasificar_dominio(r["u"]) == "otro":
            aviso(f"radar: {dominio_de(r['u'])} no está en el catálogo de referencia ni es oficial")

    metodo = " ".join(ed.get("metodo") or [])
    for frag in LINEAS_METODO:
        if frag not in metodo:
            aviso(f"metodo: falta la línea que contiene «{frag}»")
    if ed.get("fechaTexto"):
        dia = ed["fechaTexto"].split(",")[-1].strip().split(" de ")[0]
        if (ed.get("metodo") or [""])[0].find(f" {dia} de ") < 0:
            aviso("metodo: la primera línea no parece actualizada con el día de hoy")

    tr = ed.get("tendencias")
    if tr is not None:
        if not (tr.get("es") or {}).get("google") and not (tr.get("int") or {}).get("google"):
            err("tendencias: no tiene datos (ejecuta scripts/tendencias.py --pagina o quita la clave)")
        if not tr.get("comentario"):
            aviso("tendencias: falta el comentario")
        if tr.get("fecha") and ed.get("fechaISO") and tr["fecha"] < ed["fechaISO"]:
            aviso(f"tendencias: los datos son del {tr['fecha']}, no de hoy")

    if prev:
        ant = {it.get("titulo"): it for s in prev.get("secciones", []) for it in s.get("items", [])}
        for c, it in codigos.items():
            if it.get("titulo") in ant and it.get("conf") != "seguimiento":
                aviso(f"{c}: mismo título que en la edición anterior: «{it['titulo'][:70]}»")
        if ed.get("lede") and ed.get("lede") == prev.get("lede"):
            err("el lede es el mismo que el de la edición anterior")

    total = sum(len(s.get("items") or []) for s in secciones)
    print(f"Edición {ed.get('fechaISO')}: {len(secciones)} secciones, {total} noticias, "
          f"{sum(1 for c in codigos.values() if c.get('cobertura'))} con cobertura.")
    for m in errores:
        print("ERROR  " + m)
    for m in avisos:
        print("AVISO  " + m)
    print("RESULTADO: " + ("hay errores: corrígelos antes de publicar." if errores else
                           "sin errores" + (" (revisa los avisos)." if avisos else ".")))
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
