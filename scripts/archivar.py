#!/usr/bin/env python3
"""Add editions to the monthly archive that the page's «Ediciones» calendar reads.

Usage: python3 archivar.py <archivo_dir> <page.html> [<page.html> ...]

For each page it reads the edition JSON (<script id="edition">) and stores it under its fechaISO in
<archivo_dir>/<AAAA-MM>.json, then rewrites <archivo_dir>/<AAAA-MM>-dias.json (sorted list of days).
Existing month files in <archivo_dir> are loaded first, so download them from the artifact before
running this. Prints one line per published path that changed, e.g. "archivo/2026-10.json", ready to
map in the Artifact publish `files` argument.
"""
import json, os, re, sys


def edition(page):
    src = open(page, encoding="utf-8").read()
    m = re.search(r'<script type="application/json" id="edition">(.*?)</script>', src, re.S)
    if not m:
        raise SystemExit(f"{page}: no edition JSON found")
    d = json.loads(m.group(1))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.get("fechaISO", "")):
        raise SystemExit(f"{page}: missing or invalid fechaISO")
    return d


def main(folder, pages):
    os.makedirs(folder, exist_ok=True)
    months, changed = {}, set()
    for page in pages:
        d = edition(page)
        ym = d["fechaISO"][:7]
        if ym not in months:
            path = os.path.join(folder, f"{ym}.json")
            months[ym] = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
            if not isinstance(months[ym], dict):
                raise SystemExit(f"{path}: unexpected format")
        months[ym][d["fechaISO"]] = d
        changed.add(ym)
    for ym in sorted(changed):
        data = dict(sorted(months[ym].items()))
        with open(os.path.join(folder, f"{ym}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        with open(os.path.join(folder, f"{ym}-dias.json"), "w", encoding="utf-8") as f:
            json.dump({"dias": list(data)}, f, ensure_ascii=False)
        print(f"archivo/{ym}.json")
        print(f"archivo/{ym}-dias.json")
        print(f"  ({len(data)} ediciones en {ym}: {', '.join(k[8:] for k in data)})", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
