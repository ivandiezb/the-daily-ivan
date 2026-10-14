"""Mapas de situación para los carruseles de Instagram (Internacional y Geopolítica).

mapa_svg(["UKR", "RUS"], ancho, alto) devuelve un <svg> con la región centrada en el primer país (el foco),
pintado en amarillo, los demás países citados en el tono claro de la sección y el resto del mapa en gris
translúcido. Acepta códigos ISO 3166-1 alfa-3 («UKR») o nombres en español («Ucrania», «EE. UU.»).

Datos: Natural Earth 1:50m (dominio público), en la versión TopoJSON de world-atlas (licencia ISC, ver
LICENSE-world-atlas.txt). Solo biblioteca estándar.
"""
import json, math, os, re, unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
_PAISES = None


def _norm(s):
    s = re.sub(r"[.\s]+", " ", (s or "").strip().lower()).strip()
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _cargar():
    global _PAISES
    if _PAISES is not None:
        return _PAISES
    topo = json.load(open(os.path.join(AQUI, "countries-50m.json"), encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcos = []
    for arco in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arco:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcos.append(pts)

    def anillo(indices):
        pts = []
        for i in indices:
            a = arcos[i] if i >= 0 else arcos[~i][::-1]
            pts.extend(a if not pts else a[1:])
        return pts

    paises = {}
    for g in topo["objects"]["countries"]["geometries"]:
        if g.get("id") is None:
            continue
        if g["type"] == "Polygon":
            polis = [g["arcs"]]
        elif g["type"] == "MultiPolygon":
            polis = g["arcs"]
        else:
            continue
        anillos = []
        for p in polis:
            for r in p:
                pts = anillo(r)
                xs = [x for x, _ in pts]
                if max(xs) - min(xs) > 300:  # cruza el antimeridiano (Rusia, Fiyi…): se pasa a 0–360
                    pts = [(x + 360 if x < 0 else x, y) for x, y in pts]
                anillos.append(pts)
        paises[g["id"]] = anillos
    _PAISES = paises
    return paises


def _codigo(c, tabla):
    if not c:
        return None
    if c in tabla:
        return tabla[c]
    n = _norm(c)
    n2 = {"ee uu": "eeuu", "eeuu": "eeuu", "ee uu ": "eeuu", "uk": "reino unido"}.get(n, n)
    return tabla.get(n2) or tabla.get(c.upper())


def _caja(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _area(pts):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def mapa_svg(codigos, ancho, alto, foco="#FFE45C", resalte="rgba(255,255,255,.55)",
             tierra="rgba(255,255,255,.13)", borde="rgba(255,255,255,.32)", margen=0.35, span_min=14.0, clase="mapa"):
    tabla = json.load(open(os.path.join(AQUI, "paises.json"), encoding="utf-8"))
    paises = _cargar()
    ids = []
    for c in codigos or []:
        i = _codigo(c, tabla)
        if i and i in paises and i not in ids:
            ids.append(i)
    if not ids:
        return ""
    # caja del foco: su anillo más grande (evita territorios de ultramar)
    principal = max(paises[ids[0]], key=_area)
    x0, y0, x1, y1 = _caja(principal)
    for i in ids[1:]:  # los demás países solo amplían la vista si están cerca
        bx0, by0, bx1, by1 = _caja(max(paises[i], key=_area))
        nx0, ny0, nx1, ny1 = min(x0, bx0), min(y0, by0), max(x1, bx1), max(y1, by1)
        if nx1 - nx0 <= 70 and ny1 - ny0 <= 45:
            x0, y0, x1, y1 = nx0, ny0, nx1, ny1
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    k = math.cos(math.radians(max(-70, min(70, cy))))
    w = max((x1 - x0) * k, span_min * 1.0) * (1 + 2 * margen)
    h = max((y1 - y0), span_min * 0.7) * (1 + 2 * margen)
    # ajusta a la proporción del hueco
    if w / h > ancho / alto:
        h = w * alto / ancho
    else:
        w = h * ancho / alto
    esc = ancho / w

    def proy(lon, lat):
        return ((lon - cx) * k * esc + ancho / 2, (cy - lat) * esc + alto / 2)

    vlon = (w / k) / 2 + 2
    vlat = h / 2 + 2
    trazos = []
    for pid, anillos in paises.items():
        color = foco if pid == ids[0] else resalte if pid in ids else tierra
        partes = []
        for r in anillos:
            bx0, by0, bx1, by1 = _caja(r)
            if bx1 < cx - vlon or bx0 > cx + vlon or by1 < cy - vlat or by0 > cy + vlat or bx1 - bx0 > 300:
                continue
            pts, ult = [], None
            for lon, lat in r:  # se saltan los puntos a menos de 0,7 px del anterior
                x, y = proy(lon, lat)
                if ult is None or abs(x - ult[0]) + abs(y - ult[1]) > 0.7:
                    pts.append((x, y))
                    ult = (x, y)
            if len(pts) > 2:
                partes.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        if partes:
            trazos.append((pid in ids, f'<path d="{"".join(partes)}" fill="{color}"/>'))
    trazos.sort(key=lambda t: t[0])  # los resaltados, encima
    fx, fy = proy(*_centro(principal))
    marca = (f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="{max(5, ancho / 28):.1f}" fill="none" stroke="{foco}" '
             f'stroke-width="{max(1.2, ancho / 200):.1f}" opacity=".9"/>')
    return (f'<svg class="{clase}" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" aria-hidden="true">'
            f'<g stroke="{borde}" stroke-width=".6" stroke-linejoin="round">{"".join(t for _, t in trazos)}</g>{marca}</svg>')


def _centro(pts):
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-9:
        x0, y0, x1, y1 = _caja(pts)
        return (x0 + x1) / 2, (y0 + y1) / 2
    return cx / (3 * a), cy / (3 * a)
