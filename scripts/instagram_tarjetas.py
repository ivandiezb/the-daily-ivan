#!/usr/bin/env python3
"""Genera las publicaciones de Instagram de una edición de The Daily Iván.

Uso:
  python3 scripts/instagram_tarjetas.py <page.html> --imagenes DIR --cola DIR
          [--extra ig.json] [--usuario allyouneedisnews] [--base-url URL] [--horas 09:30,12:00,...]
          [--tipo fraunces|bricolage]

Por cada bloque (Las 5 claves y cada sección) crea un carrusel de imágenes JPEG de 1080×1350:
una portada y una imagen por noticia; Mercados añade el panel de cotizaciones. Escribe:
  <imagenes>/<AAAA-MM-DD>/<bloque>-<n>.jpg
  <cola>/<AAAA-MM-DD>/cola.json   (hora, texto, hashtags y URL pública de cada imagen)

Diseño: cada sección tiene su color (SECCION), con luz y grano de papel y la marca «The Daily Iván». Titulares en
Bricolage Grotesque (o Fraunces con --tipo fraunces). Cada noticia es una imagen con titular (con una frase resaltada
en amarillo), un mapa de situación si la noticia trae países, una cifra protagonista si trae «dato»,
un texto explicativo de dos párrafos y «La clave» (una línea fina con el color claro de la sección). Mercados añade
barras de subida y bajada. Los mapas salen de scripts/mapa (Natural Earth).

Textos: se pasan con --extra (ig.json) o dentro de la edición como objeto "instagram":
  {"bloques": {"<id>": {"gancho": "...", "copy": "...", "hashtags": ["#..."]}},
   "items":   {"M1": {"titular": "...", "destacado": "...", "texto": "párrafo 1\n\npárrafo 2", "clave": "...",
                      "paises": ["UKR", "RUS"], "dato": {"cifra": "19 años", "pie": "sin que …"}}}}
  titular ≤ 80 caracteres; destacado = trozo literal del titular que se resalta (opcional); texto de 450 a 700
  caracteres en dos párrafos (qué ha pasado, con datos; y contexto); clave = una o dos frases (≤ 190) con la lectura
  de fondo o lo que viene; paises = códigos ISO alfa-3 (el primero es el foco del mapa); dato = cifra corta (≤ 10
  caracteres) y su explicación (≤ 70). Si faltan, se condensan de la propia edición (frases completas, sin referencias personales).
"""
import argparse, html, json, os, re, sys, tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapa import mapa_svg  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "fuentes")
# Las imágenes de cada día van en su propia rama, instagram-media-AAAA-MM-DD (una rama nueva se sube sin forzar;
# GitHub Actions borra las de más de dos días).
REPO_RAW = "https://raw.githubusercontent.com/ivandiezb/the-daily-ivan/instagram-media-{fecha}"
ORDEN = ["claves", "espana", "mercados", "internacional", "geopolitica", "vivienda", "inversion", "naturaleza"]
HORAS = ["09:30", "12:00", "13:30", "15:00", "16:30", "18:00", "19:30", "21:00"]
ETIQUETAS = {  # etiquetas de fondo de cada sección, por orden de preferencia (Instagram admite 5 por publicación)
    "claves": ["#noticias", "#actualidad", "#news", "#noticiasdehoy", "#España"],
    "espana": ["#España", "#política", "#Spain", "#noticias", "#actualidad"],
    "mercados": ["#bolsa", "#economía", "#stockmarket", "#mercados", "#finanzas"],
    "inversion": ["#inversión", "#bolsa", "#investing", "#finanzas", "#stocks"],
    "geopolitica": ["#geopolítica", "#internacional", "#worldnews", "#geopolitics", "#noticias"],
    "internacional": ["#internacional", "#noticias", "#worldnews", "#news", "#actualidad"],
    "vivienda": ["#Madrid", "#vivienda", "#empleo", "#noticias", "#actualidad"],
    "naturaleza": ["#clima", "#medioambiente", "#climatechange", "#naturaleza", "#noticias"]}
NO_ETIQUETAS = {"#thedailyivan", "#thedailyiván", "#dailyivan"}
CONF = {"confirmado": "confirmada por varias fuentes o por fuente oficial", "una-fuente": "una sola fuente",
        "en-desarrollo": "en desarrollo, puede cambiar", "seguimiento": "seguimiento de una noticia anterior",
        "agenda": "previsto hoy, sin resultado conocido"}
SECCION = {  # color de fondo de cada sección y su tono claro (número, etiqueta y línea de «La clave»)
    "claves": ("#141B23", "#FFE45C"), "espana": ("#1E3A66", "#9DBDF2"), "mercados": ("#0D5A60", "#86DCD4"),
    "internacional": ("#4B2A7B", "#CDB1F5"), "geopolitica": ("#7A1F1A", "#F4A9A1"), "vivienda": ("#8A4510", "#F7C48C"),
    "inversion": ("#73204F", "#F2ACD0"), "naturaleza": ("#24563A", "#A3DCB4")}
# Frases que solo tienen sentido para el lector privado (Iván) y no deben salir en público.
PRIVADO = re.compile(r"mencionabas|pide el informe|informe ampliado|Profundizar|amplía [A-Z]\d|"
                     r"si estás valorando|tu cartera|te interesa|como pediste|me pediste", re.I)
ABREV = {"EE.", "UU.", "Sr.", "Sra.", "Dr.", "Dra.", "núm.", "art.", "pág.", "aprox.", "vs.", "etc.", "S.", "St."}
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def e(s):
    return html.escape(str(s or ""), quote=True)


def nb(s):
    """Escapa y evita cortes de línea dentro de expresiones cortas con guion (29-N, G-7, COVID-19)."""
    return re.sub(r"(?<![\w-])([\w.]{1,6}-[\w.]{1,6})(?![\w-])", r'<span style="white-space:nowrap">\1</span>', e(s))


def oraciones(t):
    t = re.sub(r"\s+", " ", (t or "").strip())
    if not t:
        return []
    trozos = re.split(r"(?<=[.!?…])([»”\")]?)\s+(?=[¿¡«\"“(A-ZÁÉÍÓÚÑ0-9])", t)
    # re.split con grupo intercala el cierre capturado; se vuelve a pegar a su frase
    frases, i = [], 0
    while i < len(trozos):
        f = trozos[i] + (trozos[i + 1] if i + 1 < len(trozos) else "")
        i += 2
        if frases:
            ult = frases[-1].split(" ")[-1]
            if ult in ABREV or re.fullmatch(r"[A-ZÁÉÍÓÚÑ]\.", ult):
                frases[-1] += " " + f
                continue
        frases.append(f)
    return frases


REF_INTERNA = re.compile(r"\s*\((?:véase |ver )?[A-Z]\d{1,2}(?: del \d{1,2}| de ayer)?\)")


def condensa(t, maxc):
    """Frases completas hasta ~maxc caracteres, descartando las de uso privado."""
    out, n = [], 0
    t = REF_INTERNA.sub("", (t or "").replace("(interpretación mía)", "(interpretación propia)"))
    for f in oraciones(t):
        if PRIVADO.search(f):
            # «Es el tipo de escalada que mencionabas: la escasez…» → se conserva lo que va tras los dos puntos
            pre, sep, resto = f.partition(": ")
            if sep and PRIVADO.search(pre) and not PRIVADO.search(resto) and len(resto) > 40:
                f = resto[0].upper() + resto[1:]
            else:
                continue
        if out and n + len(f) > maxc:
            break
        out.append(f)
        n += len(f) + 1
    return out


def num(x, dec):
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 else "") + s


def fecha_corta(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]} {d.year}"


def iconos(src):
    m = re.search(r"var ICONS = (\{.*?\});", src)
    return json.loads(m.group(1)) if m else {}


def svg(path):
    return (f'<svg viewBox="0 0 24 24" aria-hidden="true">{path}</svg>' if path else "")


CSS = """
@font-face{font-family:Archivo;font-weight:500;src:url("F/archivo-latin-500-normal.woff2")}
@font-face{font-family:Archivo;font-weight:600;src:url("F/archivo-latin-600-normal.woff2")}
@font-face{font-family:Archivo;font-weight:700;src:url("F/archivo-latin-700-normal.woff2")}
@font-face{font-family:Archivo;font-weight:800;src:url("F/archivo-latin-800-normal.woff2")}
@font-face{font-family:"Source Serif 4";font-weight:400;src:url("F/source-serif-4-latin-400-normal.woff2")}
@font-face{font-family:"Source Serif 4";font-weight:600;src:url("F/source-serif-4-latin-600-normal.woff2")}
@font-face{font-family:"Source Serif 4";font-weight:400;font-style:italic;src:url("F/source-serif-4-latin-400-italic.woff2")}
@font-face{font-family:"JetBrains Mono";font-weight:500;src:url("F/jetbrains-mono-latin-500-normal.woff2")}
@font-face{font-family:"JetBrains Mono";font-weight:700;src:url("F/jetbrains-mono-latin-700-normal.woff2")}
@font-face{font-family:Fraunces;font-weight:600;src:url("F/fraunces-latin-600-normal.woff2")}
@font-face{font-family:Fraunces;font-weight:800;src:url("F/fraunces-latin-800-normal.woff2")}
@font-face{font-family:Fraunces;font-weight:900;src:url("F/fraunces-latin-900-normal.woff2")}
@font-face{font-family:Bricolage;font-weight:500;src:url("F/bricolage-grotesque-latin-500-normal.woff2")}
@font-face{font-family:Bricolage;font-weight:700;src:url("F/bricolage-grotesque-latin-700-normal.woff2")}
@font-face{font-family:Bricolage;font-weight:800;src:url("F/bricolage-grotesque-latin-800-normal.woff2")}
body.fraunces{--disp:Fraunces;--dw:800;--tt:30px;--ls:-.3px}
body.bricolage{--disp:Bricolage;--dw:800;--tt:31px;--ls:-.7px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#777;font-family:Archivo,Arial,sans-serif}
.slide{width:540px;height:675px;margin:0 0 10px;overflow:hidden;display:flex;flex-direction:column;
  background:var(--sec);color:#fff;padding:28px 32px 20px}
.top{display:flex;justify-content:space-between;align-items:center;flex:none}
.brand{font:800 10.5px/1 Archivo;letter-spacing:2.4px;text-transform:uppercase;background:#FFE45C;color:#1d1a00;padding:6px 9px 5px;border-radius:4px}
.date{font:500 10.5px/1 "JetBrains Mono";letter-spacing:.4px;text-transform:uppercase;opacity:.75}
.lab{margin-top:18px;display:flex;align-items:center;gap:10px;flex:none}
.lab .n{font:800 27px/1 Archivo;color:transparent;-webkit-text-stroke:1.2px var(--acc);letter-spacing:-.5px}
.lab .s{font:800 11px/1.2 Archivo;letter-spacing:2.4px;text-transform:uppercase;color:var(--acc)}
.lab .k{margin-left:auto;font:500 10.5px/1 "JetBrains Mono";opacity:.65}
.body{--s:1;flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;margin-top:12px}
.ttl{font:800 calc(29px*var(--s))/1.08 Archivo;letter-spacing:-.5px;flex:none}
mark{background:#FFE45C;color:var(--sec);padding:0 .12em;border-radius:3px;-webkit-box-decoration-break:clone;box-decoration-break:clone}
.txt{margin-top:calc(13px*var(--s));font:400 calc(17.5px*var(--s))/1.46 "Source Serif 4";color:rgba(255,255,255,.93);flex:none}
.txt p+p{margin-top:calc(9px*var(--s))}
.hueco{flex:1;min-height:calc(16px*var(--s))}
.clave{flex:none;border-left:3px solid var(--acc);padding:calc(3px*var(--s)) 0 calc(3px*var(--s)) 14px}
.clave .h{display:flex;align-items:center;gap:7px;font:800 calc(10px*var(--s))/1 Archivo;letter-spacing:2.2px;text-transform:uppercase;color:var(--acc);margin-bottom:calc(7px*var(--s))}
.clave .h svg{width:14px;height:14px;fill:none;stroke:var(--acc);stroke-width:2;stroke-linecap:round;stroke-linejoin:round;opacity:.75}
.clave p{font:600 calc(15.5px*var(--s))/1.38 Archivo;color:rgba(255,255,255,.95)}
.pie{margin-top:12px;display:flex;justify-content:space-between;gap:18px;font:500 10.5px/1.3 Archivo;opacity:.72;flex:none}
.pie span:first-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pie span:last-child{white-space:nowrap}
/* identidad: luz, grano, marca, mapas, dato */
.slide{position:relative;background:radial-gradient(130% 75% at 100% 0%,rgba(255,255,255,.11),rgba(255,255,255,0) 60%),var(--sec)}
.slide::after{content:"";position:absolute;inset:0;z-index:0;pointer-events:none;opacity:.13;mix-blend-mode:overlay;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 .55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>")}
.slide>*{position:relative;z-index:1}
.marca{display:flex;align-items:center;gap:9px;font:var(--dw) 16.5px/1 var(--disp);letter-spacing:-.2px}
.marca i{width:9px;height:9px;background:#FFE45C;transform:rotate(45deg);flex:none}
.ttl{font:var(--dw) calc(var(--tt)*var(--s))/1.07 var(--disp);letter-spacing:var(--ls)}
.minimapa{float:right;width:136px;height:102px;margin:4px 0 8px 14px;border-radius:10px;overflow:hidden;background:rgba(0,0,0,.16);box-shadow:inset 0 0 0 1px rgba(255,255,255,.2)}
.minimapa svg,.mapa-portada svg{display:block;width:100%;height:100%}
.mapa-portada{flex:none;height:196px;margin-top:12px;border-radius:12px;overflow:hidden;background:rgba(0,0,0,.16);box-shadow:inset 0 0 0 1px rgba(255,255,255,.18)}
.dato{display:flex;gap:14px;align-items:center;margin-top:calc(12px*var(--s));padding:calc(9px*var(--s)) 0;border-top:1px solid rgba(255,255,255,.22);border-bottom:1px solid rgba(255,255,255,.22);flex:none}
.dato b{font:900 calc(44px*var(--s))/1 var(--disp);color:#FFE45C;letter-spacing:-1px;white-space:nowrap}
.dato span{font:600 calc(14.5px*var(--s))/1.35 Archivo;opacity:.92}
.mk .bar{width:74px;padding-left:12px}
.barra{display:block;position:relative;height:8px;background:rgba(255,255,255,.09);border-radius:4px}
.barra::before{content:"";position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:rgba(255,255,255,.45)}
.barra i{position:absolute;top:0;bottom:0;border-radius:4px}
/* portadas */
.hook{margin-top:calc(14px*var(--s));font:var(--dw) calc(40px*var(--s))/1.04 var(--disp);letter-spacing:var(--ls);flex:none}
.lst{list-style:none;flex:none}
.lst li{display:flex;gap:12px;align-items:baseline;font:600 calc(16px*var(--s))/1.3 Archivo;padding:calc(9px*var(--s)) 0;border-top:1px solid rgba(255,255,255,.2)}
.lst li em{font:800 calc(14px*var(--s))/1.3 Archivo;font-style:normal;color:var(--acc);width:22px;flex:none}
.big{margin-top:24px;font:900 210px/.8 var(--disp);color:#FFE45C;letter-spacing:-8px;flex:none}
.sub{margin-top:14px;font:var(--dw) calc(40px*var(--s))/1.03 var(--disp);letter-spacing:var(--ls);flex:none}
/* las 5 claves */
.ctx{margin-top:calc(14px*var(--s));font:400 calc(20px*var(--s))/1.45 "Source Serif 4";color:rgba(255,255,255,.93);flex:none}
.mas{flex:none;display:flex;align-items:center;gap:8px;font:600 calc(14px*var(--s))/1.35 Archivo;color:var(--acc)}
/* mercados */
.mk{width:100%;border-collapse:collapse;font:600 calc(15px*var(--s))/1.2 Archivo;flex:none;margin-top:4px}
.mk td{padding:calc(7.5px*var(--s)) 0;border-bottom:1px solid rgba(255,255,255,.16)}
.mk tr:last-child td{border-bottom:0}
.mk .v,.mk .c{text-align:right;font-family:"JetBrains Mono";font-weight:500;font-size:calc(13.5px*var(--s));white-space:nowrap}
.mk .c{width:84px}
.mk .u{font:500 calc(10.5px*var(--s)) Archivo;opacity:.65}
.up{color:#8EE6A8}.down{color:#FF9C94}.flat{opacity:.7}
.nota{flex:none;font:400 calc(13.5px*var(--s))/1.4 "Source Serif 4";color:rgba(255,255,255,.8)}
"""

FIT_JS = r"""
() => {
  const over = el => el.scrollHeight > el.clientHeight + 1;
  const report = [];
  for (const slide of document.querySelectorAll('.slide')) {
    const body = slide.querySelector('.body'); let s = 1, trimmed = 0;
    if (body) {
      const fit = () => { s = parseFloat(body.dataset.grow || 1.12); body.style.setProperty('--s', s);
        while (over(body) && s > 0.8) { s = Math.round((s - 0.02) * 1000) / 1000; body.style.setProperty('--s', s); } };
      fit();
      while (over(body)) { // si ni así cabe, se quita la última frase del texto más largo
        const ps = [...body.querySelectorAll('.txt p, .ctx')].filter(p => p.querySelectorAll('.f').length > 1)
          .sort((a, b) => b.textContent.length - a.textContent.length);
        if (!ps.length) break;
        const fs = ps[0].querySelectorAll('.f'); fs[fs.length - 1].remove(); trimmed++; fit();
      }
    }
    report.push({id: slide.id, s, dropped: 0, trimmed, overflow: (body && over(body)) || over(slide)});
  }
  return report;
}
"""

LLAVE = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3 20 3"/><path d="M16 7l3 3"/><path d="M13.5 9.5l2 2"/></svg>'


NOWRAP = re.compile(r"(?<![\w-])([\w.]{1,6}-[\w.]{1,6})(?![\w-])")


def titular_html(t, destacado=""):
    """Titular escapado, con la frase destacada (si aparece tal cual) resaltada en amarillo."""
    esc = e(t)
    if destacado and e(destacado) in esc:
        esc = esc.replace(e(destacado), "\x00" + e(destacado) + "\x01", 1)
    esc = NOWRAP.sub(r'<span style="white-space:nowrap">\1</span>', esc)
    return esc.replace("\x00", "<mark>").replace("\x01", "</mark>")


def frases_html(frases):
    return " ".join(f'<span class="f">{nb(f)}</span>' for f in frases)


def medios_de(it, maximo=3):
    """Nombres de los medios citados («Europa Press · El Mundo · Infodefensa»), sin el titular de cada enlace."""
    nombres = []
    for f in it.get("fuentes", []):
        n = (f.get("t") or "").split(":")[0].strip()
        if n and n not in nombres:
            nombres.append(n)
    return " · ".join(nombres[:maximo])


def etiquetas_de(bid, propuestas, maximo=5):
    """Hasta 2 etiquetas del tema del día (las propone la tarea diaria) y el resto, las de fondo de la sección."""
    fondo = ETIQUETAS.get(bid, ETIQUETAS["claves"])
    base = {t.lower() for t in fondo}
    tema = []
    for t in propuestas or []:
        t = re.sub(r"\s+", "", t if t.startswith("#") else "#" + t)
        if len(t) > 1 and t.lower() not in NO_ETIQUETAS and t.lower() not in base and t.lower() not in {x.lower() for x in tema}:
            tema.append(t)
    out = tema[:2]
    for t in fondo:
        if len(out) >= maximo:
            break
        if t.lower() not in {x.lower() for x in out}:
            out.append(t)
    return out


def texto_publicacion(bid, gancho, copy, titulares, etiquetas):
    partes = [gancho.strip()]
    if copy and copy.strip():
        partes += ["", copy.strip()]
    partes += ["", "Las cinco claves:" if bid == "claves" else "En este carrusel:"]
    partes += [f"{i + 1}. {t}" for i, t in enumerate(titulares)]
    partes += ["", "Desliza para leer cada noticia y su clave."]
    if bid == "inversion":
        partes += ["Contenido informativo; no es una recomendación de inversión."]
    partes += ["", "Resumen elaborado a partir de las fuentes citadas. La edición completa, con el enlace a cada fuente, "
               "está en el enlace de la bio.", "", " ".join(etiquetas)]
    texto = "\n".join(partes)
    if len(texto) > 2200:
        raise SystemExit(f"{bid}: el texto supera los 2.200 caracteres de Instagram ({len(texto)})")
    return texto


def parrafo(frases, opt=False):
    if not frases:
        return ""
    inner = " ".join(f'<span class="f">{e(f)}</span>' for f in frases)
    return f'<p class="p"{" data-opt" if opt else ""}>{inner}</p>'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page")
    ap.add_argument("--imagenes", required=True)
    ap.add_argument("--cola", required=True)
    ap.add_argument("--extra", help="JSON con el objeto 'instagram' si no viene dentro de la edición")
    ap.add_argument("--usuario", default="allyouneedisnews")
    ap.add_argument("--base-url", default=REPO_RAW,
                    help="URL pública bajo la que quedarán <AAAA-MM-DD>/<archivo>.jpg ({fecha} se sustituye por la fecha)")
    ap.add_argument("--horas", default=",".join(HORAS))
    ap.add_argument("--tipo", default="bricolage", choices=["fraunces", "bricolage"], help="tipografía de los titulares")
    a = ap.parse_args()

    src = open(a.page, encoding="utf-8").read()
    d = json.loads(re.search(r'<script type="application/json" id="edition">(.*?)</script>', src, re.S).group(1))
    ig = d.get("instagram") or {}
    if a.extra:
        ig = json.load(open(a.extra, encoding="utf-8"))
    igb, igi = ig.get("bloques", {}), ig.get("items", {})
    ico = iconos(src)
    fecha = d["fechaISO"]
    fcorta = fecha_corta(fecha)
    handle = "@" + a.usuario.lstrip("@")
    sec_de = {it["code"]: s for s in d["secciones"] for it in s["items"]}
    item_de = {it["code"]: it for s in d["secciones"] for it in s["items"]}

    def publico(t):
        t = (t or "").replace("(interpretación mía)", "(interpretación propia)").replace("interpretación mía", "interpretación propia")
        return REF_INTERNA.sub("", t)

    def texto_item(code):
        """Titular, frase destacada, párrafos y clave de una noticia: los de ig.json o, si faltan, condensados de la edición."""
        it, ov = item_de[code], igi.get(code, {})
        if ov.get("texto"):
            parrafos = [publico(x) for x in re.split(r"\n\s*\n", ov["texto"])]
        elif ov.get("hecho") or ov.get("importa"):
            parrafos = [publico(ov.get("hecho")), publico(ov.get("importa"))]
        else:
            parrafos = [" ".join(condensa(it.get("hecho"), 420)), " ".join(condensa(it.get("importa"), 260))]
        if ov.get("clave"):
            clave, etiqueta = publico(ov["clave"]), "La clave"
        else:  # sin clave escrita, se usa lo que hay que vigilar, con su nombre
            clave, etiqueta = publico(ov.get("vigilar")) or " ".join(condensa(it.get("vigilar"), 180)), "A vigilar"
        dato = ov.get("dato") if isinstance(ov.get("dato"), dict) and ov["dato"].get("cifra") else None
        return {"titular": ov.get("titular") or ov.get("titulo") or it["titulo"], "destacado": ov.get("destacado") or "",
                "texto": [x for x in parrafos if x and x.strip()], "clave": clave, "etiqueta": etiqueta,
                "paises": [p for p in (ov.get("paises") or []) if isinstance(p, str)], "dato": dato}


    bloques = [{"id": "claves", "titulo": "Las 5 claves", "claves": d.get("claves", [])}]
    for s in d["secciones"]:
        bloques.append({"id": s["id"], "titulo": s["titulo"], "corto": s.get("corto"), "items": s["items"]})
    rango = {b: i for i, b in enumerate(ORDEN)}
    fuera = [b["id"] for b in bloques if b["id"] not in rango]
    if fuera:  # p. ej. «deportes»: está en la newsletter y en la web, pero no tiene carrusel propio
        print(f"Sin carrusel en Instagram (no están en ORDEN): {', '.join(fuera)}", file=sys.stderr)
    bloques = sorted((b for b in bloques if b["id"] in rango), key=lambda b: rango[b["id"]])
    horas = [h.strip() for h in a.horas.split(",") if h.strip()]
    if len(bloques) > len(horas):
        print(f"Aviso: {len(bloques)} bloques y {len(horas)} horas; se omiten: "
              f"{', '.join(b['id'] for b in bloques[len(horas):])}", file=sys.stderr)
        bloques = bloques[:len(horas)]

    slides, posts = [], []
    hora_de = {b["id"]: h for b, h in zip(bloques, horas)}
    for b, hora in zip(bloques, horas):
        bid = b["id"]
        sec_c, acc_c = SECCION.get(bid, SECCION["claves"])
        style = f'style="--sec:{sec_c};--acc:{acc_c}"'
        o = igb.get(bid, {})
        top = (f'<div class="top"><span class="marca"><i></i>The Daily Iván</span>'
               f'<span class="date">{e(fcorta)}</span></div>')
        files = []

        def add(html_slide):
            n = len(files) + 1
            sid = f"{bid}-{n}"
            files.append(f"{sid}.jpg")
            slides.append(html_slide.replace("§ID§", sid))

        def pie(izq, der=None):
            return f'<div class="pie"><span>{izq}</span><span>{der or e(handle)}</span></div>'

        if bid == "claves":
            claves = b["claves"][:5]
            gancho = o.get("gancho") or f"claves para entender el {DIAS[datetime.strptime(fecha, '%Y-%m-%d').weekday()]}"
            lista = "".join(f'<li><em>{i + 1}</em><span>{nb(texto_item(k.get("ref"))["titular"] if k.get("ref") in item_de else k["t"])}</span></li>'
                            for i, k in enumerate(claves))
            titulos = [texto_item(k["ref"])["titular"] if k.get("ref") in item_de else k["t"] for k in claves]
            add(f'<section class="slide portada" id="§ID§" {style}>{top}<div class="big">{len(claves)}</div>'
                f'<div class="body" data-grow="1"><div class="sub">{nb(gancho)}</div><div class="hueco"></div>'
                f'<ul class="lst">{lista}</ul></div>{pie(e(handle), "Desliza →")}</section>')
            for i, k in enumerate(claves):
                ref = k.get("ref")
                sec = sec_de.get(ref)
                t = texto_item(ref) if ref in item_de else {"titular": k["t"], "destacado": ""}
                corto = (sec.get("corto") or sec["titulo"]) if sec else "Las claves"
                acc_k = SECCION.get(sec["id"], SECCION["claves"])[1] if sec else acc_c
                mas = (f'<div class="mas">→ Más, en el carrusel de {e(corto)} ({hora_de[sec["id"]]})</div>'
                       if sec and sec["id"] in hora_de else "")
                add(f'<section class="slide" id="§ID§" style="--sec:{sec_c};--acc:{acc_k}">{top}'
                    f'<div class="lab"><span class="n">{i + 1:02d}</span><span class="s">{e(corto)}</span>'
                    f'<span class="k">{i + 1}/{len(claves)}</span></div>'
                    f'<div class="body" data-grow="1.35"><h2 class="ttl">{titular_html(t["titular"], t.get("destacado"))}</h2>'
                    f'<div class="ctx">{frases_html(oraciones(k["t"]))}</div><div class="hueco"></div>{mas}</div>'
                    f'{pie(e(handle), "")}</section>')
        else:
            items = b["items"]
            corto = b.get("corto") or b["titulo"]
            lead = texto_item(items[0]["code"])
            gancho = o.get("gancho") or lead["titular"]
            titulos = [texto_item(it["code"])["titular"] for it in items]
            lista = "".join(f'<li><em>{i + 1:02d}</em><span>{nb(t)}</span></li>' for i, t in enumerate(titulos[:4]))
            con_pais = next((texto_item(it["code"])["paises"] for it in items if texto_item(it["code"])["paises"]), [])
            mapa = mapa_svg(con_pais, 476, 196, resalte=acc_c) if con_pais else ""
            add(f'<section class="slide portada" id="§ID§" {style}>{top}'
                f'<div class="lab"><span class="s">{e(b["titulo"])}</span></div>'
                f'<div class="body" data-grow="1.1">{('<div class="mapa-portada">' + mapa + '</div>') if mapa else ""}'
                f'<div class="hook">{nb(gancho)}</div><div class="hueco"></div>'
                f'<ul class="lst">{lista}</ul></div>{pie(e(handle), "Desliza →")}</section>')

            if bid == "mercados" and d.get("mercados"):
                filas = []
                maxc = max([abs(m["c"]) for m in d["mercados"] if m.get("c") is not None] or [1]) or 1
                for m in d["mercados"]:
                    tp, v, dec, c = m.get("tipo"), m["v"], m.get("dec", 2), m.get("c")
                    if tp == "indice":
                        val = f'{num(v, dec)} <span class="u">pts</span>'
                    elif tp == "rent":
                        val = f'{num(v, dec)} <span class="u">%</span>'
                    elif tp == "divisa":
                        val = f'{num(v, 4)} <span class="u">$/€</span>'
                    else:
                        val = f'{num(v, dec)} <span class="u">${("/" + m["por"]) if m.get("por") else ""}</span>'
                    if c is None:
                        ch = '<span class="flat">—</span>'
                    else:
                        cls = "up" if c > 0 else "down" if c < 0 else "flat"
                        ch = f'<span class="{cls}">{"+" if c > 0 else ""}{num(c, 2)} %</span>'
                    if c:
                        ancho = min(50, abs(c) / maxc * 50)
                        lado = f"left:50%;width:{ancho:.1f}%" if c > 0 else f"left:{50 - ancho:.1f}%;width:{ancho:.1f}%"
                        barra = f'<span class="barra"><i style="{lado};background:{"#8EE6A8" if c > 0 else "#FF9C94"}"></i></span>'
                    else:
                        barra = '<span class="barra"></span>'
                    filas.append(f'<tr><td>{e(m["n"])}</td><td class="v">{val}</td><td class="c">{ch}</td><td class="bar">{barra}</td></tr>')
                fx = d.get("fx") or {}
                add(f'<section class="slide" id="§ID§" {style}>{top}'
                    f'<div class="lab"><span class="s">Panel de mercados</span><span class="k">{e(fx.get("s", "").split("·")[0].strip())}</span></div>'
                    f'<div class="body" data-grow="1.08"><table class="mk">{"".join(filas)}</table><div class="hueco"></div>'
                    f'<p class="nota">Cifras de prensa económica, orientativas: no son cotizaciones en tiempo real. '
                    f'Los bonos, en rentabilidad anual.</p></div>{pie(e(handle), "")}</section>')

            for i, it in enumerate(items):
                t = texto_item(it["code"])
                clave = (f'<div class="clave"><div class="h">{LLAVE}<span>{e(t["etiqueta"])}</span></div>'
                         f'<p>{frases_html(oraciones(t["clave"]))}</p></div>') if t["clave"] else ""
                parrafos = "".join(f'<p>{frases_html(oraciones(p))}</p>' for p in t["texto"] if p.strip())
                medios = medios_de(it)
                aviso = "Contenido informativo, no es una recomendación de inversión" if bid == "inversion" else ""
                izq = e(aviso) if aviso else (e("Fuentes: " + medios) if medios else "")
                mini = mapa_svg(t["paises"], 136, 102, resalte=acc_c, span_min=10.0, margen=0.45) if t["paises"] else ""
                mini = f'<div class="minimapa">{mini}</div>' if mini else ""
                dato = (f'<div class="dato"><b>{nb(t["dato"]["cifra"])}</b><span>{nb(t["dato"].get("pie", ""))}</span></div>'
                        if t["dato"] else "")
                add(f'<section class="slide" id="§ID§" {style}>{top}'
                    f'<div class="lab"><span class="n">{i + 1:02d}</span><span class="s">{e(corto)}</span>'
                    f'<span class="k">{i + 1}/{len(items)}</span></div>'
                    f'<div class="body" data-grow="1.22"><div>{mini}<h2 class="ttl">{titular_html(t["titular"], t.get("destacado"))}</h2></div>'
                    f'{dato}<div class="txt">{parrafos}</div><div class="hueco"></div>{clave}</div>'
                    f'{pie(izq)}</section>')

        # texto de la publicación
        tags = etiquetas_de(bid, o.get("hashtags"))
        texto = texto_publicacion(bid, gancho if bid != "claves" else f"{len(claves)} {gancho}", o.get("copy"), titulos, tags)
        posts.append({"id": f"{fecha}-{bid}", "bloque": bid, "hora": hora, "texto": texto, "hashtags": tags,
                      "imagenes": [f"{a.base_url.format(fecha=fecha).rstrip('/')}/{fecha}/{f}" for f in files], "archivos": files})

    for p in posts:
        if not 2 <= len(p["imagenes"]) <= 10:
            raise SystemExit(f"{p['id']}: un carrusel admite de 2 a 10 imágenes ({len(p['imagenes'])})")

    # render
    out_img = os.path.join(a.imagenes, fecha)
    os.makedirs(out_img, exist_ok=True)
    css = CSS.replace('url("F/', 'url("file://' + FUENTES + "/")
    doc = f'<!doctype html><html lang="es"><head><meta charset="utf-8"><style>{css}</style></head><body class="{a.tipo}">{"".join(slides)}</body></html>'
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "tarjetas.html")
        open(path, "w", encoding="utf-8").write(doc)
        with sync_playwright() as pw:
            br = pw.chromium.launch()
            pg = br.new_page(viewport={"width": 560, "height": 700}, device_scale_factor=2)
            pg.goto("file://" + path)
            pg.evaluate("Promise.allSettled([...document.fonts].map(f => f.load())).then(() => document.fonts.ready).then(() => true)")
            faltan = pg.evaluate("[...document.fonts].filter(f => f.status !== 'loaded').map(f => f.family + ' ' + f.weight)")
            if faltan:
                raise SystemExit("No se han cargado las fuentes: " + ", ".join(faltan))
            informe = pg.evaluate(FIT_JS)
            for r in informe:
                pg.locator(f"#{r['id']}").screenshot(path=os.path.join(out_img, r["id"] + ".jpg"), type="jpeg", quality=88)
            br.close()
    malos = [r for r in informe if r["overflow"]]
    for r in informe:
        if r["dropped"] or r["trimmed"] or r["s"] < 1:
            print(f"  ajuste {r['id']}: escala {r['s']}, secciones quitadas {r['dropped']}, frases quitadas {r['trimmed']}", file=sys.stderr)
    if malos:
        raise SystemExit("No caben: " + ", ".join(r["id"] for r in malos))

    out_cola = os.path.join(a.cola, fecha)
    os.makedirs(out_cola, exist_ok=True)
    cola = {"fecha": fecha, "zona": "Europe/Madrid", "usuario": a.usuario.lstrip("@"),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "publicaciones": posts}
    with open(os.path.join(out_cola, "cola.json"), "w", encoding="utf-8") as f:
        json.dump(cola, f, ensure_ascii=False, indent=1)
    print(os.path.join(out_cola, "cola.json"))
    print(f"{len(posts)} publicaciones, {sum(len(p['imagenes']) for p in posts)} imágenes en {out_img}", file=sys.stderr)


if __name__ == "__main__":
    main()
