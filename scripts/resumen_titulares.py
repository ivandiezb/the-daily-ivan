#!/usr/bin/env python3
"""Resume los titulares recogidos (datos/titulares/AAAA-MM-DD.json) para la tarea diaria.

Uso: python3 scripts/resumen_titulares.py datos/titulares/AAAA-MM-DD.json [--por-medio 10] [--json salida.json]

Imprime:
  1. las fuentes leídas, por grupo y línea editorial;
  2. los TEMAS CON MÁS COBERTURA: titulares de medios distintos que cuentan la misma noticia (por parecido de sus
     palabras, también entre español, inglés y francés), ordenados por número de medios. Ayuda a medir la
     importancia; revisa siempre a mano lo que agrupa;
  3. los titulares de cada medio y las fuentes oficiales (BOE, Banco de España, BCE, Fed, Moncloa).
Con --json guarda también los temas en un archivo, con los medios de cada uno.
"""
import argparse, heapq, json, math, re, sys, unicodedata
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


# Palabras de titular que no identifican una noticia (cifras, formatos, verbos comodín): no sirven para agrupar.
GENERICAS = set("""
millones millon miles euros dolares libras directo ultima ultimas ultimo hora horas minuto minutos noticias noticia video
videos fotos imagenes claves datos parte caso casos primer primera primero segunda segundo semana semanas meses junto contra
dice dicen pide piden sigue siguen deja dejan sale salen llega llegan podria quiere quieren ahora hasta todo toda
live latest update updates news watch photos week weeks first year years people could would should just
estados unidos united states reino unido kingdom generales
""".split())
RAIZ = 7          # se comparan los primeros 7 caracteres: «ejecución» y «ejecuciones» cuentan como la misma palabra
UMBRAL = 0.25     # parecido medio mínimo (coseno TF-IDF) para unir dos grupos de titulares
UNIR_IDIOMA = (0.45, 0.30)  # 2.ª pasada: parecido mínimo entre grupos del mismo idioma / de idiomas distintos
DESCOLGADO = 0.2  # un titular que se parece menos que esto al resto de su grupo se saca de él
PALABRAS_IDIOMA = {
    "es": set("de la el en los las del por con para una que se su al".split()),
    "en": set("the of to in for and on is with as after at by from an".split()),
    "fr": set("le la les des du et pour une sur dans au aux est".split()),
}


def tokens(titulo):
    return [t for t in re.findall(r"[a-z0-9ñ]+", norm(titulo))
            if len(t) >= 4 and not t.isdigit() and t not in STOP and t not in GENERICAS]


def idioma_de_medios(items):
    """Idioma predominante de cada medio, contando palabras vacías en todos sus titulares."""
    cuenta = defaultdict(Counter)
    for medio, t, _ in items:
        pal = re.findall(r"[a-z]+", norm(t))
        for lengua, vacias in PALABRAS_IDIOMA.items():
            cuenta[medio][lengua] += sum(p in vacias for p in pal)
    return {m: c.most_common(1)[0][0] for m, c in cuenta.items()}


def agrupar(items):
    """items: [(medio, titulo, url)]. Agrupa los titulares que cuentan la misma noticia.

    1.ª pasada: agrupamiento jerárquico por parecido medio (average linkage) entre titulares, con vectores TF-IDF de
       las palabras (recortadas a RAIZ letras). Al exigir parecido con el grupo entero, y no con un solo titular,
       evita las cadenas «A se parece a B, B a C» que juntan noticias distintas.
    2.ª pasada: une grupos cuyo vector medio se parece; con menos exigencia si son de idiomas distintos (la misma
       noticia en español e inglés solo comparte nombres propios).
    """
    n = len(items)
    palabras = [tokens(t) for _, t, _ in items]
    raices = [{p[:RAIZ] for p in ps} for ps in palabras]
    df = Counter(x for rs in raices for x in rs)
    vec = []
    for rs in raices:
        w = {x: math.log(n / df[x]) for x in sorted(rs) if df[x] >= 2}  # orden fijo: mismo resultado en cada ejecución
        nr = math.sqrt(sum(v * v for v in w.values())) or 1
        vec.append({x: v / nr for x, v in w.items()})
    indice = defaultdict(list)
    for i, v in enumerate(vec):
        for x in v:
            indice[x].append(i)
    suma = defaultdict(dict)  # suma de parecidos entre los miembros de dos grupos
    compartidas = Counter()
    for x, idx in indice.items():
        for a in idx:
            for b in idx:
                if a < b:
                    suma[a][b] = suma[a].get(b, 0) + vec[a][x] * vec[b][x]
                    compartidas[a, b] += 1
    # una sola palabra en común («precio», «guerra») no hace la misma noticia; y dos titulares del mismo medio no se
    # unen directamente (suelen ser ángulos distintos de un tema y no suman cobertura)
    pares = [(a, b, s) for a in suma for b, s in suma[a].items()
             if compartidas[a, b] >= 2 and items[a][0] != items[b][0]]
    suma = defaultdict(dict)
    for a, b, s in pares:
        suma[a][b] = suma[b][a] = s
    miembros = {i: [i] for i in range(n)}
    cola = [(-s, a, b) for a in suma for b, s in suma[a].items() if a < b and s >= UMBRAL]
    heapq.heapify(cola)
    nuevo = n
    while cola:
        _, a, b = heapq.heappop(cola)
        if a not in miembros or b not in miembros:
            continue
        c, nuevo = nuevo, nuevo + 1
        miembros[c] = miembros.pop(a) + miembros.pop(b)
        for k in sorted((set(suma[a]) | set(suma[b])) & miembros.keys()):
            if k == c:
                continue
            s = suma[a].get(k, 0) + suma[b].get(k, 0)
            suma[c][k] = suma[k][c] = s
            if s / (len(miembros[c]) * len(miembros[k])) >= UMBRAL:
                heapq.heappush(cola, (-s / (len(miembros[c]) * len(miembros[k])), min(c, k), max(c, k)))

    lengua = idioma_de_medios(items)

    def centro(idx):
        c = Counter()
        for i in idx:
            for x, v in vec[i].items():
                c[x] += v
        nr = math.sqrt(sum(v * v for v in c.values())) or 1
        return {x: v / nr for x, v in c.items()}

    def idioma(idx):
        return Counter(lengua[items[i][0]] for i in idx).most_common(1)[0][0]

    grupos = [g for g in miembros.values() if len(g) >= 2]
    while True:
        cs, ls = [centro(g) for g in grupos], [idioma(g) for g in grupos]
        mejor = (0, None, None)
        for a in range(len(grupos)):
            for b in range(a + 1, len(grupos)):
                s = sum(v * cs[b].get(x, 0) for x, v in cs[a].items())
                if s >= UNIR_IDIOMA[ls[a] != ls[b]] and s > mejor[0]:
                    mejor = (s, a, b)
        if mejor[1] is None:
            break
        _, a, b = mejor
        grupos[a] += grupos.pop(b)

    def parecido_al_resto(i, idx):
        c = Counter()
        for j in idx:
            if j != i:
                for x, v in vec[j].items():
                    c[x] += v
        nr = math.sqrt(sum(v * v for v in c.values())) or 1
        return sum(v * c.get(x, 0) for x, v in vec[i].items()) / nr

    temas = []
    for idx in grupos:
        if len(idx) >= 3:  # fuera los titulares que apenas se parecen al resto del grupo
            idx = [i for i in idx if parecido_al_resto(i, idx) >= DESCOLGADO]
        medios = sorted({items[i][0] for i in idx})
        if len(medios) < 2:
            continue
        # claves legibles: la raíz más repetida, mostrada con la palabra completa más frecuente
        completas = defaultdict(Counter)
        for i in idx:
            for p in palabras[i]:
                completas[p[:RAIZ]][p] += 1
        comunes = Counter(x for i in idx for x in vec[i])
        idx.sort(key=lambda i: -sum(vec[i].get(x, 0) for x, _ in comunes.most_common(5)))
        temas.append({"medios": medios, "n": len(medios),
                      "claves": [completas[x].most_common(1)[0][0] for x, _ in comunes.most_common(5)],
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
    print(f"\nTEMAS CON MÁS COBERTURA (agrupación automática por parecido de los titulares; {len(prensa)} medios leídos;"
          " compruébala: puede juntar o separar noticias)")
    for t in temas[:30]:
        if t["n"] < 3:
            break
        print(f"- {t['n']} medios · claves: {', '.join(t['claves'])} · {', '.join(t['medios'])}")
        vistos = set()
        for h in [h for h in t["titulares"] if not (h["medio"] in vistos or vistos.add(h["medio"]))][:4]:
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
