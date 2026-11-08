#!/usr/bin/env python3
"""Construye la página de la edición en claude.ai (el artifact) a partir de la plantilla de la web (index.html) y del
JSON de una edición, para que las dos versiones compartan siempre el mismo código.

La página de claude.ai es la misma plantilla sin la cabecera <head> (la herramienta Artifact pone la suya) y con la
configuración de su versión: la URL de la propia página y la tarea programada que lanza el botón «Actualizar».

Uso:
  python3 scripts/pagina_claude.py --plantilla index.html --edicion trabajo/page.html --salida trabajo/claude.html \\
      --tarea trig_... [--pagina https://claude.ai/artifact/...] [--prueba "MODO PRUEBA: ..."]
"""
import argparse, json, re, sys

EDICION_RE = re.compile(r'(<script type="application/json" id="edition">)(.*?)(</script>)', re.S)


def js_texto(s):
    return (s or "").replace("\\", "\\\\").replace("'", "\\'").replace("\n", " ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plantilla", required=True)
    ap.add_argument("--edicion", required=True, help="página (HTML) de la que se toma el JSON de la edición")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--tarea", required=True, help="id de la tarea programada de actualización (trig_...)")
    ap.add_argument("--pagina", help="URL de esta página en claude.ai")
    ap.add_argument("--prueba", default="", help="texto que el botón añade al lanzar la tarea (solo páginas de prueba)")
    a = ap.parse_args()

    tpl = open(a.plantilla, encoding="utf-8").read()
    src = open(a.edicion, encoding="utf-8").read()
    m = EDICION_RE.search(src)
    if not m:
        sys.exit("La página de la edición no tiene el bloque JSON")
    texto_ed = m.group(2)
    json.loads(texto_ed)
    cab = re.search(r"<head>(.*?)</head>", tpl, re.S)
    cuerpo = re.search(r"<body>(.*?)</body>", tpl, re.S)
    if not (cab and cuerpo):
        sys.exit("La plantilla no tiene <head> o <body>")
    cab = cab.group(1)
    cab = cab[cab.index("<title>"):]  # sin metas ni icono: la herramienta Artifact pone su propia cabecera
    pagina = cab.strip() + "\n\n" + cuerpo.group(1).strip() + "\n"
    pagina = EDICION_RE.sub(lambda x: x.group(1) + "\n" + texto_ed.strip() + "\n" + x.group(3), pagina, count=1)
    cambios = {"tarea": a.tarea, "prueba": a.prueba}
    if a.pagina:
        cambios["pagina"] = a.pagina
    for clave, valor in cambios.items():
        pagina, n = re.subn(r"(\n\s*%s: )'[^'\n]*'" % clave, lambda x: x.group(1) + "'" + js_texto(valor) + "'", pagina, count=1)
        if not n:
            sys.exit(f"No encuentro «{clave}» en la configuración (CFG) de la plantilla")
    open(a.salida, "w", encoding="utf-8").write(pagina)
    print(f"{a.salida}: {len(pagina)} caracteres; tarea {a.tarea}" + (" (página de pruebas)" if a.prueba else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
