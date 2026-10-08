#!/usr/bin/env python3
"""Genera las publicaciones de Instagram de una edición de The Daily Iván.

Uso:
  python3 scripts/instagram_tarjetas.py <page.html> --imagenes DIR --cola DIR
          [--extra ig.json] [--usuario allyouneedisnews] [--base-url URL] [--horas 10:30,12:00,...]

Por cada bloque (Las 5 claves y cada sección) crea un carrusel de imágenes JPEG de 1080×1350:
una portada y una imagen por noticia; Mercados añade el panel de cotizaciones. Escribe:
  <imagenes>/<AAAA-MM-DD>/<bloque>-<n>.jpg
  <cola>/<AAAA-MM-DD>/cola.json   (hora, texto, hashtags y URL pública de cada imagen)

Textos: si la edición trae un objeto "instagram" (o se pasa con --extra), se usa tal cual:
  {"bloques": {"<id>": {"gancho": "...", "copy": "...", "hashtags": ["#..."]}},
   "items":   {"M1": {"titulo": "...", "hecho": "...", "importa": "...", "vigilar": "..."}}}
Si falta, se condensa a partir de la propia edición (frases completas, sin referencias personales).
"""
import argparse, html, json, os, re, sys, tempfile
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "fuentes")
REPO_RAW = "https://raw.githubusercontent.com/ivandiezb/the-daily-ivan/instagram-media"
ORDEN = ["claves", "espana", "mercados", "internacional", "geopolitica", "vivienda", "inversion", "naturaleza"]
HORAS = ["10:30", "12:00", "13:30", "15:00", "16:30", "18:00", "19:30", "21:00"]
MARCA = "#TheDailyIvan"
ETIQUETAS = {  # respaldo si la edición no propone hashtags (máximo 5 por publicación en total)
    "claves": ["#noticias", "#actualidad", "#España"], "mercados": ["#economía", "#bolsa", "#mercados"],
    "inversion": ["#inversión", "#bolsa", "#mercados"], "geopolitica": ["#geopolítica", "#internacional"],
    "espana": ["#España", "#política"], "internacional": ["#internacional", "#Europa"],
    "vivienda": ["#vivienda", "#empleo"], "naturaleza": ["#clima", "#medioambiente"]}
CONF = {"confirmado": "confirmada por varias fuentes o por fuente oficial", "una-fuente": "una sola fuente",
        "en-desarrollo": "en desarrollo, puede cambiar", "seguimiento": "seguimiento de una noticia anterior",
        "agenda": "previsto hoy, sin resultado conocido"}
COLORES = {  # fondo de banda, tinta, filete/etiqueta (los mismos de la web y el correo)
    "blue": ("#DCE5F2", "#14325F", "#3A659F"), "gray": ("#E2E5E9", "#262D36", "#5A6470"),
    "green": ("#DCEDE2", "#174A2C", "#2E7149")}
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


def condensa(t, maxc):
    """Frases completas hasta ~maxc caracteres, descartando las de uso privado."""
    out, n = [], 0
    t = (t or "").replace("(interpretación mía)", "(interpretación propia)")
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
*{box-sizing:border-box;margin:0;padding:0}
body{background:#777;font-family:Archivo,Arial,sans-serif;color:#141B23}
.slide{width:540px;height:675px;background:#EEF1F4;padding:18px;display:flex;margin:0 0 10px;overflow:hidden}
.card{flex:1;min-width:0;background:#fff;border:1px solid #D5DCE4;border-radius:14px;padding:22px 26px 16px;display:flex;flex-direction:column}
.top{display:flex;justify-content:space-between;align-items:center}
.brand{font:800 10.5px/1 Archivo;letter-spacing:2.2px;text-transform:uppercase;background:#FFEFA0;color:#3D3400;padding:6px 9px 5px;border-radius:5px}
.date{font:500 10.5px/1 "JetBrains Mono";color:#4B5765;letter-spacing:.3px;text-transform:uppercase}
.band{margin-top:14px;background:var(--bg);color:var(--ink);border-left:5px solid var(--lbl);border-radius:6px;padding:8px 11px;font:800 15px/1.1 Archivo;display:flex;align-items:center;gap:8px}
.band svg,.cover-ico svg{width:18px;height:18px;stroke:var(--lbl);fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
.band .n{margin-left:auto;font:500 11px/1 "JetBrains Mono";color:var(--lbl)}
.body{--s:1;flex:1;min-height:0;overflow:hidden;margin-top:16px}
.ttl{font:800 calc(24px*var(--s))/1.13 Archivo;letter-spacing:-.2px}
.chip{display:inline-block;font:700 calc(11px*var(--s))/1 "JetBrains Mono";background:#5A6470;color:#fff;border-radius:4px;padding:4px 6px;vertical-align:calc(4px*var(--s));margin-right:7px}
.lbl{font:700 calc(10.5px*var(--s))/1 Archivo;letter-spacing:1.4px;text-transform:uppercase;color:var(--lbl);margin:calc(15px*var(--s)) 0 calc(6px*var(--s))}
.p{font:400 calc(16px*var(--s))/1.45 "Source Serif 4";color:#141B23}
.big{font:700 calc(27px*var(--s))/1.22 Archivo;letter-spacing:-.2px;margin-top:6px}
.ref{margin-top:calc(18px*var(--s));font:600 calc(13px*var(--s))/1.35 Archivo;color:#4B5765}
.foot{border-top:1px solid #D5DCE4;padding-top:9px;margin-top:10px;font:italic 400 11.5px/1.35 "Source Serif 4";color:#4B5765}
.foot .v{font-style:normal;font-family:Archivo;font-weight:600;font-size:10.5px;letter-spacing:.2px;margin-top:3px}
.meta{display:flex;justify-content:space-between;margin-top:7px;font:600 10.5px/1 Archivo;color:#4B5765}
.meta .ia{color:#5A6470}
/* portada */
.cover .card{background:var(--bg);border:0;border-left:12px solid var(--lbl);border-radius:14px}
.cover .date{color:var(--ink)}
.cover-ico{margin-top:30px;display:flex;align-items:center;gap:10px;font:800 15px/1 Archivo;letter-spacing:2px;text-transform:uppercase;color:var(--lbl)}
.cover-ico svg{width:26px;height:26px;stroke-width:2.2}
.hook{--s:1;margin-top:16px;font:800 calc(37px*var(--s))/1.08 Archivo;letter-spacing:-.6px;color:var(--ink)}
.list{margin-top:auto;padding-top:18px;border-top:2px solid var(--lbl);list-style:none}
.list li{display:flex;gap:8px;font:600 14px/1.3 Archivo;color:var(--ink);margin-top:9px}
.list.small li{font-size:13px;margin-top:7px}
.list .c{font:700 11px/1 "JetBrains Mono";background:var(--lbl);color:#fff;border-radius:4px;padding:4px 5px 3px;height:18px;flex:none;margin-top:0}
.swipe{display:flex;justify-content:space-between;align-items:center;margin-top:20px;font:700 12px/1 Archivo;letter-spacing:1.6px;text-transform:uppercase;color:var(--lbl)}
.swipe .h{letter-spacing:.2px;text-transform:none;color:var(--ink);font-weight:600}
/* mercados */
.mk{width:100%;border-collapse:collapse;font:500 calc(14px*var(--s))/1.2 Archivo}
.mk td{padding:calc(6.5px*var(--s)) 0;border-bottom:1px solid #E3E8EE}
.mk tr:last-child td{border-bottom:0}
.mk .v,.mk .c{text-align:right;font-family:"JetBrains Mono";font-size:calc(12.5px*var(--s));white-space:nowrap}
.mk .c{width:86px}
.mk .u{font:500 calc(10px*var(--s)) Archivo;color:#4B5765}
.up{color:#16703D}.down{color:#B3261E}.flat{color:#4B5765}
"""

FIT_JS = r"""
() => {
  const over = el => el.scrollHeight > el.clientHeight + 1;
  const shrink = (el, min) => { let s = parseFloat(el.dataset.grow || 1); el.style.setProperty('--s', s);
    while (over(el) && s > min) { s = Math.round((s - 0.025) * 1000) / 1000; el.style.setProperty('--s', s); } return s; };
  const report = [];
  for (const slide of document.querySelectorAll('.slide')) {
    const hook = slide.querySelector('.hook');
    if (hook) { // la portada: el gancho se reduce si deja sin sitio a la lista
      const card = slide.querySelector('.card'); let s = 1.15; hook.style.setProperty('--s', s);
      while (card.scrollHeight > card.clientHeight + 1 && s > 0.62) { s -= 0.02; hook.style.setProperty('--s', s); }
    }
    const body = slide.querySelector('.body'); let dropped = 0, trimmed = 0, s = 1;
    if (body) {
      s = shrink(body, 0.84);
      for (const el of [...body.querySelectorAll('[data-opt]')].reverse()) {
        if (!over(body)) break; el.remove(); dropped++; s = shrink(body, 0.84);
      }
      while (over(body)) { // última opción: quitar la última frase del párrafo más largo
        const ps = [...body.querySelectorAll('.p')].filter(p => p.querySelectorAll('.f').length > 1)
          .sort((a, b) => b.textContent.length - a.textContent.length);
        if (!ps.length) { s = shrink(body, 0.7); break; }
        const fs = ps[0].querySelectorAll('.f'); fs[fs.length - 1].remove(); trimmed++; s = shrink(body, 0.84);
      }
    }
    const card = slide.querySelector('.card');
    report.push({id: slide.id, s, dropped, trimmed, overflow: (body && over(body)) || card.scrollHeight > card.clientHeight + 1});
  }
  return report;
}
"""


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
    ap.add_argument("--base-url", default=REPO_RAW, help="URL pública bajo la que quedarán <AAAA-MM-DD>/<archivo>.jpg")
    ap.add_argument("--horas", default=",".join(HORAS))
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

    bloques = [{"id": "claves", "titulo": "Las 5 claves", "kind": "gray", "claves": d.get("claves", [])}]
    for s in d["secciones"]:
        bloques.append({"id": s["id"], "titulo": s["titulo"], "kind": "green" if s.get("tipo") == "inversion" else "blue",
                        "items": s["items"]})
    rango = {b: i for i, b in enumerate(ORDEN)}
    bloques.sort(key=lambda b: rango.get(b["id"], 99))
    horas = [h.strip() for h in a.horas.split(",") if h.strip()]
    if len(bloques) > len(horas):
        print(f"Aviso: {len(bloques)} bloques y {len(horas)} horas; se omiten: "
              f"{', '.join(b['id'] for b in bloques[len(horas):])}", file=sys.stderr)
        bloques = bloques[:len(horas)]

    slides, posts = [], []
    for b, hora in zip(bloques, horas):
        bid, (bg, ink, lbl) = b["id"], COLORES[b["kind"]]
        style = f'style="--bg:{bg};--ink:{ink};--lbl:{lbl}"'
        o = igb.get(bid, {})
        top = (f'<div class="top"><span class="brand">The Daily Iván</span>'
               f'<span class="date">{e(fcorta)}</span></div>')
        meta = (f'<div class="meta"><span>{e(handle)}</span><span class="ia">Resumen elaborado con IA</span></div>')
        files = []

        def add(html_slide):
            n = len(files) + 1
            sid = f"{bid}-{n}"
            files.append(f"{sid}.jpg")
            slides.append(html_slide.replace("§ID§", sid))

        if bid == "claves":
            claves = b["claves"]
            gancho = o.get("gancho") or "Lo que hay que saber hoy, en cinco claves."
            tit_ref = {it["code"]: (igi.get(it["code"], {}).get("titulo") or it["titulo"]) for s in d["secciones"] for it in s["items"]}
            lista = "".join(f'<li><span class="c">{e(k.get("ref", i + 1))}</span><span>{nb(tit_ref.get(k.get("ref"), k["t"]))}</span></li>'
                            for i, k in enumerate(claves[:5]))
            titulos = [k["t"] for k in claves]
        else:
            items = b["items"]
            lead = items[0]
            gancho = o.get("gancho") or igi.get(lead["code"], {}).get("titulo") or lead["titulo"]
            lista = "".join(f'<li><span class="c">{e(it["code"])}</span><span>{nb(igi.get(it["code"], {}).get("titulo") or it["titulo"])}</span></li>'
                            for it in items[:4])
            titulos = [igi.get(it["code"], {}).get("titulo") or it["titulo"] for it in items]
        add(f'<section class="slide cover" id="§ID§" {style}><div class="card">{top}'
            f'<div class="cover-ico">{svg(ico.get(bid))}<span>{e(b["titulo"])}</span></div>'
            f'<div class="hook">{nb(gancho)}</div><ul class="list{" small" if bid == "claves" else ""}">{lista}</ul>'
            f'<div class="swipe"><span class="h">{e(handle)}</span><span>Desliza →</span></div></div></section>')

        if bid == "claves":
            for i, k in enumerate(claves):
                sec = sec_de.get(k.get("ref"))
                ref = (f'<div class="ref"><span class="chip">{e(k["ref"])}</span>Detalle y fuentes en el carrusel de '
                       f'{e(sec.get("corto") or sec["titulo"])}</div>') if sec else ""
                add(f'<section class="slide" id="§ID§" {style}><div class="card">{top}'
                    f'<div class="band">{svg(ico.get("claves"))}<span>Las 5 claves</span><span class="n">{i + 1}/{len(claves)}</span></div>'
                    f'<div class="body" data-grow="1.3"><p class="big">{nb(k["t"])}</p>{ref}</div>'
                    f'<div class="foot">Edición completa, con enlace a cada fuente: enlace en la bio.{meta}</div></div></section>')
        else:
            if bid == "mercados" and d.get("mercados"):
                filas = []
                for m in d["mercados"]:
                    t, v, dec, c = m.get("tipo"), m["v"], m.get("dec", 2), m.get("c")
                    if t == "indice":
                        val = f'{num(v, dec)} <span class="u">pts</span>'
                    elif t == "rent":
                        val = f'{num(v, dec)} <span class="u">%</span>'
                    elif t == "divisa":
                        val = f'{num(v, 4)} <span class="u">$/€</span>'
                    else:
                        val = f'{num(v, dec)} <span class="u">${("/" + m["por"]) if m.get("por") else ""}</span>'
                    if c is None:
                        ch = '<span class="flat">—</span>'
                    else:
                        cls = "up" if c > 0 else "down" if c < 0 else "flat"
                        ch = f'<span class="{cls}">{"+" if c > 0 else ""}{num(c, 2)} %</span>'
                    filas.append(f'<tr><td>{e(m["n"])}</td><td class="v">{val}</td><td class="c">{ch}</td></tr>')
                fx = d.get("fx") or {}
                add(f'<section class="slide" id="§ID§" {style}><div class="card">{top}'
                    f'<div class="band">{svg(ico.get("mercados"))}<span>Panel de mercados</span><span class="n">{e(fx.get("s", "").split("·")[0].strip())}</span></div>'
                    f'<div class="body"><table class="mk">{"".join(filas)}</table></div>'
                    f'<div class="foot">Cifras de prensa económica ({e(fx.get("s", ""))}), orientativas: no son cotizaciones en tiempo real. '
                    f'Bonos en rentabilidad anual.{meta}</div></div></section>')
            for i, it in enumerate(items):
                ov = igi.get(it["code"], {})
                breve = it.get("breve")
                hecho = oraciones(ov["hecho"]) if ov.get("hecho") else condensa(it.get("hecho"), 360 if breve else 330)
                importa = oraciones(ov["importa"]) if ov.get("importa") else condensa(it.get("importa"), 260)
                vigilar = oraciones(ov["vigilar"]) if ov.get("vigilar") else condensa(it.get("vigilar"), 190)
                cuerpo = (f'<h2 class="ttl"><span class="chip">{e(it["code"])}</span>{nb(ov.get("titulo") or it["titulo"])}</h2>'
                          + (f'<div class="lbl">Qué ha pasado</div>{parrafo(hecho)}' if hecho else "")
                          + (f'<div data-opt><div class="lbl">Por qué importa</div>{parrafo(importa)}</div>' if importa else "")
                          + (f'<div data-opt><div class="lbl">Qué vigilar</div>{parrafo(vigilar)}</div>' if vigilar else ""))
                fuentes = " · ".join(f["t"] for f in it.get("fuentes", [])[:4])
                aviso = " Contenido informativo, no es una recomendación de inversión." if bid == "inversion" else ""
                add(f'<section class="slide" id="§ID§" {style}><div class="card">{top}'
                    f'<div class="band">{svg(ico.get(bid))}<span>{e(b["titulo"])}</span><span class="n">{i + 1}/{len(items)}</span></div>'
                    f'<div class="body">{cuerpo}</div>'
                    f'<div class="foot">{("Fuentes: " + e(fuentes) + ".") if fuentes else ""}{aviso}'
                    f'<div class="v">Verificación: {e(CONF.get(it.get("conf"), it.get("conf", "")))}</div>{meta}</div></div></section>')

        # texto de la publicación
        etiquetas = [MARCA] + [t if t.startswith("#") else "#" + t for t in (o.get("hashtags") or ETIQUETAS.get(bid, []))]
        vistos, tags = set(), []
        for t in etiquetas:
            t = re.sub(r"\s+", "", t)
            if t.lower() not in vistos and len(tags) < 5:
                vistos.add(t.lower())
                tags.append(t)
        partes = [gancho]
        if o.get("copy"):
            partes += ["", o["copy"]]
        if bid == "claves":
            partes += ["", "Desliza: una clave por imagen, con el bloque donde está el detalle."]
        else:
            partes += ["", "En este carrusel:"] + [f"▸ {t}" for t in titulos]
            partes += ["", "Desliza para ver qué ha pasado, por qué importa y las fuentes."]
        if bid == "inversion":
            partes += ["", "Contenido informativo; no es una recomendación de inversión."]
        partes += ["La edición completa del día, con enlace a cada fuente, está en el enlace de la bio.",
                   "", "ℹ️ Resumen elaborado con IA a partir de las fuentes citadas.", "", " ".join(tags)]
        texto = "\n".join(partes)
        if len(texto) > 2200:
            raise SystemExit(f"{bid}: el texto supera los 2.200 caracteres de Instagram ({len(texto)})")
        posts.append({"id": f"{fecha}-{bid}", "bloque": bid, "hora": hora, "texto": texto, "hashtags": tags,
                      "imagenes": [f"{a.base_url.rstrip('/')}/{fecha}/{f}" for f in files], "archivos": files})

    for p in posts:
        if not 2 <= len(p["imagenes"]) <= 10:
            raise SystemExit(f"{p['id']}: un carrusel admite de 2 a 10 imágenes ({len(p['imagenes'])})")

    # render
    out_img = os.path.join(a.imagenes, fecha)
    os.makedirs(out_img, exist_ok=True)
    css = CSS.replace('url("F/', 'url("file://' + FUENTES + "/")
    doc = f'<!doctype html><html lang="es"><head><meta charset="utf-8"><style>{css}</style></head><body>{"".join(slides)}</body></html>'
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
