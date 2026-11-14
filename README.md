# The Daily Iván

Briefing diario de noticias en español: mercados, inversión, geopolítica, España, internacional, vivienda y naturaleza, con fuentes enlazadas.

- `index.html`: la edición del día (se actualiza cada mañana de forma automática).
- `archivo/`: ediciones anteriores, por meses; las abre el calendario «Ediciones» de la página.
- `instagram/<fecha>/cola.json`: publicaciones de Instagram del día (hora, texto, hashtags e imágenes); `estado.json` anota lo publicado.
- `scripts/`: herramientas. `instagram_tarjetas.py` genera los carruseles (las imágenes van a la rama `instagram-media`, que solo guarda el último día); `ig_publicar.py` los publica desde GitHub Actions (`.github/workflows/instagram.yml`).

### Instagram: configuración
- Secretos del repositorio (Settings → Secrets and variables → Actions → Secrets): `IG_TOKEN` (token de Instagram) e `IG_CLAVE` (clave para guardar cifrado el token renovado; genérala con `openssl rand -base64 32` y no la reutilices).
- Variable del repositorio (misma pantalla, pestaña Variables): `IG_ACTIVO` = `si` para publicar de verdad. Sin ella, solo simula.
- Pausa: Actions → Instagram → «Disable workflow», o `IG_ACTIVO` = `no`.

### Seguridad
- `instagram/token.enc` está cifrado, pero el repositorio y la web son públicos: cualquiera puede descargar el archivo. La clave `IG_CLAVE` debe ser larga y aleatoria, y conviene rotarla junto con el token de Meta si hay dudas.
- No publiques tokens, claves ni datos privados en issues, PRs ni capturas. Este repositorio no debe contener secretos en claro.
- `main` debería tener bloqueados los *force push*; los flujos automáticos publican directamente en `main`, así que revisa cualquier cambio de código que puedan ejecutar.
