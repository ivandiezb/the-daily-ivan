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
import argparse, heapq, json, math, os, re, sys, unicodedata
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fuentes_catalogo import BLOQUES, ESPECIALIZADOS, EXCLUIDOS, FUENTES, GENERALISTAS, clasificar_dominio  # noqa: E402

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


# La misma palabra en español, inglés y francés (sobre todo lugares y personas que se escriben distinto), para que
# la misma noticia contada en varios idiomas se agrupe junta.
EQUIV = {}
for _canon, _variantes in {
    "riyadh": "riad riyad", "kyiv": "kiev kiew", "beijing": "pekin", "moscow": "moscu moscou", "london": "londres",
    "iran": "irani iranian iranians iranies", "israel": "israeli israelis israelies israelien", "ukraine": "ucrania ukrainian ucraniano ucranianos ukrainians",
    "russia": "rusia russian ruso rusos russians russie russe", "china": "chinese chino chinos chine", "saudi": "saudies saudita sauditas saudis saoudite",
    "houthi": "huties hutis houthis", "pentagon": "pentagono", "execution": "ejecucion executed ejecutado ejecutar executions",
    "hurricane": "huracan ouragan", "earthquake": "terremoto seisme", "airport": "aeropuerto aeroport", "nato": "otan",
    "germany": "alemania allemagne german aleman alemanes", "france": "francia french frances", "italy": "italia italian", "japan": "japon japanese japones",
    "brazil": "brasil bresil", "syria": "siria syrie", "lebanon": "libano liban", "turkey": "turquia turquie",
    "korea": "corea coree", "greenland": "groenlandia", "zelensky": "zelenski zelenskyy", "putin": "poutine",
    "khamenei": "jamenei", "hezbollah": "hezbola", "election": "elecciones elections electoral comicios midterms",
    "president": "presidente presidential presidencial", "petroleo": "petrole crude crudo", "gold": "oro", "tariffs": "aranceles tariff arancel",
    "inflation": "inflacion", "attack": "ataque ataques attacks attaque", "strike": "strikes", "missile": "misil misiles missiles",
    "drone": "dron drones", "ceasefire": "alto", "nobel": "nobels", "peace": "paix", "prize": "premio prix",
}.items():
    for _v in _variantes.split():
        EQUIV[_v] = _canon


def tokens(titulo):
    return [EQUIV.get(t, t) for t in re.findall(r"[a-z0-9ñ]+", norm(titulo))
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


def normalizar(d):
    """Completa cada fuente con su cabecera («medio») y su tipo según el catálogo (también para datos antiguos)."""
    cat = {f["id"]: f for f in FUENTES}
    antiguo = {"espana": "generalista", "internacional": "generalista", "economia": "especializado", "oficial": "oficial"}
    for f in d["fuentes"]:
        c = cat.get(f["id"], {})
        f["tipo"] = c.get("tipo") or f.get("tipo") or antiguo.get(f.get("grupo"), "generalista")
        f["medio"] = c.get("medio") or f.get("medio") or f["nombre"]
        f["bloques"] = c.get("bloques") or f.get("bloques") or []
        f["linea"] = c.get("linea", f.get("linea", ""))
        f["dominio"] = c.get("dominio") or f.get("dominio") or ""
    return d


def clase(tipo):
    return "gen" if tipo in GENERALISTAS else "esp" if tipo in ESPECIALIZADOS else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("archivo")
    ap.add_argument("--por-medio", type=int, default=8)
    ap.add_argument("--json")
    a = ap.parse_args()
    d = normalizar(json.load(open(a.archivo, encoding="utf-8")))
    ok = [f for f in d["fuentes"] if f["ok"]]
    # tipo de cada cabecera: generalista si alguna de sus fuentes lo es
    tipo_medio = {}
    for f in ok:
        c = clase(f["tipo"])
        if c and tipo_medio.get(f["medio"]) != "gen":
            tipo_medio[f["medio"]] = c
    gen = sorted(m for m, c in tipo_medio.items() if c == "gen")
    esp = sorted(m for m, c in tipo_medio.items() if c == "esp")
    oficiales = [f for f in ok if f["tipo"] == "oficial"]

    print(f"FUENTES LEÍDAS el {d['fecha']} a las {d['hora']}: {len(ok)} de {d['fuentes_total']} con titulares recientes.")
    print(f"  Medios generalistas y agencias ({len(gen)}; son los que cuentan en «Cobertura»):")
    lineas = defaultdict(list)
    for f in ok:
        if clase(f["tipo"]) == "gen" and f["medio"] not in lineas[f["linea"] or "—"]:
            lineas[f["linea"] or "—"].append(f["medio"])
    for l, ms in sorted(lineas.items()):
        print(f"    {l}: {', '.join(ms)}")
    print(f"  Especializados y análisis ({len(esp)}; cuentan aparte): " + ", ".join(esp))
    print("  Verificadores: " + ", ".join(f["nombre"] for f in ok if f["tipo"] == "verificador"))
    print(f"  Oficiales ({len(oficiales)}): " + ", ".join(f["nombre"] for f in oficiales))
    fallan = [f"{f['nombre']} ({f.get('error', '')[:40]})" for f in d["fuentes"] if not f["ok"]]
    if fallan:
        print("  Sin titulares recientes hoy: " + "; ".join(fallan))
    print("  Excluidos del catálogo (no se leen ni se citan): " + "; ".join(f"{k}: {v}" for k, v in EXCLUIDOS.items()))

    prensa = [f for f in ok if clase(f["tipo"])]
    items = [(f["medio"], it["t"], it["u"]) for f in prensa for it in f["items"]]
    temas = agrupar(items)
    for t in temas:
        t["medios_gen"] = [m for m in t["medios"] if tipo_medio.get(m) == "gen"]
        t["medios_esp"] = [m for m in t["medios"] if tipo_medio.get(m) == "esp"]
        t["n"], t["esp"] = len(t["medios_gen"]), len(t["medios_esp"])
    temas.sort(key=lambda t: (-(t["n"] + t["esp"]), -t["n"], -len(t["titulares"])))
    print(f"\nTEMAS CON MÁS COBERTURA (agrupación automática por parecido de los titulares, también entre idiomas; "
          f"de {len(gen)} generalistas y {len(esp)} especializados leídos. Compruébala: puede juntar o separar noticias)")
    for t in [t for t in temas if t["n"] + t["esp"] >= 3][:35]:
        print(f"- {t['n']} generalista{'s' if t['n'] != 1 else ''} + {t['esp']} especializado{'s' if t['esp'] != 1 else ''}"
              f" · claves: {', '.join(t['claves'])}")
        print(f"    generalistas: {', '.join(t['medios_gen']) or '—'} | especializados: {', '.join(t['medios_esp']) or '—'}")
        vistos = set()
        for h in [h for h in t["titulares"] if not (h["medio"] in vistos or vistos.add(h["medio"]))][:4]:
            print(f"    · [{h['medio']}] {h['t'][:150]}")

    radar = [r for r in d.get("radar", []) if r.get("ok")]
    if radar:
        print("\nRADAR AMPLIO (portadas de Google News, que agregan miles de medios). Solo para detectar qué se está contando "
              "y si se nos escapa algo: nunca se cita y no cuenta en «Cobertura». Solo aparecen historias que cuentan al "
              "menos dos medios del catálogo (en el radar local, uno o una institución).")
        def clave(x):
            x = re.sub(r"^www\.|\.(com|es|org|net|co\.uk|fr|de|it)\b.*$", "", norm(x).strip())
            return re.sub(r"[^a-z0-9ñ]", "", x)
        cat = {}
        for f in d["fuentes"]:
            for n in (f["medio"], f["nombre"], f["dominio"]):
                if n and len(clave(n)) > 2:
                    cat[clave(n)] = f["medio"]

        def del_catalogo(nombre):
            k = clave(nombre)
            if k in cat:
                return cat[k]
            for c, m in cat.items():  # «RTVE.es», «EL PAÍS», «Euronews.com»…
                if len(c) > 4 and (k.startswith(c) or c.startswith(k)) and abs(len(k) - len(c)) <= 12:
                    return m
            return None
        vistos = set()
        for r in radar:
            local = r["id"] == "gn_local"
            filas = []
            for it in r["items"]:
                if norm(it["t"]) in vistos:
                    continue
                medios = list(dict.fromkeys(m for m in [it["medio"]] + [x["medio"] for x in it.get("relacionadas", [])] if m))
                de_cat = list(dict.fromkeys(filter(None, (del_catalogo(m) for m in medios))))
                inst = clasificar_dominio(it.get("web") or "") == "oficial"
                if len(de_cat) >= 2 or (local and (de_cat or inst)):
                    vistos.add(norm(it["t"]))
                    filas.append(f"  - {it['t'][:150]} ({it['medio']}) · del catálogo: {', '.join(de_cat) or '—'}")
            if filas:
                print(f"## {r['nombre']}")
                print("\n".join(filas[:8]))

    print("\nPOR BLOQUE: ESPECIALIZADOS Y ANÁLISIS (titulares más recientes de cada uno)")
    for b in BLOQUES:
        fs = [f for f in ok if clase(f["tipo"]) == "esp" and b in f["bloques"]]
        if not fs:
            continue
        print(f"### {b}")
        for f in fs:
            print(f"## {f['nombre']}")
            for it in f["items"][:5]:
                print(f"  - {it['t'][:170]}")

    print(f"\nTITULARES DE LOS GENERALISTAS (los {a.por_medio} más recientes de cada medio español y "
          f"{max(3, a.por_medio // 2)} de cada internacional)")
    for f in [f for f in ok if clase(f["tipo"]) == "gen"]:
        print(f"## {f['nombre']} [{f['linea']}]")
        for it in f["items"][:a.por_medio if "espana" in f["bloques"] else max(3, a.por_medio // 2)]:
            print(f"  - {it['t'][:170]}")
    print("\nVERIFICADORES (bulos desmentidos y comprobaciones)")
    for f in [f for f in ok if f["tipo"] == "verificador"]:
        print(f"## {f['nombre']}")
        for it in f["items"][:5]:
            print(f"  - {it['t'][:170]}")
    print("\nFUENTES OFICIALES Y PRIMARIAS (enlázalas directamente cuando la noticia dependa de ellas)")
    for f in sorted(oficiales, key=lambda f: (BLOQUES.index(f["bloques"][0]) if f["bloques"] and f["bloques"][0] in BLOQUES else 9)):
        print(f"## {f['nombre']} · {', '.join(f['bloques'])}")
        for it in f["items"][:25 if f["id"] == "boe" else 5]:
            print(f"  - {it['t'][:220]}  {it['u'] if 'news.google.com' not in it['u'] else ''}".rstrip())
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"fecha": d["fecha"], "medios_leidos": len(gen), "generalistas_leidos": len(gen),
                       "especializados_leidos": len(esp), "generalistas": gen, "especializados": esp, "temas": temas},
                      fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
