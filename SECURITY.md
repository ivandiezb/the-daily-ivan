# Seguridad

Este es un proyecto personal, pero publica una web y ejecuta flujos automáticos con acceso a una cuenta de Instagram.

- No abras issues públicos con tokens, claves, correos o capturas que los contengan.
- Para comunicar una vulnerabilidad, usa la pestaña **Security → Report a vulnerability** del repositorio (si está habilitada) o contacta con el propietario por GitHub.
- `instagram/token.enc` está cifrado y se publica intencionadamente para que el flujo pueda renovar el token; su seguridad depende de que `IG_CLAVE` sea una clave aleatoria larga.
- Los cambios en `main` ejecutan código con permisos de escritura y con el token de Instagram: revisa los PR y evita el *force push*.
