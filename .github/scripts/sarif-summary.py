#!/usr/bin/env python3
"""Fasst die SARIF-Ergebnisse der CodeQL-JavaScript-Analyse sichtbar zusammen.

Solange das Standard-Setup für Code Scanning aktiv ist, kann GitHub die SARIF
einer erweiterten (Advanced-)Konfiguration nicht übernehmen - beide schließen
sich gegenseitig aus. Damit die Inline-JavaScript-Befunde trotzdem sichtbar
sind, werden sie hier auf drei Wegen ausgegeben:

1. als Markdown in die Lauf-Zusammenfassung (`$GITHUB_STEP_SUMMARY`),
2. als Warnung pro Befund im Workflow-Log (erscheint als Annotation),
3. als kompakte Tabelle auf der Konsole.

Die vollständige SARIF-Datei wird zusätzlich als Workflow-Artefakt abgelegt.

Aufruf: python3 sarif-summary.py [verzeichnis_mit_sarif]
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

# GitHub-Workflow-Befehle erzeugen Annotationen im Lauf und in Pull Requests.
LEVEL_STUFE = {"error": 3, "warning": 2, "note": 1}
LEVEL_DE = {"error": "Fehler", "warning": "Warnung", "note": "Hinweis"}
MAX_ANNOTATIONEN = 20


def schweregrad(regel: dict, level: str) -> tuple[float, str]:
    """Liefert (sortierwert, anzeigetext) für einen Befund."""
    sicherheitswert = None
    eigenschaften = regel.get("properties") or {}
    roh = eigenschaften.get("security-severity")
    try:
        sicherheitswert = float(roh)
    except (TypeError, ValueError):
        sicherheitswert = None

    stufe = LEVEL_STUFE.get(level, 0)
    # Fehler vor Warnungen vor Hinweisen, innerhalb einer Stufe nach
    # security-severity absteigend.
    sortierwert = stufe * 100 + (sicherheitswert if sicherheitswert is not None else 0)
    if sicherheitswert is not None:
        anzeige = f"{LEVEL_DE.get(level, level)} (Severity {sicherheitswert})"
    else:
        anzeige = LEVEL_DE.get(level, level)
    return sortierwert, anzeige


def sammle_befunde(verzeichnis: Path) -> list[dict]:
    """Liest alle *.sarif im Verzeichnis und liefert normalisierte Befunde."""
    befunde: list[dict] = []
    if not verzeichnis.is_dir():
        return befunde

    for sarif_pfad in sorted(verzeichnis.rglob("*.sarif")):
        try:
            daten = json.loads(sarif_pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError) as fehler:
            print(f"Achtung: SARIF nicht lesbar ({sarif_pfad}): {fehler}")
            continue

        for lauf in daten.get("runs", []):
            regeln = (lauf.get("tool", {}).get("driver", {}) or {}).get("rules", []) or []
            regel_nach_index = {index: regel for index, regel in enumerate(regeln)}
            for ergebnis in lauf.get("results", []):
                regel_id = ergebnis.get("ruleId", "unbekannt")
                regel = regel_nach_index.get(ergebnis.get("ruleIndex"), {})
                level = ergebnis.get("level", "warning")
                _, anzeige = schweregrad(regel, level)
                meldung = (ergebnis.get("message", {}) or {}).get("text", "").strip()
                fundorte: list[str] = []
                for ort in ergebnis.get("locations", []):
                    physisch = (ort.get("physicalLocation", {}) or {})
                    uri = ((physisch.get("artifactLocation", {}) or {}).get("uri", ""))
                    zeile = ((physisch.get("region", {}) or {}).get("startLine"))
                    if zeile is not None:
                        fundorte.append(f"{uri}:{zeile}")
                    elif uri:
                        fundorte.append(uri)
                befunde.append(
                    {
                        "regel": regel_id,
                        "level": level,
                        "anzeige": anzeige,
                        "meldung": meldung,
                        "fundorte": fundorte,
                    }
                )
    return befunde


def ausgabe_markdown(befunde: list[dict]) -> str:
    zeilen: list[str] = []
    zeilen.append("## CodeQL JavaScript (Inline-Skripte)")
    zeilen.append("")
    if not befunde:
        zeilen.append("Keine Befunde gefunden. :white_check_mark:")
        zeilen.append("")
        zeilen.append(
            "Die vollständige SARIF-Datei liegt als Workflow-Artefakt "
            "`codeql-javascript-sarif` bei."
        )
        return "\n".join(zeilen)

    zaehler = Counter((b["regel"], b["anzeige"]) for b in befunde)
    zeilen.append(f"**{len(befunde)} Befund(e)** in {len(zaehler)} Regel(n).")
    zeilen.append("")
    zeilen.append("| Schweregrad | Regel | Anzahl |")
    zeilen.append("| --- | --- | --- |")
    for (regel, anzeige), anzahl in zaehler.most_common():
        zeilen.append(f"| {anzeige} | `{regel}` | {anzahl} |")
    zeilen.append("")

    zeilen.append("<details>")
    zeilen.append("<summary>Befunde im Einzelnen</summary>")
    zeilen.append("")
    for befund in befunde[:50]:
        fundort = befund["fundorte"][0] if befund["fundorte"] else "ohne Fundort"
        meldung = befund["meldung"] or "(keine Meldung)"
        zeilen.append(
            f"- **{befund['regel']}** ({befund['anzeige']}) – {meldung} "
            f"`{fundort}`"
        )
    if len(befunde) > 50:
        zeilen.append(f"- … und {len(befunde) - 50} weitere (siehe SARIF-Artefakt).")
    zeilen.append("</details>")
    zeilen.append("")
    zeilen.append(
        "Diese Befunde stammen aus den Inline-Skripten von "
        "`Docker/static/index.html` und `StandAlone/ho-planer.html`. "
        "Die vollständige SARIF-Datei liegt als Workflow-Artefakt "
        "`codeql-javascript-sarif` bei."
    )
    return "\n".join(zeilen)


def schreibe_annotationen(befunde: list[dict]) -> None:
    """Gibt Befunde als Workflow-Annotationen aus (ohne CI zu brechen)."""
    for befund in befunde[:MAX_ANNOTATIONEN]:
        stichwort = "error" if befund["level"] == "error" else "warning"
        fundort = befund["fundorte"][0] if befund["fundorte"] else "ohne Fundort"
        meldung = (befund["meldung"] or "Befund").replace("\n", " ").replace("%", "%25")
        meldung = meldung.replace("\r", "%0D")
        print(f"::{stichwort} title=CodeQL::{befund['regel']} ({fundort}): {meldung}")
    ueberzaehlig = len(befunde) - MAX_ANNOTATIONEN
    if ueberzaehlig > 0:
        print(f"::notice title=CodeQL::{ueberzaehlig} weitere Befunde - siehe Lauf-Zusammenfassung und SARIF-Artefakt.")


def main() -> int:
    verzeichnis = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../results")
    befunde = sammle_befunde(verzeichnis)

    markdown = ausgabe_markdown(befunde)
    print(markdown)
    schreibe_annotationen(befunde)

    zusammenfassung = os.environ.get("GITHUB_STEP_SUMMARY")
    if zusammenfassung:
        with open(zusammenfassung, "a", encoding="utf-8") as ziel:
            ziel.write(markdown + "\n\n")
    else:
        print("\n(Hinweis: keine Lauf-Zusammenfassung, da $GITHUB_STEP_SUMMARY fehlt.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
