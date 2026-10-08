#!/usr/bin/env python3
"""Publica en Instagram la siguiente publicación pendiente del día. Lo ejecuta GitHub Actions cada 15 minutos.

Lee instagram/<hoy>/cola.json (hoy = fecha en Madrid) y publica como mucho UNA publicación por ejecución:
la más antigua cuya hora ya ha llegado, que no conste como publicada y que respete una separación mínima con
la anterior. Lo que hace queda en instagram/<hoy>/estado.json (el flujo de trabajo lo guarda en el repositorio).

Variables de entorno
  IG_TOKEN    token de larga duración de Instagram (secreto del repositorio)
  IG_CLAVE    clave con la que se cifra el token renovado en instagram/token.enc (secreto del repositorio)
  IG_ACTIVO   "si" para publicar de verdad; cualquier otro valor = simulación (variable del repositorio)
  GITHUB_TOKEN, GITHUB_REPOSITORY   (los pone GitHub) para abrir un aviso si algo falla
  IG_HOST, IG_AHORA, IG_ESPERA      solo para pruebas: otra API, otra hora de Madrid, otro sondeo
Código de salida: 0 si no había nada que hacer o todo ha ido bien; 1 si algo ha fallado.
"""
import hashlib, json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MADRID = ZoneInfo("Europe/Madrid")
HOST = os.environ.get("IG_HOST", "https://graph.instagram.com").rstrip("/")
API = HOST + "/v25.0"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(RAIZ, "instagram")
TOKEN_ENC = os.path.join(DIR, "token.enc")
SEPARACION = timedelta(minutes=40)   # mínimo entre dos publicaciones si se acumulan retrasos
MAX_INTENTOS = 3                     # por publicación; después se salta
RENOVAR_CADA = timedelta(days=7)     # el token dura 60 días; se renueva con mucho margen
ESPERA = float(os.environ.get("IG_ESPERA", "4"))
resumen = []


def log(msg):
    print(msg, flush=True)
    resumen.append(msg)


def ahora():
    v = os.environ.get("IG_AHORA")
    return datetime.fromisoformat(v).replace(tzinfo=MADRID) if v else datetime.now(MADRID)


class ApiError(Exception):
    def __init__(self, status, body):
        self.status, self.body = status, body
        err = body.get("error", {}) if isinstance(body, dict) else {}
        self.code = err.get("code")
        super().__init__(f"HTTP {status}: {err.get('message') or body}")


def api(method, path, token=None, params=None, body=None):
    url = path if path.startswith("http") else API + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as ex:
        try:
            payload = json.loads(ex.read() or b"{}")
        except ValueError:
            payload = {}
        raise ApiError(ex.code, payload) from None


# ---------- token ----------
def huella(t):
    return hashlib.sha256((t or "").encode()).hexdigest()[:16]


def openssl(args, data):
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-a", "-A", *args,
                        "-pass", "env:IG_CLAVE"], input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip() or "openssl ha fallado")
    return r.stdout


def leer_token_guardado():
    if not (os.path.exists(TOKEN_ENC) and os.environ.get("IG_CLAVE")):
        return None
    try:
        return json.loads(openssl(["-d"], open(TOKEN_ENC, "rb").read().strip() + b"\n"))
    except Exception as ex:  # clave cambiada o archivo dañado: se vuelve al secreto
        log(f"Aviso: no se ha podido leer instagram/token.enc ({ex}); uso el secreto IG_TOKEN.")
        return None


def guardar_token(info):
    if not os.environ.get("IG_CLAVE"):
        log("Aviso: falta el secreto IG_CLAVE; el token renovado no se puede guardar.")
        return
    open(TOKEN_ENC, "wb").write(openssl(["-salt"], json.dumps(info).encode()) + b"\n")


def obtener_token():
    """Devuelve (token, info). El guardado cifrado manda mientras proceda del mismo IG_TOKEN."""
    secreto = os.environ.get("IG_TOKEN", "").strip()
    info = leer_token_guardado()
    if info and secreto and info.get("origen") != huella(secreto):
        log("El secreto IG_TOKEN ha cambiado: se usa el nuevo y se descarta el guardado.")
        info = None
    if info and info.get("token"):
        return info["token"], info
    if not secreto:
        return None, None
    return secreto, {"token": secreto, "origen": huella(secreto), "renovado": None, "intento": None}


def renovar_si_toca(token, info, ahora_utc):
    """Renueva el token si hace más de RENOVAR_CADA (o no consta) y guarda el resultado cifrado."""
    ult = info.get("renovado")
    intento = info.get("intento")
    if ult and ahora_utc - datetime.fromisoformat(ult) < RENOVAR_CADA:
        return token
    if intento and ahora_utc - datetime.fromisoformat(intento) < timedelta(hours=6):
        return token
    info["intento"] = ahora_utc.isoformat(timespec="seconds")
    try:
        r = api("GET", HOST + "/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": token})
        nuevo = r.get("access_token")
        if nuevo:
            info.update(token=nuevo, renovado=ahora_utc.isoformat(timespec="seconds"),
                        caduca_dias=round(r.get("expires_in", 0) / 86400, 1))
            log(f"Token renovado: válido otros {info['caduca_dias']} días.")
            token = nuevo
    except ApiError as ex:  # p. ej. el token tiene menos de 24 horas; se reintenta en 6 horas
        log(f"Aviso: no se ha podido renovar el token todavía ({ex}).")
    guardar_token(info)
    return token


# ---------- utilidades ----------
def leer_json(path, defecto):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else defecto


def escribir_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def comprobar_imagenes(urls):
    for u in urls:
        req = urllib.request.Request(u, method="GET")
        with urllib.request.urlopen(req, timeout=30) as r:
            tipo = r.headers.get("Content-Type", "")
            r.read(1)
            if r.status != 200 or "jpeg" not in tipo:
                raise RuntimeError(f"{u} responde {r.status} con tipo {tipo!r}")


def esperar(token, cid, limite=300):
    t0 = time.time()
    while True:
        st = api("GET", f"/{cid}", token, {"fields": "status_code"}).get("status_code")
        if st in ("FINISHED", "PUBLISHED"):
            return
        if st in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"el contenedor {cid} ha terminado en {st}")
        if time.time() - t0 > limite:
            raise RuntimeError(f"el contenedor {cid} sigue en {st} tras {limite} s")
        time.sleep(ESPERA)


def cuenta(token):
    me = api("GET", "/me", token, {"fields": "user_id,username"})
    if isinstance(me.get("data"), list) and me["data"]:
        me = me["data"][0]
    return str(me.get("user_id") or me.get("id")), me.get("username", "")


def ya_publicada(token, ig_id, post, desde):
    """Evita duplicados si una ejecución anterior publicó pero no pudo guardar el estado."""
    primera = post["texto"].split("\n", 1)[0].strip()
    r = api("GET", f"/{ig_id}/media", token, {"fields": "id,caption,timestamp,permalink", "limit": 12})
    for m in r.get("data", []):
        cap = (m.get("caption") or "").split("\n", 1)[0].strip()
        ts = m.get("timestamp", "")
        try:
            reciente = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z") >= desde
        except ValueError:
            reciente = True
        if cap == primera and reciente:
            return m
    return None


def avisar(titulo, cuerpo):
    tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (tok and repo):
        return
    base = f"https://api.github.com/repos/{repo}"
    hdr = {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json", "User-Agent": "the-daily-ivan"}
    try:
        q = urllib.request.Request(base + "/issues?state=open&labels=instagram&per_page=1", headers=hdr)
        abiertos = json.loads(urllib.request.urlopen(q, timeout=30).read())
        if abiertos:
            url, data = f"{base}/issues/{abiertos[0]['number']}/comments", {"body": f"**{titulo}**\n\n{cuerpo}"}
        else:
            url, data = base + "/issues", {"title": "Instagram: fallo al publicar", "labels": ["instagram"],
                                           "body": f"**{titulo}**\n\n{cuerpo}\n\nCierra este aviso cuando esté resuelto."}
        urllib.request.urlopen(urllib.request.Request(url, data=json.dumps(data).encode(), headers=hdr, method="POST"), timeout=30)
    except Exception as ex:
        log(f"Aviso: no se ha podido abrir el aviso en GitHub ({ex}).")


# ---------- principal ----------
def main():
    now = ahora()
    hoy = now.date().isoformat()
    cola_p, estado_p = os.path.join(DIR, hoy, "cola.json"), os.path.join(DIR, hoy, "estado.json")
    activo = os.environ.get("IG_ACTIVO", "").strip().lower() in ("si", "sí", "true", "1")
    if not os.path.exists(cola_p):
        log(f"{now:%H:%M} · No hay cola para {hoy}; nada que hacer.")
        return 0
    cola = json.load(open(cola_p, encoding="utf-8"))
    estado = leer_json(estado_p, {"publicadas": {}, "errores": {}, "simuladas": {}})
    estado.setdefault("simuladas", {})
    hechas = estado["publicadas"]
    # en simulación, lo ya simulado cuenta como hecho para no repetir la prueba cada 15 minutos
    vistas = hechas if activo else {**hechas, **{k: {"hora": v} for k, v in estado["simuladas"].items()}}

    pendientes = []
    for p in cola["publicaciones"]:
        h = datetime.combine(now.date(), datetime.strptime(p["hora"], "%H:%M").time(), MADRID)
        intentos = estado["errores"].get(p["id"], {}).get("intentos", 0)
        if p["id"] not in vistas and h <= now and intentos < MAX_INTENTOS:
            pendientes.append(p)
    if not pendientes:
        quedan = [p["hora"] for p in cola["publicaciones"] if p["id"] not in vistas]
        log(f"{now:%H:%M} · Nada pendiente ahora. Publicadas {len(hechas)}/{len(cola['publicaciones'])}; "
            f"próximas: {', '.join(quedan) or 'ninguna'}.")
        return 0
    if vistas:
        ultima = max(datetime.fromisoformat(v["hora"]) for v in vistas.values())
        if now - ultima < SEPARACION:
            log(f"{now:%H:%M} · Hay {len(pendientes)} pendiente(s), pero la última salió a las {ultima:%H:%M}; "
                f"se respeta la separación de {SEPARACION.seconds // 60} min.")
            return 0
    post = pendientes[0]
    log(f"{now:%H:%M} · Toca: {post['id']} (prevista {post['hora']}, {len(post['imagenes'])} imágenes).")

    try:
        comprobar_imagenes(post["imagenes"])
    except Exception as ex:
        log(f"Las imágenes aún no están disponibles ({ex}); se reintentará en la próxima ejecución.")
        return 0

    token, info = obtener_token()
    if not token:
        log("Falta el secreto IG_TOKEN: no se puede consultar ni publicar.")
        return 0 if not activo else 1
    try:
        try:
            ig_id, usuario = cuenta(token)
        except ApiError:
            secreto = os.environ.get("IG_TOKEN", "").strip()
            if not secreto or secreto == token:
                raise
            log("El token guardado ya no sirve; pruebo con el secreto IG_TOKEN.")
            token, info = secreto, {"token": secreto, "origen": huella(secreto), "renovado": None, "intento": None}
            ig_id, usuario = cuenta(token)
            guardar_token(info)
        token = renovar_si_toca(token, info, now.astimezone(ZoneInfo("UTC")))
    except ApiError as ex:
        log(f"El token no es válido o la cuenta no responde: {ex}")
        if activo:
            avisar("El token de Instagram no funciona", f"{ex}\n\nGenera un token nuevo y actualiza el secreto IG_TOKEN.")
        return 1 if activo else 0
    esperado = cola.get("usuario", "").lower()
    if esperado and usuario.lower() != esperado:
        log(f"El token es de @{usuario}, pero la cola es para @{esperado}: no se publica nada.")
        if activo:
            avisar("Cuenta de Instagram equivocada", f"Token de @{usuario}; cola para @{esperado}.")
        return 1 if activo else 0

    if not activo:
        estado["simuladas"][post["id"]] = now.isoformat(timespec="seconds")
        escribir_json(estado_p, estado)
        log(f"SIMULACIÓN (IG_ACTIVO no es «si»): token válido para @{usuario}; imágenes accesibles. "
            f"Se habría publicado {post['id']}.")
        return 0

    try:
        previa = ya_publicada(token, ig_id, post, now.replace(hour=0, minute=0, second=0))
        if previa:
            hechas[post["id"]] = {"media_id": previa["id"], "permalink": previa.get("permalink"),
                                  "hora": now.isoformat(timespec="seconds"), "nota": "ya estaba publicada"}
            escribir_json(estado_p, estado)
            log(f"{post['id']} ya estaba en la cuenta ({previa.get('permalink')}); se anota sin repetir.")
            return 0
        hijos = []
        for u in post["imagenes"]:
            hijos.append(api("POST", f"/{ig_id}/media", token, body={"image_url": u, "is_carousel_item": True})["id"])
        for h in hijos:
            esperar(token, h)
        cid = api("POST", f"/{ig_id}/media", token,
                  body={"media_type": "CAROUSEL", "children": ",".join(hijos), "caption": post["texto"]})["id"]
        esperar(token, cid)
        mid = api("POST", f"/{ig_id}/media_publish", token, body={"creation_id": cid})["id"]
        try:
            link = api("GET", f"/{mid}", token, {"fields": "permalink"}).get("permalink")
        except ApiError:
            link = None
        hechas[post["id"]] = {"media_id": mid, "permalink": link, "hora": now.isoformat(timespec="seconds")}
        estado["errores"].pop(post["id"], None)
        escribir_json(estado_p, estado)
        log(f"Publicada {post['id']}: {link or mid}")
        return 0
    except Exception as ex:
        e = estado["errores"].setdefault(post["id"], {"intentos": 0})
        e.update(intentos=e["intentos"] + 1, ultimo=str(ex)[:500], hora=now.isoformat(timespec="seconds"))
        escribir_json(estado_p, estado)
        log(f"Error al publicar {post['id']} (intento {e['intentos']} de {MAX_INTENTOS}): {ex}")
        if e["intentos"] >= MAX_INTENTOS:
            avisar(f"No se ha podido publicar {post['id']}", f"Último error: {ex}")
        return 1


if __name__ == "__main__":
    try:
        code = main()
    finally:
        out = os.environ.get("GITHUB_STEP_SUMMARY")
        if out and resumen:
            with open(out, "a", encoding="utf-8") as f:
                f.write("### Instagram\n\n" + "\n".join(f"- {r}" for r in resumen) + "\n")
    sys.exit(code)
