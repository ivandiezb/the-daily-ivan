# The Daily Iván

Briefing diario de noticias en español: mercados, inversión, geopolítica, España, internacional, vivienda, naturaleza y deportes, con fuentes enlazadas.

- `index.html`: la edición del día (se actualiza cada mañana de forma automática).
- `archivo/`: ediciones anteriores, por meses; las abre el calendario «Ediciones» de la página.
- `instagram/<fecha>/cola.json`: publicaciones de Instagram del día (hora, texto, hashtags e imágenes); `estado.json` anota lo publicado.
- `scripts/`: herramientas. `instagram_tarjetas.py` genera los carruseles (las imágenes van a la rama `instagram-media`, que solo guarda el último día); `ig_publicar.py` los publica desde GitHub Actions (`.github/workflows/instagram.yml`).

### Flujo de cada día
1. **Recogida** (`.github/workflows/fuentes.yml`, rama `datos`): titulares del catálogo (`recoger_fuentes.py`) y cotizaciones de los valores que más se mueven (`valores.py`: Ibex 35, Euro Stoxx 50 y S&P 500, del servicio de datos de CNBC, con la evolución de la sesión para las minigráficas y el Russell 2000). La lanzan la tarea de la mañana (7:50) y la actualización de media tarde (16:49) con `publicar_github.py fuentes`, además de su horario propio. Antes de la apertura CNBC «pasa de día» las cotizaciones; entonces `valores.py` toma la variación de la caché `datos/valores/cotizaciones.json`, que guarda cada ejecución.
2. **Edición** (tarea programada de Claude): escribe el JSON de la edición, ejecuta `valores.py edicion` (bloque «Valores que más se mueven» y Russell 2000), valida con `validar_edicion.py` y monta la página de claude.ai con `pagina_claude.py` a partir de esta misma plantilla (`index.html`), para que las dos versiones compartan el diseño.
3. **Publicación**: `publicar_github.py edicion` manda la edición a `.github/workflows/publicar.yml`, que monta `index.html` con la plantilla de main, actualiza `archivo/`, genera la cola de Instagram y despliega GitHub Pages. El email sale de `build_email.py` (si con los valores pasara de 95 KB, va sin ese bloque).

### Instagram: configuración
- Secretos del repositorio (Settings → Secrets and variables → Actions → Secrets): `IG_TOKEN` (token de Instagram) e `IG_CLAVE` (una contraseña larga cualquiera, para guardar cifrado el token renovado).
- Variable del repositorio (misma pantalla, pestaña Variables): `IG_ACTIVO` = `si` para publicar de verdad. Sin ella, solo simula.
- Pausa: Actions → Instagram → «Disable workflow», o `IG_ACTIVO` = `no`.
