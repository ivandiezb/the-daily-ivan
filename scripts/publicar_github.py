#!/usr/bin/env python3
"""Sube la edición del día a GitHub por la API (sin git push a main) y comprueba que la web se actualiza.

Por qué así: las tareas programadas trabajan en un modo automático que puede bloquear órdenes de git (y empujar
directamente a main o forzar ramas son de las primeras candidatas). Este script no toca main: crea una rama NUEVA
«publicar-AAAA-MM-DD-HHMMSS» con los archivos de la edición, y el flujo de GitHub Actions «Publicar edición»
(.github/workflows/publicar.yml) la lleva a main, pide la reconstrucción de GitHub Pages y borra la rama.

Uso (desde R = el repositorio):
  python3 scripts/publicar_github.py edicion --fecha AAAA-MM-DD --mensaje "Edición del …" \
          index.html archivo/2026-10.json archivo/2026-10-dias.json instagram/AAAA-MM-DD/cola.json [--esperar 480]
      Sube esos archivos (rutas relativas al repositorio, con el contenido local actual) y espera hasta que main
      tenga la edición de esa fecha. Última línea: «WEB_OK» o «WEB_FALLO: <motivo>». Código 0 solo si WEB_OK.
  python3 scripts/publicar_github.py imagenes --fecha AAAA-MM-DD --carpeta trabajo/ig_media/AAAA-MM-DD [--rama …]
      Crea la rama instagram-media-AAAA-MM-DD con las imágenes en AAAA-MM-DD/ (la que usa instagram_tarjetas.py).
  python3 scripts/publicar_github.py comprobar --fecha AAAA-MM-DD
      Solo comprueba si la web pública (rama main) ya tiene la edición de esa fecha.

Usa la API REST de GitHub con el token de GH_TOKEN o GITHUB_TOKEN (en las sesiones de Claude, el proxy añade la
credencial). Solo biblioteca estándar.
"""
import argparse, base64, json, os, re, sys, time, urllib.error, urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("REPO_GITHUB", "ivandiezb/the-daily-ivan")
API = f"https://api.github.com/repos/{REPO}"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOR = {"name": "Iván Díez", "email": "ivandiezberjano@gmail.com"}


def llamar(metodo, ruta, cuerpo=None, crudo=False, intentos=4):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    cab = {"Accept": "application/vnd.github.raw" if crudo else "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "the-daily-ivan"}
    if token:
        cab["Authorization"] = f"Bearer {token}"
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    if datos:
        cab["Content-Type"] = "application/json"
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(API + ruta, data=datos, headers=cab, method=metodo)
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
                return b.decode("utf-8", "replace") if crudo else (json.loads(b) if b else {})
        except urllib.error.HTTPError as e:
            texto = e.read().decode("utf-8", "replace")[:300]
            ultimo = f"HTTP {e.code} en {metodo} {ruta}: {texto}"
            if e.code in (400, 401, 403, 404, 409, 422):
                raise RuntimeError(ultimo)
        except Exception as e:  # red, proxy, tiempo de espera
            ultimo = f"{type(e).__name__} en {metodo} {ruta}: {e}"
        time.sleep(3 * (i + 1))
    raise RuntimeError(ultimo)


def blob(contenido):
    return llamar("POST", "/git/blobs", {"content": base64.b64encode(contenido).decode(), "encoding": "base64"})["sha"]


def crear_rama(rama, archivos, mensaje, padre=True):
    """archivos: {ruta_en_repo: bytes}. Crea un commit (sobre main o huérfano) y la rama nueva que apunta a él."""
    entradas = [{"path": p, "mode": "100644", "type": "blob", "sha": blob(c)} for p, c in sorted(archivos.items())]
    cuerpo_arbol = {"tree": entradas}
    padres = []
    if padre:
        main = llamar("GET", "/git/ref/heads/main")["object"]["sha"]
        cuerpo_arbol["base_tree"] = llamar("GET", f"/git/commits/{main}")["tree"]["sha"]
        padres = [main]
    arbol = llamar("POST", "/git/trees", cuerpo_arbol)["sha"]
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = llamar("POST", "/git/commits", {"message": mensaje, "tree": arbol, "parents": padres,
                                             "author": dict(AUTOR, date=ahora), "committer": dict(AUTOR, date=ahora)})["sha"]
    llamar("POST", "/git/refs", {"ref": f"refs/heads/{rama}", "sha": commit})
    return commit


def web_tiene(fecha):
    html = llamar("GET", "/contents/index.html?ref=main", crudo=True)
    m = re.search(r'"fechaISO"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html)
    return (m.group(1) if m else None) == fecha, (m.group(1) if m else "desconocida")


def estado_flujo(rama):
    try:
        runs = llamar("GET", f"/actions/runs?branch={rama}&per_page=5").get("workflow_runs", [])
        return ", ".join(f"{r['name']}: {r['status']}/{r['conclusion']}" for r in runs) or "sin ejecuciones todavía"
    except Exception as e:
        return f"no consultable ({e})"


def cmd_edicion(a):
    archivos = {}
    for ruta in a.archivos:
        local = os.path.join(a.raiz, ruta)
        if not os.path.isfile(local):
            raise SystemExit(f"WEB_FALLO: no existe {local}")
        archivos[ruta.replace(os.sep, "/")] = open(local, "rb").read()
    if "index.html" in archivos:
        m = re.search(rb'"fechaISO"\s*:\s*"(\d{4}-\d{2}-\d{2})"', archivos["index.html"])
        if not m or m.group(1).decode() != a.fecha:
            raise SystemExit(f"WEB_FALLO: index.html no es la edición del {a.fecha} "
                             f"(lleva {m.group(1).decode() if m else 'ninguna fecha'})")
    rama = f"publicar-{a.fecha}-{datetime.now(timezone.utc):%H%M%S}"
    try:
        commit = crear_rama(rama, archivos, a.mensaje)
    except Exception as e:
        print(f"WEB_FALLO: no se pudo crear la rama {rama}: {e}")
        return 1
    print(f"Rama {rama} creada (commit {commit[:7]}) con {len(archivos)} archivos; GitHub Actions la lleva a main.")
    limite = time.time() + a.esperar
    while True:
        try:
            ok, actual = web_tiene(a.fecha)
        except Exception as e:
            ok, actual = False, f"error al consultar ({e})"
        if ok:
            print("WEB_OK")
            return 0
        if time.time() > limite:
            print(f"WEB_FALLO: tras {a.esperar} s main sigue con la edición del {actual}. "
                  f"Flujo de la rama: {estado_flujo(rama)}")
            return 1
        time.sleep(20)


def cmd_imagenes(a):
    carpeta = a.carpeta
    nombres = sorted(f for f in os.listdir(carpeta) if f.lower().endswith((".jpg", ".jpeg", ".png")))
    if not nombres:
        raise SystemExit(f"No hay imágenes en {carpeta}")
    archivos = {f"{a.fecha}/{n}": open(os.path.join(carpeta, n), "rb").read() for n in nombres}
    rama = a.rama or f"instagram-media-{a.fecha}"
    try:
        crear_rama(rama, archivos, f"Imágenes de Instagram {a.fecha}", padre=False)
    except Exception as e:
        print(f"IMAGENES_FALLO: {e}")
        return 1
    print(f"IMAGENES_OK: {len(nombres)} imágenes en la rama {rama}")
    return 0


def cmd_comprobar(a):
    ok, actual = web_tiene(a.fecha)
    print("WEB_OK" if ok else f"WEB_FALLO: main tiene la edición del {actual}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("edicion")
    e.add_argument("--fecha", required=True)
    e.add_argument("--mensaje", required=True)
    e.add_argument("--esperar", type=int, default=480)
    e.add_argument("--raiz", default=RAIZ)
    e.add_argument("archivos", nargs="+")
    i = sub.add_parser("imagenes")
    i.add_argument("--fecha", required=True)
    i.add_argument("--carpeta", required=True)
    i.add_argument("--rama")
    c = sub.add_parser("comprobar")
    c.add_argument("--fecha", required=True)
    a = ap.parse_args()
    return {"edicion": cmd_edicion, "imagenes": cmd_imagenes, "comprobar": cmd_comprobar}[a.orden](a)


if __name__ == "__main__":
    sys.exit(main())
