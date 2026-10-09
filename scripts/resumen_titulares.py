#!/usr/bin/env python3
"""Resume los titulares recogidos (datos/titulares/AAAA-MM-DD.json) para la tarea diaria.

Uso: python3 scripts/resumen_titulares.py datos/titulares/AAAA-MM-DD.json [--por-medio 10] [--json salida.json]

Imprime:
  1. las fuentes leídas, por grupo y línea editorial;
  2. los TEMAS CON MÁS COBERTURA: titulares de medios distintos que comparten palabras poco comunes, agrupados
     y ordenados por número de medios (ayuda a medir la importancia; revisa siempre a mano lo que agrupa);
  3. los titulares de cada medio y las fuentes oficiales (BOE, Banco de España, BCE, Fed, Moncloa).
Con --json guarda también los temas en un archivo, con los medios de cada uno.
"""
import argparse, json, re, sys, unicodedata
from collections import Counter, defaultdict

STOP = set("""
a al algo ante antes aqui asi aun aunque bajo bien cada como con contra cual cuando de del desde donde dos el ella ellas
ellos en entre era eran es esa ese eso esta estan este esto estos fue fueron gran han hasta hay hoy la las le les lo los mas
me mientras mucho muy nada ni no nos nuevo nueva nuevos nuevas o otra otro para pero poco por porque que quien se sea segun
ser si sin sobre son su sus tambien tan tiene tienen todo todos tras tu un una uno unos unas ya yo vez veces anos ano dias dia
the and for with from that this have has are was were will into after over about than more their they them his her its not
but who what when where which while new says said says les des une pour dans sur avec par aux est sont qui que plus
despues segun ademas puede pueden hace hacer sera seran tener ante sino cuyo cuya donde tras gobierno espana
""".split())


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def fichas(titulo):
    toks = re.findall(r"[a-z0-9ñ]+", norm(titulo))
    return {t for t in toks if (len(t) >= 4 or (t.isdigit() and len(t) >= 2)) and t not in STOP}


def agrupar(items, umbral=2):
    """items: [(medio, titulo, url)]. Une titulares de medios distintos que comparten >= umbral palabras poco comunes."""
    toks = [fichas(t) for _, t, _ in items]
    df = Counter(x for ts in toks for x in ts)
    limite = max(6, int(len(items) * 0.03))  # palabras demasiado frecuentes no sirven para agrupar
    raras = [{x for x in ts if df[x] <= limite} for ts in toks]
    padre = list(range(len(items)))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i
    por_ficha = defaultdict(list)
    for i, ts in enumerate(raras):
        for x in ts:
            por_ficha[x].append(i)
    vecinos = defaultdict(Counter)
    for x, idx in por_ficha.items():
        for a in idx:
            for b in idx:
                if a < b and items[a][0] != items[b][0]:
                    vecinos[a][b] += 1
    for a, cs in vecinos.items():
        for b, n in cs.items():
            if n >= umbral:
                padre[raiz(a)] = raiz(b)
    grupos = defaultdict(list)
    for i in range(len(items)):
        grupos[raiz(i)].append(i)
    temas = []
    for idx in grupos.values():
        medios = sorted({items[i][0] for i in idx})
        if len(medios) < 2:
            continue
        if len(idx) > 40 and umbral < 4:  # grupo demasiado grande: repartir con más exigencia
            temas += agrupar([items[i] for i in idx], umbral + 1)
            continue
        comunes = Counter(x for i in idx for x in raras[i])
        temas.append({"medios": medios, "n": len(medios), "claves": [w for w, _ in comunes.most_common(5)],
                      "titulares": [{"medio": items[i][0], "t": items[i][1], "u": items[i][2]} for i in idx]})
    return sorted(temas, key=lambda t: (-t["n"], -len(t["titulares"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--por-medio", type=int, default=10)
    ap.add_argument("--json")
    a = ap.parse_args()
    d = json.load(open(a.archivo, encoding="utf-8"))
    ok = [f for f in d["fuentes"] if f["ok"]]
    prensa = [f for f in ok if f["grupo"] != "oficial"]
    print(f"TITULARES RECOGIDOS el {d['fecha']} a las {d['hora']}: {len(ok)} de {d['fuentes_total']} fuentes con datos "
          f"({len(prensa)} medios de comunicación).")
    for g in ("espana", "economia", "internacional", "oficial"):
        fs = [f"{f['nombre']} [{f['linea']}]" for f in ok if f["grupo"] == g]
        print(f"  {g}: " + "; ".join(fs))
    fallan = [f["nombre"] for f in d["fuentes"] if not f["ok"]]
    if fallan:
        print("  sin datos hoy: " + ", ".join(fallan))

    items = [(f["nombre"], it["t"], it["u"]) for f in prensa for it in f["items"]]
    temas = agrupar(items)
    print(f"\nTEMAS CON MÁS COBERTURA (agrupación automática por palabras compartidas; {len(prensa)} medios leídos)")
    for t in temas[:30]:
        if t["n"] < 3:
            break
        print(f"- {t['n']} medios · claves: {', '.join(t['claves'])} · {', '.join(t['medios'])}")
        for h in t["titulares"][:3]:
            print(f"    · [{h['medio']}] {h['t'][:150]}")

    print(f"\nTITULARES POR MEDIO (los {a.por_medio} primeros de cada uno)")
    for f in prensa:
        print(f"## {f['nombre']} [{f['linea']}]")
        for it in f["items"][:a.por_medio]:
            print(f"  - {it['t'][:170]}")
    print("\nFUENTES OFICIALES")
    for f in [f for f in ok if f["grupo"] == "oficial"]:
        print(f"## {f['nombre']}")
        for it in f["items"][:25 if f["id"] == "boe" else 8]:
            print(f"  - {it['t'][:220]}  {it['u']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"fecha": d["fecha"], "medios_leidos": len(prensa), "temas": temas}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
