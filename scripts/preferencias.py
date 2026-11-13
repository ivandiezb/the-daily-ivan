#!/usr/bin/env python3
"""Resume los votos «¿Te interesa?» de los lectores para que la tarea diaria afine la selección de noticias.

Los votos llegan por dos vías:
  · la página de la edición en claude.ai guarda cada voto en su base de datos (colección «votos», un documento por
    edición y noticia: {fecha, code, seccion, titulo, voto: 1 | -1, ts, via}); la tarea los baja con ArtifactData
    («list», con out_dir) a una carpeta;
  · la web pública abre un correo ya escrito con el asunto «[TDI] Me interesa M1 2026-11-08» (o «No me interesa»);
    la tarea los busca en Gmail y guarda el resultado de la búsqueda en un JSON.

Uso:
  python3 scripts/preferencias.py --archivo trabajo/archivo [--db trabajo/votos_db] [--correo trabajo/votos_correo.json]
                                  [--dias 60] [--json trabajo/preferencias.json] [--yo ivandiezberjano@gmail.com]

Imprime un resumen para leer (secciones y temas con más y menos interés, y las noticias votadas) y, con --json, lo
guarda también en ese archivo. Los votos de Iván (los de claude.ai y los que manda desde su correo) pesan 1; los de
otros lectores, 0,5. Los votos pierden la mitad de su peso cada 30 días. Solo biblioteca estándar.
"""
import argparse, glob, json, math, os, re, sys, unicodedata
from collections import defaultdict
from datetime import datetime, timezone

ASUNTO = re.compile(r"\[TDI\]\s*(No me interesa|Me interesa)\s+([A-Z]\d{1,2})\s+(\d{4}-\d{2}-\d{2})", re.I)
CORREO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
VIDA_MEDIA = 30.0
PESO_OTROS = 0.5
STOP = set("""a al algo ante antes con contra como cual cuando de del desde donde dos el ella en entre era es esa ese
esta este esto ha han hasta hay la las le les lo los mas más me mi muy ni no nos o otra otro para pero por que qué se
según ser si sí sin sobre su sus tan te tras tres un una uno unos unas y ya ante hoy ayer año años mil millones
dólares euros puntos tras pese frente nuevo nueva nuevos nuevas primer primera gran sus será son fue sus está están
tiene tienen hace cada todo toda todos todas otros otras parte día días semana mes""".split())


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def leer_json(ruta):
    try:
        return json.load(open(ruta, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cuando(s):
    """Fecha ISO, RFC 2822 de Gmail o milisegundos → datetime con zona, o None."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return datetime.fromtimestamp(s / 1000 if s > 1e11 else s, tz=timezone.utc)
    s = str(s).strip()
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        return None


def votos_db(carpeta):
    """Documentos que ArtifactData guardó con out_dir (o un JSON con la lista)."""
    out = []
    rutas = glob.glob(os.path.join(carpeta, "**", "*.json"), recursive=True) if os.path.isdir(carpeta) else [carpeta]
    for r in rutas:
        j = leer_json(r)
        for d in (j if isinstance(j, list) else [j]):
            if not isinstance(d, dict):
                continue
            if isinstance(d.get("data"), dict):  # {id, version, data: {...}}
                d = d["data"]
            if d.get("fecha") and d.get("code") and d.get("voto") in (1, -1):
                out.append({"fecha": d["fecha"], "code": d["code"], "voto": d["voto"], "quien": "ivan",
                            "ts": cuando(d.get("ts")), "via": "claude.ai", "titulo": d.get("titulo"),
                            "seccion": d.get("seccion")})
    return out


def mensajes_de(j):
    """Recorre el resultado de la búsqueda de Gmail (o una lista ya simplificada) y devuelve los mensajes."""
    if isinstance(j, list):
        for x in j:
            yield from mensajes_de(x)
    elif isinstance(j, dict):
        if any(k in j for k in ("subject", "asunto")):
            yield j
        for k in ("threads", "messages", "mensajes"):
            if isinstance(j.get(k), list):
                yield from mensajes_de(j[k])


def votos_correo(ruta, yo):
    j = leer_json(ruta)
    out, vistos = [], set()
    for m in mensajes_de(j):
        asunto = m.get("subject") or m.get("asunto") or ""
        g = ASUNTO.search(asunto)
        if not g:
            continue
        de = m.get("sender") or m.get("de") or m.get("from") or ""
        if isinstance(de, dict):
            de = de.get("email") or de.get("address") or json.dumps(de)
        mm = CORREO.search(str(de))
        dir_ = mm.group(0) if mm else str(de)
        clave = (m.get("id"), asunto, str(de), str(m.get("date") or m.get("fecha")))
        if clave in vistos:
            continue
        vistos.add(clave)
        out.append({"fecha": g.group(3), "code": g.group(2).upper(), "voto": -1 if g.group(1).lower().startswith("no") else 1,
                    "quien": "ivan" if dir_ and yo and dir_.lower() == yo.lower() else (dir_ or "lector").lower(),
                    "ts": cuando(m.get("date") or m.get("fecha")), "via": "correo"})
    return out


def archivo(carpeta):
    """{fecha: edición} de todos los meses del archivo."""
    ed = {}
    for r in sorted(glob.glob(os.path.join(carpeta, "????-??.json"))):
        j = leer_json(r)
        if isinstance(j, dict):
            ed.update({k: v for k, v in j.items() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", k)})
    return ed


def terminos(titulo):
    """Personas, lugares y organizaciones (palabras con mayúscula fuera del inicio, siglas, cifras con nombre) y
    palabras de contenido del titular, normalizadas."""
    t = re.sub(r"[«»“”\"'()\[\]:;,.¿?¡!]", " ", titulo or "")
    palabras = t.split()
    out, i = [], 0
    while i < len(palabras):
        w = palabras[i]
        if i > 0 and (w[:1].isupper() or (w.isupper() and len(w) > 1)):
            grupo = [w]
            while i + 1 < len(palabras) and (palabras[i + 1][:1].isupper() or palabras[i + 1] in ("de", "del")):
                grupo.append(palabras[i + 1]); i += 1
            while grupo and grupo[-1] in ("de", "del"):
                grupo.pop()
            out.append(" ".join(grupo))
        i += 1
    for w in palabras:
        n = norm(w)
        if len(n) >= 5 and n not in STOP and not n.isdigit():
            out.append(n)
    vistos, res = set(), []
    for x in out:
        k = norm(x)
        if k not in vistos and k not in STOP:
            vistos.add(k); res.append(x)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archivo", required=True, help="carpeta con archivo/AAAA-MM.json")
    ap.add_argument("--db", help="carpeta (o JSON) con los votos de la base de datos de claude.ai")
    ap.add_argument("--correo", help="JSON con el resultado de la búsqueda de Gmail")
    ap.add_argument("--dias", type=int, default=60)
    ap.add_argument("--yo", default="ivandiezberjano@gmail.com")
    ap.add_argument("--json")
    a = ap.parse_args()

    ahora = datetime.now(timezone.utc)
    brutos = (votos_db(a.db) if a.db else []) + (votos_correo(a.correo, a.yo) if a.correo else [])
    # un voto por persona y noticia: el último
    ultimo = {}
    for v in brutos:
        k = (v["fecha"], v["code"], v["quien"])
        if k not in ultimo or (v["ts"] or ahora) >= (ultimo[k]["ts"] or ahora):
            ultimo[k] = v
    eds = archivo(a.archivo)
    sec_tot, ter_tot, ter_n, votadas = defaultdict(float), defaultdict(float), defaultdict(int), []
    n_ivan = n_otros = descartados = 0
    for v in ultimo.values():
        try:
            dias = (ahora - datetime.fromisoformat(v["fecha"]).replace(tzinfo=timezone.utc)).days
        except ValueError:
            continue
        if dias > a.dias:
            continue
        ed = eds.get(v["fecha"]) or {}
        item, seccion = None, v.get("seccion")
        for s in ed.get("secciones", []):
            for it in s.get("items", []):
                if it.get("code") == v["code"]:
                    item, seccion = it, s.get("id")
        titulo = (item or {}).get("titulo") or v.get("titulo")
        if not titulo:
            descartados += 1
            continue
        peso = (1.0 if v["quien"] == "ivan" else PESO_OTROS) * math.pow(0.5, max(dias, 0) / VIDA_MEDIA)
        n_ivan += v["quien"] == "ivan"
        n_otros += v["quien"] != "ivan"
        if seccion:
            sec_tot[seccion] += v["voto"] * peso
        for t in terminos(titulo):
            ter_tot[t] += v["voto"] * peso
            ter_n[t] += 1
        votadas.append({"fecha": v["fecha"], "code": v["code"], "seccion": seccion, "voto": v["voto"],
                        "quien": "Iván" if v["quien"] == "ivan" else "otro lector", "titulo": titulo})

    votadas.sort(key=lambda x: (x["fecha"], x["code"]), reverse=True)
    secs = sorted(sec_tot.items(), key=lambda x: -x[1])
    ters = [(t, round(p, 2), ter_n[t]) for t, p in ter_tot.items() if ter_n[t] >= 2 and abs(p) >= 0.6]
    gustan = sorted([x for x in ters if x[1] > 0], key=lambda x: -x[1])[:12]
    no_gustan = sorted([x for x in ters if x[1] < 0], key=lambda x: x[1])[:12]
    res = {"generado": ahora.isoformat(timespec="minutes"), "dias": a.dias, "votos": len(votadas), "de_ivan": n_ivan,
           "de_otros": n_otros, "secciones": {k: round(p, 2) for k, p in secs}, "temas_que_gustan": gustan,
           "temas_que_no": no_gustan, "noticias": votadas[:40]}

    print(f"PREFERENCIAS DE LOS LECTORES (votos «¿Te interesa?» de los últimos {a.dias} días: {len(votadas)}; "
          f"{n_ivan} de Iván y {n_otros} de otros lectores, que pesan la mitad; los votos pierden la mitad de su peso "
          f"cada {int(VIDA_MEDIA)} días)" + (f"; {descartados} sin noticia identificable" if descartados else ""))
    if not votadas:
        print("- Aún no hay votos: selecciona como siempre.")
    else:
        if secs:
            print("- Secciones (positivo = más interés): " + ", ".join(f"{k} {p:+.1f}" for k, p in secs))
        if gustan:
            print("- Temas que interesan: " + ", ".join(f"{t} ({p:+.1f}, {n} votos)" for t, p, n in gustan))
        if no_gustan:
            print("- Temas que interesan menos: " + ", ".join(f"{t} ({p:+.1f}, {n} votos)" for t, p, n in no_gustan))
        print("- Noticias votadas (las más recientes primero):")
        for x in votadas[:25]:
            print(f"    {'👍' if x['voto'] > 0 else '👎'} {x['fecha']} {x['code']} [{x['seccion'] or '?'}] {x['titulo'][:110]}"
                  + ("" if x["quien"] == "Iván" else " (otro lector)"))
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
