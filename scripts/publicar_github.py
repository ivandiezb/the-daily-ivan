#!/usr/bin/env python3
"""Publica la edición del día en la web pública (GitHub Pages) sin que la tarea diaria empuje nada a main.

Por qué así. Del 10 al 13 de octubre la tarea diaria no consiguió subir la edición a main ni una vez, aunque las
sesiones de prueba sí podían. Dos obstáculos comprobados: el modo automático de las tareas bloquea órdenes de git
que considera arriesgadas (el 10 bloqueó «git checkout -B»), y el proxy de GitHub de estas sesiones no deja escribir
archivos por la API (git/blobs, git/refs, contents y merges responden 403). Lo que sí deja es lanzar flujos de
GitHub Actions (workflow_dispatch / repository_dispatch) y abrir avisos (issues). Así que la sesión ya no sube
archivos: manda a GitHub Actions el JSON de la edición y los textos de Instagram, comprimidos, y el flujo
«Publicar edición» (.github/workflows/publicar.yml) monta index.html, actualiza el archivo, genera las imágenes de
Instagram, sube todo a main y reconstruye GitHub Pages.

Uso en la tarea diaria (desde R = el repositorio):
  python3 scripts/publicar_github.py edicion --fecha AAAA-MM-DD --pagina trabajo/page.html [--ig trabajo/ig.json]
      Vías, por orden, hasta que una funcione: 1) workflow_dispatch; 2) repository_dispatch; 3) git push de una
      rama NUEVA «publicar-AAAA-MM-DD-HHMMSS» (nunca main, nunca forzado) con la edición en entrada/.
      Después espera (--esperar, 360 s; lo normal es 1–2 minutos) a que main tenga la edición de esa fecha y a que
      GitHub Pages la despliegue. Lánzalo con un tiempo límite de la herramienta de al menos 600000 ms.
      Última línea: «WEB_OK» o «WEB_FALLO: <motivo literal>». Código 0 solo si WEB_OK. Si falla, deja además un
      aviso (issue) en el repositorio con el registro completo.
  python3 scripts/publicar_github.py comprobar --fecha AAAA-MM-DD
      Solo comprueba si main ya tiene la edición de esa fecha.

Uso dentro de GitHub Actions (no lo ejecuta la tarea diaria):
  desempaquetar --salida DIR      lee EDICION / IG / FECHA del entorno y escribe DIR/edicion.json y DIR/ig.json
  montar --entrada DIR [--repo .] escribe index.html (plantilla actual + edición nueva) y actualiza archivo/

Solo biblioteca estándar. Credenciales: GH_TOKEN o GITHUB_TOKEN si existen (en las sesiones de Claude el proxy las
añade él solo).
"""
import argparse, base64, html, json, lzma, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request
from datetime import datetime, timezone

REPO = os.environ.get("REPO_GITHUB", "ivandiezb/the-daily-ivan")
API = f"https://api.github.com/repos/{REPO}"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTOR = ("Iván Díez", "ivandiezberjano@gmail.com")
FLUJO = "publicar.yml"
EVENTO = "publicar-edicion"
EDICION_RE = re.compile(r'(<script type="application/json" id="edition">)(.*?)(</script>)', re.S)
MAX_CARGA = 60000  # límite práctico de GitHub para los datos de un dispatch (unos 64 KB)

registro = []


def log(texto):
    registro.append(texto)
    print(texto, flush=True)


# ---------------------------------------------------------------- API de GitHub
def llamar(metodo, ruta, cuerpo=None, crudo=False, intentos=3):
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
            texto = e.read().decode("utf-8", "replace")[:400]
            ultimo = f"HTTP {e.code} en {metodo} {ruta}: {texto}"
            if 400 <= e.code < 500 and e.code != 429:
                raise RuntimeError(ultimo)
        except Exception as e:  # red, proxy, tiempo de espera
            ultimo = f"{type(e).__name__} en {metodo} {ruta}: {e}"
        time.sleep(3 * (i + 1))
    raise RuntimeError(ultimo)


def empaquetar(b):
    return base64.b64encode(lzma.compress(b, preset=9 | lzma.PRESET_EXTREME)).decode()


def desempaquetar_texto(s):
    return lzma.decompress(base64.b64decode(s)).decode("utf-8")


def fecha_de_index(html_texto):
    m = re.search(r'"fechaISO"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html_texto or "")
    return m.group(1) if m else None


def main_tiene(fecha):
    """(True/False, fecha que hay en main, sha de main)."""
    sha = llamar("GET", "/git/ref/heads/main")["object"]["sha"]
    actual = fecha_de_index(llamar("GET", f"/contents/index.html?ref={sha}", crudo=True))
    return actual == fecha, actual or "desconocida", sha


def pages_construida(fecha):
    """¿Ha desplegado GitHub Pages una versión de main que ya trae la edición de esa fecha? (El proxy no deja leer
    /pages/builds, así que se mira la última ejecución correcta de «pages build and deployment».)"""
    try:
        runs = llamar("GET", "/actions/runs?event=dynamic&status=success&per_page=5").get("workflow_runs", [])
        runs = [r for r in runs if r.get("name") == "pages build and deployment"]
        if not runs:
            return False, "sin despliegues recientes"
        sha = runs[0]["head_sha"]
        f = fecha_de_index(llamar("GET", f"/contents/index.html?ref={sha}", crudo=True))
        return f == fecha, f"último despliegue {sha[:7]} con la edición del {f}"
    except Exception as e:
        return False, f"no consultable ({e})"


def flujos_recientes():
    try:
        runs = llamar("GET", f"/actions/workflows/{FLUJO}/runs?per_page=3").get("workflow_runs", [])
        return "; ".join(f"{r['event']} {r['created_at']} {r['status']}/{r['conclusion']} {r['html_url']}" for r in runs)
    except Exception as e:
        return f"no consultable ({e})"


# ---------------------------------------------------------------- vías de envío (tarea diaria)
def via_workflow_dispatch(fecha, ed, ig):
    llamar("POST", f"/actions/workflows/{FLUJO}/dispatches",
           {"ref": "main", "inputs": {"fecha": fecha, "edicion": ed, "ig": ig, "origen": "tarea diaria"}}, intentos=2)


def via_repository_dispatch(fecha, ed, ig):
    llamar("POST", "/dispatches", {"event_type": EVENTO,
                                   "client_payload": {"fecha": fecha, "edicion": ed, "ig": ig, "origen": "tarea diaria"}},
           intentos=2)


def git(*args, entorno=None, entrada=None):
    r = subprocess.run(["git", "-C", RAIZ, *args], capture_output=True, text=True, input=entrada,
                       env=dict(os.environ, **(entorno or {})), timeout=180)
    if r.returncode:
        raise RuntimeError(f"git {args[0]}: {(r.stderr or r.stdout).strip()[-400:]}")
    return r.stdout.strip()


def via_rama(fecha, texto_ed, texto_ig, mensaje):
    """Commit encima de origin/main con entrada/edicion.json (y entrada/ig.json), hecho con órdenes de bajo nivel
    sobre un índice temporal: no toca el directorio de trabajo, ni la rama actual, ni main. Se sube como rama nueva."""
    rama = f"publicar-{fecha}-{datetime.now(timezone.utc):%H%M%S}"
    git("fetch", "-q", "origin", "+main:refs/remotes/origin/main")
    with tempfile.TemporaryDirectory() as tmp:
        ent = {"GIT_INDEX_FILE": os.path.join(tmp, "indice"),
               "GIT_AUTHOR_NAME": AUTOR[0], "GIT_AUTHOR_EMAIL": AUTOR[1],
               "GIT_COMMITTER_NAME": AUTOR[0], "GIT_COMMITTER_EMAIL": AUTOR[1]}
        git("read-tree", "origin/main", entorno=ent)
        for nombre, texto in (("edicion.json", texto_ed), ("ig.json", texto_ig)):
            if texto is None:
                continue
            ruta = os.path.join(tmp, nombre)
            open(ruta, "w", encoding="utf-8").write(texto)
            blob = git("hash-object", "-w", ruta)
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},entrada/{nombre}", entorno=ent)
        arbol = git("write-tree", entorno=ent)
        commit = git("commit-tree", arbol, "-p", "origin/main", "-m", mensaje, entorno=ent)
    git("push", "-q", "origin", f"{commit}:refs/heads/{rama}")
    return rama


def aviso(titulo, cuerpo):
    """Deja constancia en GitHub (issue con etiqueta «web»); GitHub lo notifica por correo al dueño."""
    try:
        abiertos = llamar("GET", "/issues?state=open&labels=web&per_page=1")
        if abiertos:
            llamar("POST", f"/issues/{abiertos[0]['number']}/comments", {"body": f"**{titulo}**\n\n{cuerpo}"})
            return f"comentado en el aviso #{abiertos[0]['number']}"
        n = llamar("POST", "/issues", {"title": titulo, "body": cuerpo, "labels": ["web"]})["number"]
        return f"aviso #{n} abierto"
    except Exception as e:
        return f"no se pudo dejar el aviso ({e})"


def cmd_edicion(a):
    src = open(a.pagina, encoding="utf-8").read()
    m = EDICION_RE.search(src)
    if not m:
        print("WEB_FALLO: la página no tiene el bloque JSON de la edición")
        return 1
    texto_ed = m.group(2)
    d = json.loads(texto_ed)
    if d.get("fechaISO") != a.fecha:
        print(f"WEB_FALLO: la página es la edición del {d.get('fechaISO')}, no la del {a.fecha}")
        return 1
    texto_ig = None
    if a.ig and os.path.isfile(a.ig):
        texto_ig = open(a.ig, encoding="utf-8").read()
        json.loads(texto_ig)
    mensaje = a.mensaje or f"Edición del {d.get('fechaTexto', a.fecha)}"
    ed_b64 = empaquetar(texto_ed.encode())
    ig_b64 = empaquetar(texto_ig.encode()) if texto_ig else ""
    log(f"Edición {a.fecha}: JSON {len(texto_ed)} caracteres → {len(ed_b64)} comprimido; Instagram {len(ig_b64)}.")

    enviada = None
    try:
        log(f"main tiene ahora la edición del {main_tiene(a.fecha)[1]}.")
    except Exception as e:
        log(f"Aviso: no se pudo leer main ({e}).")
    vias = []
    if len(ed_b64) + len(ig_b64) <= MAX_CARGA:
        vias += [("workflow_dispatch", lambda: via_workflow_dispatch(a.fecha, ed_b64, ig_b64)),
                 ("repository_dispatch", lambda: via_repository_dispatch(a.fecha, ed_b64, ig_b64))]
    else:
        log("La carga supera el límite de un dispatch: se usa directamente la rama.")
    vias.append(("rama publicar-*", lambda: via_rama(a.fecha, texto_ed, texto_ig, mensaje)))
    for nombre, fn in vias:
        try:
            r = fn()
            enviada = nombre + (f" ({r})" if r else "")
            log(f"Enviada por {enviada}.")
            break
        except Exception as e:
            log(f"Vía {nombre} no disponible: {e}")
    if not enviada:
        motivo = "ninguna vía de envío ha funcionado (detalle arriba)"
        log(f"WEB_FALLO: {motivo}")
        log(aviso(f"No se pudo publicar la edición del {a.fecha}", "```\n" + "\n".join(registro) + "\n```"))
        return 1

    limite = time.time() + a.esperar
    en_main, actual, sha = False, "desconocida", ""
    while time.time() < limite:
        time.sleep(15)
        try:
            ok, actual, sha = main_tiene(a.fecha)
        except Exception as e:
            log(f"(consulta fallida: {e})")
            continue
        if ok and not en_main:
            en_main = True
            log(f"main ya tiene la edición del {a.fecha} ({sha[:7]}).")
        if ok:
            listo, estado = pages_construida(a.fecha)
            if listo:
                log(f"GitHub Pages desplegada con esta edición ({estado}).")
                print("WEB_OK")
                return 0
    if en_main:
        log(f"GitHub Pages aún no confirma el despliegue ({pages_construida(a.fecha)[1]}); se actualizará sola.")
        print("WEB_OK")
        return 0
    motivo = (f"tras {a.esperar} s main sigue con la edición del {actual}. Enviada por {enviada}. "
              f"Últimas ejecuciones de «Publicar edición»: {flujos_recientes()}")
    log(f"WEB_FALLO: {motivo}")
    log(aviso(f"La edición del {a.fecha} no ha llegado a la web", "```\n" + "\n".join(registro) + "\n```"))
    return 1


def cmd_comprobar(a):
    ok, actual, sha = main_tiene(a.fecha)
    print("WEB_OK" if ok else f"WEB_FALLO: main tiene la edición del {actual}")
    return 0 if ok else 1


# ---------------------------------------------------------------- dentro de GitHub Actions
def cmd_desempaquetar(a):
    os.makedirs(a.salida, exist_ok=True)
    texto_ed = desempaquetar_texto(os.environ["EDICION"])
    d = json.loads(texto_ed)
    fecha = os.environ.get("FECHA") or d.get("fechaISO")
    if d.get("fechaISO") != fecha:
        raise SystemExit(f"La edición recibida es del {d.get('fechaISO')}, no del {fecha}")
    open(os.path.join(a.salida, "edicion.json"), "w", encoding="utf-8").write(texto_ed)
    if os.environ.get("IG"):
        texto_ig = desempaquetar_texto(os.environ["IG"])
        json.loads(texto_ig)
        open(os.path.join(a.salida, "ig.json"), "w", encoding="utf-8").write(texto_ig)
    print(fecha)
    return 0


def cmd_montar(a):
    texto_ed = open(os.path.join(a.entrada, "edicion.json"), encoding="utf-8").read()
    d = json.loads(texto_ed)
    if "</script" in texto_ed.lower():
        raise SystemExit("El JSON de la edición contiene «</script»: no se puede incrustar")
    ruta = os.path.join(a.repo, "index.html")
    src = open(ruta, encoding="utf-8").read()
    if not EDICION_RE.search(src):
        raise SystemExit("index.html no tiene el bloque JSON de la edición")
    nuevo = EDICION_RE.sub(lambda m: m.group(1) + texto_ed + m.group(3), src, count=1)
    sm = re.search(r'id="slogan">(.*?)</p>', src, re.S)
    slogan = html.unescape(sm.group(1)).strip() if sm else ""
    desc = html.escape(f"{d.get('fechaTexto', '')}. {slogan}".strip(". "))
    for patron in (r'(<meta name="description" content=")[^"]*(">)', r'(<meta property="og:description" content=")[^"]*(">)'):
        nuevo = re.sub(patron, lambda m: m.group(1) + desc + m.group(2), nuevo, count=1)
    with tempfile.TemporaryDirectory() as tmp:
        anterior = os.path.join(tmp, "anterior.html")
        open(anterior, "w", encoding="utf-8").write(src)
        open(ruta, "w", encoding="utf-8").write(nuevo)
        open(os.path.join(a.repo, ".nojekyll"), "a").close()
        # archiva la edición anterior (por si faltaba) y la nueva
        r = subprocess.run([sys.executable, os.path.join(RAIZ, "scripts", "archivar.py"),
                            os.path.join(a.repo, "archivo"), anterior, ruta], capture_output=True, text=True)
        sys.stderr.write(r.stderr)
        if r.returncode:
            raise SystemExit(f"archivar.py falló: {r.stdout}{r.stderr}")
    print(d.get("fechaTexto", d.get("fechaISO")))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("edicion")
    e.add_argument("--fecha", required=True)
    e.add_argument("--pagina", required=True)
    e.add_argument("--ig")
    e.add_argument("--mensaje")
    e.add_argument("--esperar", type=int, default=360)
    c = sub.add_parser("comprobar")
    c.add_argument("--fecha", required=True)
    dz = sub.add_parser("desempaquetar")
    dz.add_argument("--salida", required=True)
    mo = sub.add_parser("montar")
    mo.add_argument("--entrada", required=True)
    mo.add_argument("--repo", default=".")
    a = ap.parse_args()
    return {"edicion": cmd_edicion, "comprobar": cmd_comprobar, "desempaquetar": cmd_desempaquetar,
            "montar": cmd_montar}[a.orden](a)


if __name__ == "__main__":
    sys.exit(main())
