# Testanleitung

Diese Anleitung beschreibt die technische Prüfung beider Laufzeitvarianten. Sie ändert keine fachlichen Regeln; deren verbindliche Definition steht in den [gemeinsamen Verträgen](../README.md#gemeinsame-verträge).

## Voraussetzungen

- Python passend zur jeweiligen Variante sowie `pip`
- Für Browser-Tests: Playwright und Chromium
- Freie Ports `5000` (Docker/Flask) und `8000` (Standalone-Testserver)
- Für die Standalone-GUI-Tests gegebenenfalls Internetzugriff: Vue, Vuetify, PDF.js, Chart.js und weitere Ressourcen werden per CDN geladen.

> **Hinweis:** `Docker/run_tests.py` setzt `HO_PLANER_DATA_DIR` auf ein temporäres Verzeichnis. Flask-Testserver und Pytest verwenden damit dieselbe isolierte SQLite-Datenbank; das Verzeichnis wird nach dem Lauf gelöscht. Direkte manuelle Pytest-Läufe ohne diese Umgebungsvariable können weiterhin die Standarddatenbank unter `Docker/data/` verwenden.

## Schnelle Prüfung vor einem Commit

Im Repository-Stamm ausführen:

```bash
git diff --check
git status
git diff --stat
```

Bei Änderungen an gemeinsamen Verträgen oder Referenzfällen müssen beide Varianten getestet werden, da `shared/**` beide CI-Testworkflows auslöst.

## Automatisierte Tests der Docker-Variante

Aus dem Verzeichnis `Docker/`:

```bash
python -m pip install -r requirements.txt
playwright install chromium --with-deps
python run_tests.py
```

`run_tests.py` startet die Flask-Anwendung selbst auf Port `5000`, wartet auf ihre Erreichbarkeit und führt anschließend `python -m pytest tests` aus. Vorher darf keine eigene Anwendung auf Port `5000` laufen.

Die Testbereiche umfassen unter anderem Zeitnormalisierung, Pausen, Nachtschichten, Split-Buchungen, Feiertage, Teilzeitmodelle, GLZ-Anker, JSON-Import/-Export, API und Playwright-GUI.

## Automatisierte Tests der Standalone-Variante

Aus dem Verzeichnis `StandAlone/`:

```bash
python -m pip install pytest pytest-playwright
playwright install chromium --with-deps
python run_tests.py
```

`run_tests.py` startet selbst `python -m http.server 8000` und führt dann `python -m pytest test_standalone.py` aus. Port `8000` muss frei sein. Die Testfixture leert vor jedem Test den Browser-`localStorage`.

Für einen einzelnen direkten Test muss der Webserver getrennt laufen:

```bash
python -m http.server 8000
python -m pytest test_standalone.py
```

Die Tests prüfen unter anderem Pausen, Feiertage, JSON-Import, unvollständige Einträge, GLZ-Anker, Zeitnormalisierung, Split-Buchungen, Einstellungen, Ansichten und PDF-Importdialog.

## Gemeinsame Referenzfälle und Fachregeln

Die fachliche Gleichheit wird durch versionierte Verträge und Referenzfälle abgesichert:

- [`shared/contracts/business-rules.md`](../shared/contracts/business-rules.md)
- [`shared/contracts/data-model.md`](../shared/contracts/data-model.md)
- [`shared/contracts/json-export.schema.json`](../shared/contracts/json-export.schema.json)
- [`shared/test-cases/`](../shared/test-cases/)

Besonders vor einem Release müssen die Referenzfälle für Pausen, Hessen-Feiertage, unvollständige Einträge, GLZ und JSON-Import in beiden Varianten erfolgreich sein.

## PDF-Testdaten und übersprungene Tests

Private PDF-Testdateien und lokale Erwartungen werden nicht versioniert; der Repository-Stamm ignoriert `pdf/` und `Docker/tests/testfiles/`. Die Dateien dürfen weder in Commits noch in Release-Artefakte gelangen.

Die vorhandenen automatisierten PDF-Fälle überspringen sich, wenn private Dateien fehlen:

- Docker: `Docker/tests/testfiles/standard.pdf`, `complex.pdf`, `error.pdf`
- Standalone: `StandAlone/testfiles/standard.pdf`, `error.pdf`

Für die sieben lokalen Zeitnachweise den Ordner `pdf/` ausschließlich als Lesebasis verwenden. Die Prüfung erfolgt ohne Datenbankimport über `parse_pdf_content(..., include_report=True)`. Pro Datei mindestens kontrollieren:

- erkannten Monat und Seitenzahl;
- Anzahl importierbarer Blöcke;
- Split-Buchungen, fehlende Buchungen und GLZ-Anker;
- Parserwarnungen für unbekannte Status, ungerade Zeitfolgen und fehlenden GLZ-Kontext.

Personenbezogene Ergebnisse nicht in Testlogs, Commits oder Ticketkommentare kopieren. Falls stabile Regressionserwartungen benötigt werden, ein lokales, ebenfalls ignoriertes Manifest neben den PDFs verwenden. Ein übersprungener PDF-Test ist kein erfolgreicher Parsernachweis.

## Manuelle Smoke-Tests der Docker-Variante

Die Anwendung unter `http://localhost:5000` prüfen:

1. Startseite laden; `/beta` muss auf `/` weiterleiten.
2. Einstellungen speichern, einschließlich optional aktivierter Samstage und Sonntage.
3. Eintrag anlegen, bearbeiten und löschen.
4. Split-Buchung mit mehreren Blöcken an einem Tag anlegen.
5. Pausengrenzen mit Tagesbruttozeiten `6:00`, `6:01`, `6:30`, `6:31`, `9:30`, `9:31`, `9:45` und `9:46` prüfen.
6. Nachtschicht prüfen, beispielsweise `22:00–02:00`.
7. Gesetzlichen Feiertag und eigenen Sondertag am selben Datum prüfen; der gesetzliche Feiertag hat Vorrang.
8. JSON exportieren, additiv importieren und den identischen Import wiederholen; Duplikate müssen übersprungen werden.
9. Überschreibimport ausführen und das zuvor erzeugte SQLite-Backup prüfen.
10. Container neu starten und Persistenz von Datenbank und Backups im Volume prüfen.

## JSON-Austausch zwischen Docker und Standalone

Vor Releases mit Änderungen an Export, Import, Datenmodell oder Fachregeln beide Richtungen prüfen:

1. In Docker exportieren und in Standalone importieren.
2. In Standalone exportieren und in Docker importieren.

Verwende dabei Einstellungen, Sondertage, Split-Buchungen, unvollständige Einträge, eine Nachtschicht sowie GLZ-Anker mit den Quellen `manual` und `pdf`.

Das portable Austauschformat lautet `ho-planer-export` in Version `1`. Der Standardimport ist additiv und darf Einstellungen nicht still überschreiben. Abweichende GLZ-Anker und Sondertage müssen als Konflikt erkennbar bleiben. Der Docker-Überschreibimport erstellt vorher ein SQLite-Backup.

## Migrationsabnahme mit Bestandsdaten

Migrationen ausschließlich mit einer Kopie einer repräsentativen Bestandsdatenbank testen:

1. Kopie einer älteren SQLite-Datei erstellen.
2. Sie als `database.db` in einen separaten Test-Volume-Ordner legen.
3. Die neue Container-Version mit diesem Volume starten.
4. Prüfen, dass der Container startet, vorhandene Daten erhalten bleiben und Split-Buchungen möglich sind.
5. Bei Strukturänderungen prüfen, dass `data/backups/` ein Migrationsbackup enthält und `schema_migrations` die ausgeführte Version enthält.
6. GLZ-Werte und deren Quellen prüfen.
7. Optional einen kontrollierten Fehlerpfad mit einer inkompatiblen Kopie testen; das Migrationsbackup muss erhalten bleiben.

Details zu Datenbank, Backup und Wiederherstellung enthält die [Docker-Migrationsdokumentation](../Docker/docs/migrations-and-backups.md).

## Tests vor einem Release

Vor einem Release mindestens ausführen beziehungsweise abnehmen:

- automatisierte Tests beider Varianten;
- vollständige PDF-Tests mit den privaten Testdateien;
- manuellen Docker-Smoke-Test;
- JSON-Roundtrip in beide Richtungen;
- bei Datenbankschemaänderungen eine Migrationsabnahme mit Bestandsdaten;
- Prüfung von Backup und Restore für das Docker-Volume.

Die Standalone-Release-Artefakte zusätzlich lokal öffnen: HTML-Datei starten, Daten exportieren und wieder importieren.

## CI und Veröffentlichungen

Docker-Tests laufen bei Pushes und Merge Requests gegen `main`, wenn `Docker/**`, `shared/**` oder der Docker-Workflow geändert wurden. Nach erfolgreichen Docker-Tests veröffentlicht nur ein Push auf `main` das Image `derplm/ho-tracker:latest`; erforderlich sind `DOCKER_USERNAME` und `DOCKER_PASSWORD`.

Standalone-Tests laufen bei Pushes und Merge Requests gegen `main`, wenn `StandAlone/**`, `shared/**` oder der Standalone-Testworkflow geändert wurden. Ein Push eines Tags nach Muster `v*` erzeugt das Standalone-Release mit HTML, ZIP und `SHA256SUMS.txt`.

Beide CI-Testworkflows installieren Playwright Chromium.

## Troubleshooting

- **Port belegt:** Prozess auf Port `5000` beziehungsweise `8000` beenden und den jeweiligen Teststarter erneut ausführen.
- **Chromium fehlt:** `playwright install chromium --with-deps` ausführen.
- **Standalone-GUI lädt nicht:** CDN-Erreichbarkeit und Browserkonsole prüfen.
- **PDF-Test übersprungen:** private Test-PDF am erwarteten Pfad bereitstellen.
- **Docker-Testdaten verändert:** Den Teststarter verwenden. Bei einem direkten manuellen Testlauf ohne `HO_PLANER_DATA_DIR` die Datenbank aus einem Backup im persistenten Volume wiederherstellen; vorher den aktuellen Stand sichern.
- **Migration fehlgeschlagen:** Container stoppen, Migrationsbackup im Volume prüfen und nach der [Wiederherstellungsanleitung](../Docker/docs/migrations-and-backups.md) vorgehen.
