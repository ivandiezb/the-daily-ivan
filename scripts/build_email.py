#!/usr/bin/env python3
"""Build the daily briefing e-mail (HTML + plain text) from the edition JSON embedded in the page.

Usage: python3 build_email.py <page.html> <artifact_url> <out_dir>
Writes <out_dir>/email.html and <out_dir>/email.txt and prints the subject line.

Gmail-safe by design (checked against what the Gmail connector actually stores, 8 Oct 2026):
- it strips <style> blocks, class/id/role attributes, the `background` shorthand, box-sizing and
  color-scheme; it keeps inline `background-color`, bgcolor, borders, calc(), min/max-width.
- so every colour is an inline longhand, there is no stylesheet, and nothing relies on box-sizing.
- dark mode: Gmail's apps recolour the message themselves (no designer dark CSS reaches them).
  Blocks therefore carry both a tinted background and a coloured left rule, so they stay visible
  after Gmail darkens the tints; chips and the button are mid-tone fills with white text.
- layout: dispatches use the "fab four" hybrid — two equal columns when the message is at least
  620px wide (computer, iPad), one full-width column below that (phones), with no media queries.
"""
import html, json, math, os, re, sys

CONF = {"confirmado": "confirmada por varias fuentes o por fuente oficial", "una-fuente": "una sola fuente",
        "en-desarrollo": "en desarrollo, puede cambiar", "seguimiento": "seguimiento de una noticia anterior",
        "agenda": "previsto hoy, sin resultado conocido"}
# block kind: (band background, band text, left rule / label colour)
BANDS = {"blue": ("#D6E2F4", "#14325F", "#2F5F9E"), "gray": ("#E1E5EA", "#262D36", "#5A6470"),
         "sand": ("#F2E0C4", "#5E3A10", "#9A6524"), "green": ("#D5EBDD", "#174A2C", "#2E7149")}
INK, INK2, RULE, ACC, PAPER, CHIP = "#141B23", "#4B5765", "#D5DCE4", "#1D4A93", "#EEF1F4", "#5A6470"
UP, DOWN = "#16703D", "#B3261E"
SANS, SERIF, MONO = "Arial,Helvetica,sans-serif", "Georgia,serif", "Menlo,Consolas,monospace"
COL_BREAK = 620  # message width (px) from which dispatches sit in two columns
WEB = "https://ivandiezb.github.io/the-daily-ivan/"  # public site, always shown under the summary
WEB_LABEL = "ivandiezb.github.io/the-daily-ivan"
LINK = "#2F5F9E"  # mid blue: visible but quieter than the main button


def e(s):
    return html.escape(str(s or ""), quote=True)


def num(x, dec):
    s = f"{abs(x):,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 else "") + s


def strip(h):
    return re.sub(r"<[^>]+>", "", h.replace("<br>", " · "))


def small(s):
    return f'<br><small style="color:{INK2}">{s}</small>'


def market_cells(mk, fx):
    """Return (value_html, change_html, colour) showing $ and € side by side where it applies."""
    t, v, dec, ch = mk.get("tipo"), mk["v"], mk.get("dec", 2), mk.get("c")
    prev = mk.get("prev")
    approx = False
    if ch is not None and prev is None:
        prev, approx = v / (1 + ch / 100), True
    if t == "indice":
        val, sym = f"{num(v, dec)} pts", " pts"
    elif t == "rent":
        val, sym = f"{num(v, dec)} %", " %"
    elif t == "divisa":
        val, sym = f"{num(v, 4)} $/€" + small(f"{num(1 / v, 4)} €/$"), " $"
        dec = 4
    else:
        por = f"/{mk['por']}" if mk.get("por") else ""
        val, sym = f"{num(v, dec)} ${por}" + (small(f"≈ {num(v / fx, dec)} €") if fx else ""), " $"
    if ch is None:
        return val, "—", INK2
    diff = v - prev
    p = ("+" if ch > 0 else ("−" if ch < 0 else "")) + num(abs(ch), 2) + " %"
    ab = ("≈" if approx else "") + ("+" if diff > 0 else "") + num(diff, dec) + sym
    return val, f"{p}{small(ab)}", (UP if ch > 0 else DOWN if ch < 0 else INK2)


def est_height(it):
    """Rough rendered height (px) of a dispatch in a ~440px column; only used to balance the columns."""
    ln = lambda text, cpl, lh: math.ceil(max(1, len(text)) / cpl) * lh
    h = 26 + ln(it["code"] + "  " + it["titulo"], 50 if it.get("breve") else 44, 21 if it.get("breve") else 23.4)
    if it.get("breve"):
        h += 6 + ln(" ".join(it[k] for k in ("hecho", "importa", "vigilar") if it.get(k)), 60, 22.5)
    else:
        for k in ("hecho", "importa", "vigilar"):
            if it.get(k):
                h += 8 + 15 + ln(it[k], 60, 22.5)
    if it.get("nota"):
        h += 8 + ln(it["nota"], 66, 21)
    if it.get("fuentes"):
        h += 8 + ln(" · ".join(f["t"] for f in it["fuentes"]) + "Fuentes: ", 78, 19.5) + (19.5 if it.get("conf") else 0)
    return h


def balance(items):
    """Lead story top-left; the others go wherever the two columns end up most even.
    Ties lean towards keeping the reading order (left column first, then right) for phones."""
    hs = [est_height(it) for it in items]
    best = None
    for mask in range(1 << (len(items) - 1)):
        left, right = [0], []
        for i in range(1, len(items)):
            (right if mask >> (i - 1) & 1 else left).append(i)
        if not right:
            continue
        order = left + right
        inversions = sum(1 for a in range(len(order)) for b in range(a + 1, len(order)) if order[a] > order[b])
        score = max(sum(hs[i] for i in left), sum(hs[i] for i in right)) + 30 * inversions
        if best is None or score < best[0]:
            best = (score, left, right)
    return best[1], best[2]


def main(page, url, out):
    src = open(page, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="edition">(.*?)</script>', src, re.S)
    d = json.loads(m.group(1))
    tm = re.search(r"<title>(.*?)</title>", src, re.S)
    brand = html.unescape(tm.group(1)).strip() if tm else "The Daily Iván"
    sm = re.search(r'id="slogan">(.*?)</p>', src, re.S)
    slogan = html.unescape(sm.group(1)).strip() if sm else ""
    n_items = sum(len(sec["items"]) for sec in d["secciones"])
    words = sum(len(" ".join(str(it.get(k, "")) for k in ("titulo", "hecho", "importa", "vigilar", "nota")).split())
                for sec in d["secciones"] for it in sec["items"])
    words += sum(len(k["t"].split()) for k in d.get("claves", [])) + sum(len(r["t"].split()) for r in d.get("radar", []))
    words += sum(len(a["t"].split()) for a in d.get("agenda", [])) + len(d.get("lede", "").split())
    mins = max(1, round(words / 220))
    meta = " · ".join(x for x in (d.get("tipo", ""), f"cierre de datos {d.get('cierre', '')}", f"lectura ≈ {mins} min", f"{n_items} noticias") if x)
    meta = meta[:1].upper() + meta[1:]
    sec_of = {it["code"]: (sec.get("corto") or sec["titulo"]) for sec in d["secciones"] for it in sec["items"]}
    lede = d.get("lede", "")
    H, T = [], []

    H.append(f'<div style="display:none;max-height:0;overflow:hidden">{e(lede[:180])}</div>')
    H.append(f'<table width="100%" cellpadding="0" cellspacing="0" bgcolor="{PAPER}" style="background-color:{PAPER}"><tr><td style="padding:16px 8px">'
             f'<table width="100%" cellpadding="0" cellspacing="0" bgcolor="#FFFFFF" style="background-color:#FFFFFF;max-width:960px;margin:0 auto;border:1px solid {RULE};border-radius:6px"><tr>'
             f'<td style="padding:22px 20px;color:{INK};font-family:{SERIF};font-size:15px;line-height:1.5">')
    H.append(f'<div style="font:bold 12px {SANS};letter-spacing:2px;text-transform:uppercase"><span style="background-color:#FFEFA0;color:#3D3400;padding:3px 8px;border-radius:4px">{e(brand)}</span></div>')
    H.append(f'<div style="font:bold 26px/1.15 {SANS};margin:8px 0 4px">{e(d["fechaTexto"])}</div>')
    if slogan:
        H.append(f'<div style="color:{INK2};font-style:italic;font-size:14px;margin:0 0 4px">{e(slogan)}</div>')
    H.append(f'<div style="color:{INK2};font:italic 12px {SANS}">{e(meta)}</div>')
    if lede:
        H.append(f'<p style="color:{INK2};margin:10px 0 0">{e(lede)}</p>')
    # Public web address under the summary: small, mid-blue, chain-link emoji (Gmail drops SVG and data-URI images).
    H.append(f'<p style="margin:8px 0 0;font:13px/1.4 {SANS}"><a href="{e(WEB)}" style="color:{LINK};text-decoration:none">'
             f'&#128279;&nbsp;{e(WEB_LABEL)}</a></p>')
    H.append(f'<p style="margin:16px 0 4px"><a href="{e(url)}" style="background-color:{ACC};color:#FFFFFF;text-decoration:none;font:bold 14px {SANS};padding:9px 14px;border-radius:5px;display:inline-block">Abrir la edición completa</a>'
             f'&nbsp;&nbsp; <a href="{e(url)}#archivo" style="color:{ACC};font:bold 14px {SANS}">Ediciones anteriores</a></p>')
    T += [f"{brand.upper()} · {d['fechaTexto']}", slogan, meta, "", lede, "", f"Web: {WEB}", "", f"Edición completa: {url}",
          f"Ediciones anteriores: {url}#archivo", ""]

    def h2(t, kind):
        bg, ink, rule = BANDS[kind]
        H.append(f'<div style="background-color:{bg};color:{ink};border-left:5px solid {rule};font:bold 21px/1.2 {SANS};padding:10px 12px;border-radius:5px;margin:28px 0 8px">{e(t)}</div>')
        T.extend(["", t.upper(), "-" * len(t)])

    h2("Las 5 claves", "gray")
    for i, k in enumerate(d["claves"], 1):
        lab = f"{sec_of[k['ref']]} ({k['ref']})" if k.get("ref") in sec_of else k.get("ref", "")
        ref = f' <span style="color:{ACC};font-family:{MONO};font-size:12px">→ {e(lab)}</span>' if k.get("ref") else ""
        H.append(f'<p style="margin:0 0 10px"><b style="color:{ACC};font-family:{MONO}">{i:02d}</b>&nbsp; {e(k["t"])}{ref}</p>')
        T.append(f"{i:02d}. {k['t']} ({k.get('ref','')})")

    def market_table():
        H.append(f'<div style="color:{BANDS["blue"][2]};font:bold 12px {SANS};letter-spacing:1px;margin:18px 0 6px">INDICADORES DE MERCADO</div>')
        T.extend(["", "Indicadores de mercado"])
        H.append(f'<table width="100%" cellpadding="0" cellspacing="0" style="font-family:{SANS};font-size:14px">')
        fx = (d.get("fx") or {}).get("eurusd")
        line = f"border-top:1px solid {RULE}"
        for mk in d["mercados"]:
            val, chg, col = market_cells(mk, fx)
            H.append(f'<tr><td style="padding:6px 0;{line}"><b>{e(mk["n"])}</b><br><small style="color:{INK2}">{e(mk.get("s",""))}</small></td>'
                     f'<td align="right" style="{line};white-space:nowrap">{val}</td>'
                     f'<td align="right" style="padding-left:10px;{line};white-space:nowrap;color:{col}">{chg}</td></tr>')
            T.append(f"- {mk['n']}: {strip(val)} ({strip(chg)}) · {mk.get('s','')}")
        H.append("</table>")
        if d.get("mercadosNota"):
            H.append(f'<p style="color:{INK2};font-size:13px;margin:8px 0 0">{e(d["mercadosNota"])}</p>')
            T.append(d["mercadosNota"])

    # Fab-four column: 50% wide when the message is >= COL_BREAK px, 100% below (no media queries needed).
    col = (f"display:inline-block;vertical-align:top;width:100%;min-width:50%;max-width:100%;"
           f"width:calc(({COL_BREAK}px - 100%)*{COL_BREAK})")

    def stack(parts):
        """Dispatches one under another; a thin rule only between two of them, never after the last."""
        out = []
        for i, b in enumerate(parts):
            line = f";border-bottom:1px solid {RULE}" if i < len(parts) - 1 else ""
            out.append(f'<div style="padding:12px 0 14px{line}">{b}</div>')
        return "".join(out)

    def columns(blocks, items):
        if len(blocks) == 1:
            return stack(blocks)
        left, right = balance(items)
        # The gutter is right padding on the left column's inner wrapper (no width set there, and Gmail drops
        # box-sizing and negative margins), so rules never touch across columns and both columns stay aligned
        # with the block header. No whitespace between the two columns.
        return (f'<div><div style="{col}"><div style="padding:0 22px 0 0">{stack([blocks[i] for i in left])}</div></div>'
                f'<div style="{col}">{stack([blocks[i] for i in right])}</div></div>')
    for sec in d["secciones"]:
        kind = "green" if sec.get("tipo") == "inversion" else "blue"
        h2(sec["titulo"], kind)
        lbl = BANDS[kind][2]
        if sec.get("nota"):
            H.append(f'<p style="color:{INK2};font-style:italic;margin:0 0 8px">{e(sec["nota"])}</p>')
            T.append(sec["nota"])
        blocks = []
        for it in sec["items"]:
            P = []
            size = "16px" if it.get("breve") else "18px"
            P.append(f'<div style="font:bold {size}/1.3 {SANS};margin:2px 0 4px"><span style="background-color:{CHIP};color:#FFFFFF;font:bold 12px {MONO};padding:1px 6px;border-radius:3px;vertical-align:2px">{e(it["code"])}</span>&nbsp; {e(it["titulo"])}</div>')
            T += ["", f"[{it['code']}] {it['titulo']}"]
            if it.get("breve"):
                body = " ".join(it[k] for k in ("hecho", "importa", "vigilar") if it.get(k))
                P.append(f'<p style="margin:6px 0 0">{e(body)}</p>')
                T.append(body)
            else:
                for lb, key in (("Qué ha pasado", "hecho"), ("Por qué importa", "importa"), ("Qué vigilar", "vigilar")):
                    if it.get(key):
                        P.append(f'<p style="margin:8px 0 0"><b style="color:{lbl};font:bold 10px {SANS};letter-spacing:1px">{lb.upper()}</b><br>{e(it[key])}</p>')
                        T.append(f"{lb}: {it[key]}")
            if it.get("nota"):
                P.append(f'<p style="color:{INK2};margin:8px 0 0;font-size:14px;font-style:italic">{e(it["nota"])}</p>')
                T.append(f"({it['nota']})")
            if it.get("fuentes"):
                links = " · ".join(f'<a href="{e(f["u"])}" style="color:{INK2}">{e(f["t"])}</a>' for f in it["fuentes"])
                status = f'<br>Verificación: {e(CONF.get(it.get("conf"), it.get("conf","")))}' if it.get("conf") else ""
                cob = it.get("cobertura") or {}
                if cob.get("n"):
                    status += f'<br>Cobertura: en {cob["n"]} de {cob.get("de", "?")} medios consultados'
                P.append(f'<p style="color:{INK2};margin:8px 0 0;font-size:13px;font-style:italic">Fuentes: {links}{status}</p>')
                T.append("Fuentes: " + " · ".join(f"{f['t']} <{f['u']}>" for f in it["fuentes"]))
                if it.get("conf"):
                    T.append("Verificación: " + CONF.get(it["conf"], it["conf"]))
                if (it.get("cobertura") or {}).get("n"):
                    T.append(f"Cobertura: en {it['cobertura']['n']} de {it['cobertura'].get('de', '?')} medios consultados")
            blocks.append("\n".join(P))
        H.append(columns(blocks, sec["items"]))
        if sec["id"] == "mercados":
            market_table()

    if d.get("radar"):
        h2("Otras noticias en el radar", "gray")
        rows = []
        for i, r in enumerate(d["radar"]):
            top = f"border-top:1px solid {RULE};" if i else ""
            rows.append(f'<tr><td width="22" valign="top" style="{top}padding:9px 0 9px 2px;color:{BANDS["gray"][2]};font-size:11px;line-height:22px">&#9679;</td>'
                        f'<td style="{top}padding:9px 0">{e(r["t"])} <a href="{e(r["u"])}" style="color:{INK2};font-family:{MONO};font-size:11.5px">{e(r["f"])}</a></td></tr>')
            T.append(f"- {r['t']} ({r['f']}: {r['u']})")
        H.append('<table width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table>")
    if d.get("agenda"):
        h2("Agenda: lo que viene", "sand")
        rows = []
        for i, a in enumerate(d["agenda"]):
            top = f"border-top:1px solid {RULE};" if i else ""
            area = f'<span style="color:{INK2};font:bold 11px {SANS};letter-spacing:.5px">{e(a["a"]).upper()}</span><br>' if a.get("a") else ""
            rows.append(f'<tr><td width="92" valign="top" style="{top}padding:10px 8px 10px 0;white-space:nowrap">'
                        f'<span style="border-left:3px solid {BANDS["sand"][2]};padding-left:8px;color:{ACC};font:bold 14px {MONO}">{e(a["d"])}</span></td>'
                        f'<td valign="top" style="{top}padding:10px 0">{area}{e(a["t"])}</td></tr>')
            T.append(f"- {a['d']}" + (f" [{a['a']}]" if a.get("a") else "") + f": {a['t']}")
        H.append('<table width="100%" cellpadding="0" cellspacing="0">' + "".join(rows) + "</table>")

    tr = d.get("tendencias") or {}
    if tr.get("es"):
        h2("Tendencias de la sociedad", "gray")
        if tr.get("comentario"):
            H.append(f'<p style="margin:8px 0 0">{e(tr["comentario"])}</p>')
            T.append(tr["comentario"])
        if tr.get("destacado"):
            H.append(f'<p style="margin:10px 0 0;padding:8px 12px;border-left:3px solid #9A5800;background-color:{PAPER}">'
                     f'<b style="color:#9A5800;font-family:{SANS}">Señal a vigilar:</b> {e(tr["destacado"])}</p>')
            T.append("Señal a vigilar: " + tr["destacado"])

        def lista(items, valor):
            return " · ".join(f'{e(x["t"])} <span style="color:{INK2};font:12px {MONO}">{e(valor(x))}</span>' for x in items[:6])
        filas = [("Lo más buscado en España", tr["es"].get("google", []), lambda x: x.get("trafico", "")),
                 ("Lo que se busca en más países", (tr.get("int") or {}).get("google", []), lambda x: f'{len(x.get("paises", []))} ' + ("país" if len(x.get("paises", [])) == 1 else "países")),
                 ("Lo más leído en Wikipedia en español", tr["es"].get("wiki", []), lambda x: f'{x.get("v", 0):,}'.replace(",", "."))]
        for tit, items, valor in filas:
            if items:
                H.append(f'<p style="margin:10px 0 0;font-size:14px"><b style="color:{INK2};font:bold 10px {SANS};letter-spacing:1px">{tit.upper()}</b><br>{lista(items, valor)}</p>')
                T.append(f"{tit}: " + " · ".join(x["t"] for x in items[:6]))
        H.append(f'<p style="margin:10px 0 0;font:13px {SANS}"><a href="{e(url)}#tendencias" style="color:{ACC}">Ver el gráfico en la edición completa</a></p>')

    H.append(f'<div style="background-color:{PAPER};color:{INK2};margin-top:24px;padding:12px 14px;font-size:13.5px;border-radius:5px">'
             f'<b style="color:{INK}">Para profundizar:</b> en la <a href="{e(url)}" style="color:{ACC}">edición completa</a>, cada noticia tiene un botón '
             f'«Profundizar», que copia un encargo de investigación detallado, y los enlaces «Abrir en Claude · ChatGPT · Perplexity», que lo abren ya escrito. '
             f'También puedes abrir en Claude la ejecución de hoy de la tarea «{e(brand)}» y escribir, por ejemplo, «amplía G1».'
             f'<br><br>Las cifras de mercado son orientativas y llevan su hora y fuente.</div>')
    H.append("</td></tr></table></td></tr></table>")
    T += ["", f"Para profundizar: en la edición completa ({url}) cada noticia tiene «Profundizar» y enlaces para abrirla en Claude, ChatGPT o Perplexity.",
          "Las cifras de mercado son orientativas y llevan su hora y fuente."]

    os.makedirs(out, exist_ok=True)
    body = "\n".join(H)
    open(os.path.join(out, "email.html"), "w", encoding="utf-8").write(body)
    open(os.path.join(out, "email.txt"), "w", encoding="utf-8").write("\n".join(T))
    size = len(body.encode("utf-8"))
    if size > 95_000:
        print(f"AVISO: el email pesa {size // 1024} KB; Gmail recorta los mensajes de más de ~102 KB.", file=sys.stderr)
    print(f"{brand} · {d['fechaTexto']}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
