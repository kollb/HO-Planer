#!/usr/bin/env python3
"""Löst die Inline-Skripte der beiden Oberflächen aus den HTML-Dateien.

CodeQL wertet .html nicht aus. Die Skriptblöcke werden deshalb vor der Analyse
in .codeql-inline-js/ geschrieben, damit auch das JavaScript der Oberflächen
geprüft wird. Das Verzeichnis ist generiert und liegt in der .gitignore.
"""

import re
import sys
from pathlib import Path

QUELLEN = ("Docker/static/index.html", "StandAlone/ho-planer.html")
ZIEL = Path(".codeql-inline-js")

# Blöcke ohne src-Attribut: nur die stehen wirklich inline im Dokument.
MUSTER = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S)


def main() -> int:
    ZIEL.mkdir(exist_ok=True)
    gefunden = 0

    for quelle in QUELLEN:
        pfad = Path(quelle)
        if not pfad.exists():
            print(f"übersprungen (fehlt): {quelle}")
            continue

        bloecke = [block for block in MUSTER.findall(pfad.read_text(encoding="utf-8")) if block.strip()]
        if not bloecke:
            print(f"kein Inline-Skript in {quelle}")
            continue

        # ";" trennt die Blöcke, damit kein Block nahtlos in den nächsten läuft.
        ziel = ZIEL / f"{pfad.stem}.inline.js"
        ziel.write_text("\n;\n".join(bloecke), encoding="utf-8")
        print(f"{quelle} -> {ziel} ({sum(b.count(chr(10)) for b in bloecke)} Zeilen)")
        gefunden += 1

    if gefunden == 0:
        print("Achtung: kein Inline-Skript gefunden, CodeQL findet möglicherweise keinen Code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
