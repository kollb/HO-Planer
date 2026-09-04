#!/usr/bin/env python3
"""Löst die Inline-Skripte der beiden Oberflächen aus den HTML-Dateien.

CodeQL wertet .html nicht aus. Die Skriptblöcke werden deshalb vor der Analyse
in codeql-inline-js/ geschrieben, damit auch das JavaScript der Oberflächen
geprüft wird. Das Verzeichnis ist generiert und liegt in der .gitignore.

Bewusst kein regulärer Ausdruck: HTML lässt sich damit nicht korrekt erkennen
(CodeQL-Meldung "Bad HTML filtering regexp"). Der Parser aus der
Standardbibliothek behandelt Groß-/Kleinschreibung und Zeichendaten in
<script> korrekt - dort dürfen Zeichenreferenzen nicht aufgelöst werden.
"""

import sys
from html.parser import HTMLParser
from pathlib import Path

QUELLEN = ("Docker/static/index.html", "StandAlone/ho-planer.html")
ZIEL = Path("codeql-inline-js")


class SkriptSammler(HTMLParser):
    """Sammelt den Inhalt aller <script>-Blöcke ohne src-Attribut."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bloecke: list[str] = []
        self._puffer: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        # Nur inline stehender Code interessiert, externe Dateien nicht.
        if any(name.lower() == "src" for name, _ in attrs):
            return
        self._puffer = []

    def handle_endtag(self, tag):
        if tag.lower() != "script" or self._puffer is None:
            return
        self.bloecke.append("".join(self._puffer))
        self._puffer = None

    def handle_data(self, data):
        if self._puffer is not None:
            self._puffer.append(data)


def main() -> int:
    ZIEL.mkdir(exist_ok=True)
    gefunden = 0

    for quelle in QUELLEN:
        pfad = Path(quelle)
        if not pfad.exists():
            print(f"übersprungen (fehlt): {quelle}")
            continue

        sammler = SkriptSammler()
        sammler.feed(pfad.read_text(encoding="utf-8"))
        sammler.close()

        bloecke = [block for block in sammler.bloecke if block.strip()]
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
