#!/usr/bin/env python3
"""Prepara el bloque «Tendencias de la sociedad» a partir de datos/tendencias/AAAA-MM-DD.json.

  python3 scripts/tendencias.py datos/tendencias/AAAA-MM-DD.json --resumen
      imprime lo más buscado en Google (España e internacional) y lo más leído en Wikipedia, para analizarlo.
  python3 scripts/tendencias.py datos/tendencias/AAAA-MM-DD.json --pagina trabajo/page.html
      mete esos datos en el JSON de la edición (clave "tendencias"), conservando "comentario" y "destacado"
      si ya los has escrito allí.

Internacional = varios países (Google no publica una lista «mundial» de búsquedas en auge): se agrupan las búsquedas
iguales y se ordenan por el número de países donde aparecen y después por volumen aproximado.
"""
import argparse, json, re, sys, unicodedata
from urllib.parse import quote

PAISES_INT = ["US", "GB", "FR", "DE", "IT", "PT", "MX", "AR", "BR", "IN", "JP"]
NOMBRES = {"ES": "España", "US": "EE. UU.", "GB": "Reino Unido", "FR": "Francia", "DE": "Alemania", "IT": "Italia",
           "PT": "Portugal", "MX": "México", "AR": "Argentina", "BR": "Brasil", "IN": "India", "JP": "Japón"}
N_GOOGLE, N_WIKI = 10, 8


def norm(s):
    s = unicodedata.normalize("NFD", s.lower().strip())
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn"))


def latino(s):
    """Solo términos en alfabeto latino: el lector no podría leer los demás."""
    letras = [c for c in s if c.isalpha()]
    return bool(letras) and all("LATIN" in unicodedata.name(c, "") for c in letras)


def fmt(n):
    return f"{n:,}".replace(",", ".")


def enlace(item):
    nots = item.get("noticias") or []
    if nots and nots[0].get("u"):
        return nots[0]["u"], nots[0].get("s", ""), nots[0].get("t", "")
    return "https://www.google.com/search?q=" + quote(item["t"]), "", ""


def google_es(d):
    g = d["google"].get("ES", {})
    out = []
    for it in sorted(g.get("items", []), key=lambda x: -x.get("n", 0))[:N_GOOGLE]:
        u, s, nt = enlace(it)
        out.append({"t": it["t"], "n": it.get("n", 0), "trafico": (fmt(it["n"]) + "+") if it.get("n") else it.get("trafico", ""), "u": u, "fuente": s, "noticia": nt})
    return out


def google_int(d):
    grupos = {}
    for geo in PAISES_INT:
        for it in d["google"].get(geo, {}).get("items", []):
            if not latino(it["t"]):
                continue
            k = norm(it["t"])
            g = grupos.setdefault(k, {"t": it["t"], "n": 0, "paises": [], "item": it})
            g["n"] += it.get("n", 0)
            if geo not in g["paises"]:
                g["paises"].append(geo)
            if it.get("n", 0) > g["item"].get("n", 0):
                g["item"] = it
    out = []
    for g in sorted(grupos.values(), key=lambda g: (-len(g["paises"]), -g["n"]))[:N_GOOGLE]:
        u, s, nt = enlace(g["item"])
        out.append({"t": g["t"], "n": g["n"], "trafico": fmt(g["n"]) + "+", "paises": g["paises"], "u": u,
                    "fuente": s, "noticia": nt})
    return out


def wiki(d, lang):
    w = d["wikipedia"].get(lang, {})
    return [{"t": i["t"], "v": i["v"], "u": i["u"]} for i in w.get("items", [])[:N_WIKI]], w.get("dia", "")


def por_pais(d):
    return {geo: sorted(x.get("items", []), key=lambda i: -i.get("n", 0)) for geo, x in d["google"].items() if x.get("ok")}


def bloque(d):
    wes, dia_es = wiki(d, "es")
    wen, dia_en = wiki(d, "en")
    return {"fecha": d["fecha"], "hora": d["hora"],
            "es": {"google": google_es(d), "wiki": wes, "wiki_dia": dia_es, "wiki_lengua": "español"},
            "int": {"google": google_int(d), "wiki": wen, "wiki_dia": dia_en, "wiki_lengua": "inglés",
                    "paises": [p for p in PAISES_INT if d["google"].get(p, {}).get("ok")]}}


def resumen(b):
    print(f"TENDENCIAS recogidas el {b['fecha']} a las {b['hora']}")
    print("\nGOOGLE · ESPAÑA (búsquedas en auge, volumen aproximado)")
    for i in b["es"]["google"]:
        print(f"  - {i['t']} · {i['trafico']} · {i['fuente']}: {i['noticia'][:110]}")
    print(f"\nGOOGLE · INTERNACIONAL ({', '.join(b['int']['paises'])}; ordenado por nº de países y volumen)")
    for i in b["int"]["google"]:
        print(f"  - {i['t']} · {i['trafico']} · en {len(i['paises'])} país(es): {', '.join(i['paises'])} · {i['noticia'][:90]}")
    print("\nTODAS LAS BÚSQUEDAS EN AUGE POR PAÍS (busca señales fuera de lo habitual: materias primas, crisis, salud…)")
    for geo, items in b.get("_por_pais", {}).items():
        print(f"  {NOMBRES.get(geo, geo)}: " + "; ".join(f"{i['t']} ({i.get('trafico', '')})" for i in items))
    for k, nombre in (("es", "español"), ("int", "inglés")):
        print(f"\nWIKIPEDIA EN {nombre.upper()} · lo más leído el {b[k]['wiki_dia']} (sin tráfico automático)")
        for i in b[k]["wiki"]:
            print(f"  - {i['t']} · {fmt(i['v'])} visitas")


def inyectar(b, pagina):
    src = open(pagina, encoding="utf-8").read()
    m = re.search(r'(<script type="application/json" id="edition">)(.*?)(</script>)', src, re.S)
    if not m:
        raise SystemExit(f"{pagina}: no encuentro el JSON de la edición")
    ed = json.loads(m.group(2))
    previo = ed.get("tendencias") or {}
    for k in ("comentario", "destacado"):
        if previo.get(k):
            b[k] = previo[k]
    ed["tendencias"] = b
    nuevo = json.dumps(ed, ensure_ascii=False, indent=1).replace("</", "<\\/")
    open(pagina, "w", encoding="utf-8").write(src[:m.start(2)] + "\n" + nuevo + "\n" + src[m.end(2):])
    print(f"Tendencias añadidas a {pagina}: {len(b['es']['google'])} búsquedas de España, "
          f"{len(b['int']['google'])} internacionales; comentario {'sí' if b.get('comentario') else 'NO (falta)'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("datos")
    ap.add_argument("--resumen", action="store_true")
    ap.add_argument("--pagina")
    a = ap.parse_args()
    d = json.load(open(a.datos, encoding="utf-8"))
    b = bloque(d)
    if a.resumen or not a.pagina:
        resumen({**b, "_por_pais": por_pais(d)})
    if a.pagina:
        inyectar(b, a.pagina)


if __name__ == "__main__":
    sys.exit(main())
