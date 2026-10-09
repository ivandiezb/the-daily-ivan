#!/usr/bin/env python3
"""Turn the artifact page into a standalone public web page (GitHub Pages).

Usage: python3 publicar_web.py <page.html> <site_dir>

The artifact host wraps the page in its own <html>/<head>; a normal web host does not, so this adds
the document skeleton, charset, viewport, a favicon, link-preview tags (WhatsApp, Telegram…) and
"noindex" so search engines leave the page alone. It writes <site_dir>/index.html and .nojekyll.
The archive files (archivo/*.json) are copied separately by the daily task.
"""
import html, json, os, re, sys


def main(page, site):
    src = open(page, encoding="utf-8").read()
    # Artifact "read" can return the page inside the host's own <!doctype><html><head>…<body> wrapper:
    # keep only the page itself, from its <title> on.
    i = src.find("<title>")
    if i > 0:
        src = re.sub(r"\s*</body>\s*</html>\s*$", "", src[i:])
    m = re.search(r"</style>", src)
    if not src.lstrip().startswith("<title>") or not m:
        raise SystemExit("Unexpected page layout: expected <title> … <style>…</style> at the top")
    head, body = src[: m.end()], src[m.end():]
    d = json.loads(re.search(r'<script type="application/json" id="edition">(.*?)</script>', src, re.S).group(1))
    title = html.unescape(re.search(r"<title>(.*?)</title>", src, re.S).group(1)).strip()
    slogan_m = re.search(r'id="slogan">(.*?)</p>', src, re.S)
    slogan = html.unescape(slogan_m.group(1)).strip() if slogan_m else ""
    desc = f"{d.get('fechaTexto', '')}. {slogan}".strip(". ")
    icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
            "%3Crect width='64' height='64' rx='12' fill='%23FFEFA0'/%3E"
            "%3Ctext x='32' y='44' font-family='Arial' font-weight='700' font-size='30' text-anchor='middle' fill='%233D3400'%3EDI%3C/text%3E%3C/svg%3E")
    pre = ('<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
           '<meta name="robots" content="noindex,nofollow">\n'
           '<meta name="color-scheme" content="light dark">\n'
           f'<meta name="description" content="{html.escape(desc)}">\n'
           f'<meta property="og:title" content="{html.escape(title)}">\n'
           f'<meta property="og:description" content="{html.escape(desc)}">\n'
           '<meta property="og:type" content="website">\n'
           f'<link rel="icon" href="{icon}">\n')
    out = pre + head + "\n</head>\n<body>\n" + body.lstrip("\n") + "\n</body>\n</html>\n"
    os.makedirs(site, exist_ok=True)
    open(os.path.join(site, "index.html"), "w", encoding="utf-8").write(out)
    open(os.path.join(site, ".nojekyll"), "w").close()
    print(os.path.join(site, "index.html"))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
