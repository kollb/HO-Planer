# TODO – HO-Planer

Diese Liste enthält ausschließlich noch offene Arbeiten. Ein Punkt wird erst nach Umsetzung und erfolgreicher Prüfung abgehakt.

## Fachliche Parität und gemeinsame Verträge

- [ ] `shared/contracts/data-model.md` um `christmas_eve_and_new_years_eve_off` ergänzen (Boolean, Standard `true`).
- [ ] `shared/contracts/json-export.schema.json` um `settings.christmas_eve_and_new_years_eve_off` ergänzen, ohne das Feld für alte Exporte verpflichtend zu machen.
- [ ] `shared/contracts/business-rules.md` um die konfigurierbare Behandlung von Heiligabend und Silvester ergänzen.
- [ ] Im Fachvertrag festhalten: Ohne GLZ-Anker beginnt die Berechnung beim ersten gespeicherten Eintrag des Zieljahres.
- [ ] Im Fachvertrag festhalten: Serienplanung erzeugt Einträge nur an echten Arbeitstagen gemäß zentraler Tageslogik.
- [ ] Im Fachvertrag den strikten, partiellen JSON-Import inklusive neutraler Detailcodes beschreiben.
- [ ] Im Fachvertrag die PDF-Blockidentität `date + type + start + end` sowie Kommentar- und GLZ-Konfliktregeln beschreiben.
- [ ] `shared/test-cases/holidays.json` um Jahresendfälle mit aktivierter und deaktivierter Jahresendoption erweitern.
- [ ] Shared-GLZ-Testfall ohne Anchor ergänzen: Berechnung ab erstem Eintrag des Zieljahres.
- [ ] Shared-JSON-Importfälle für ungültige Einzelobjekte und erwartete Detailcodes ergänzen.
- [ ] Gemeinsame Referenzfälle für Serienplanung an aktiven Wochenenden, Feiertagen und Sondertagen ergänzen.
- [ ] Gemeinsame Referenzfälle für PDF-Merge, Kommentarergänzung und GLZ-Override-Konflikte ergänzen, sofern in beiden Testarchitekturen nutzbar.

## Docker: Einstellungen, Feiertage und Migration

- [ ] In `Docker/models.py` das Settings-Feld `christmas_eve_and_new_years_eve_off` mit Default `true` ergänzen.
- [ ] In `Docker/migrate.py` Migration V4 für `settings.christmas_eve_and_new_years_eve_off` implementieren.
- [ ] Sicherstellen, dass Migration V4 auch läuft, wenn `work_entry` nicht existiert.
- [ ] Bestehende SQLite-Settings bei Migration V4 rückwärtskompatibel auf `true` setzen.
- [ ] Vor jeder tatsächlichen Schemaänderung genau ein SQLite-Backup erzeugen.
- [ ] Migration V4 in `schema_migrations` erfassen.
- [ ] Zentralen Docker-Helper für Hessen-Feiertage und die optionale Jahresendregel einführen.
- [ ] Alle Docker-Aufrufer auf den zentralen Feiertagshelper umstellen.
- [ ] Veraltete Verwendung von `state='HE'` auf `subdiv='HE'` vereinheitlichen.
- [ ] `GET /api/settings` um die Jahresendoption erweitern.
- [ ] `POST /api/settings` um die Jahresendoption erweitern.
- [ ] Robuste Bool-Normalisierung für Settings-Requests einführen; insbesondere darf `"false"` nicht als `true` interpretiert werden.
- [ ] Alte Settings-Clients ohne Feld kompatibel mit Default `true` behandeln.

## Docker: Serienplanung

- [ ] `plan_series()` auf ungültige Request-Bodies prüfen.
- [ ] Serienplanung mit Ende vor Start mit HTTP 400 ablehnen.
- [ ] `weekdays` ausschließlich als Liste eindeutiger echter Integer `0..6` akzeptieren.
- [ ] Python-Boolean-Werte in `weekdays` explizit ablehnen.
- [ ] Feiertagsmap für den Serienzeitraum nur einmal erzeugen.
- [ ] Serienplanung ausschließlich über `get_day_info()` entscheiden lassen, ob ein Datum ein Arbeitstag ist.
- [ ] Gesetzliche Feiertage, freie Sondertage und inaktive Wochentage bei Serienplanung überspringen.
- [ ] Aktive Wochenendtage und Sondertage mit positiver Sollzeit bei Serienplanung zulassen.
- [ ] Bestehende Overwrite-Semantik in der Serienplanung beibehalten.
- [ ] Zukunfts-`home` weiterhin als `planned` anlegen.

## Docker: JSON-Import

- [ ] `is_valid_date()` auf echte ISO-Kalenderdaten härten.
- [ ] Separate strikte Austauschzeitvalidierung einführen: ausschließlich `""` oder `HH:MM`.
- [ ] UI-tolerante Zeitnormalisierung für normale Formulare beibehalten.
- [ ] `normalized_import_entry()` auf strukturierte Fehlercodes umstellen.
- [ ] Nicht-endliche Zahlen (`NaN`, `Infinity`, `-Infinity`) beim Austauschimport ablehnen.
- [ ] `glz_override_source` nur für `manual`, `pdf` oder `null` akzeptieren.
- [ ] Ungültige GLZ-Overridequellen nicht stillschweigend in `null` umwandeln.
- [ ] Negative Sonderstunden beim Import ablehnen.
- [ ] Fehlende oder nicht-listige `entries` als ungültigen Container ablehnen.
- [ ] Fehlende oder nicht-listige `custom_holidays` als ungültigen Container ablehnen.
- [ ] Falsches Format, falsche Version und ungültiges JSON als ungültigen Container ablehnen.
- [ ] Bei gültigem Container valide Einzelobjekte importieren und ungültige einzeln überspringen.
- [ ] Neutrale Importdetails wie `entries[2]: invalid_date` zurückgeben.
- [ ] Standardimport additiv halten und keine Settings importieren.

## Docker: PDF-Import

- [ ] Falsche PDF-Parser-Markierung für Nachtschichten mit Ende vor Start entfernen.
- [ ] PDF-Nachtschichten wie `22:00–02:00` als gültig behandeln.
- [ ] Testbare Docker-Hilfslogik zum Mergen bestehender und importierter PDF-Blöcke erstellen.
- [ ] PDF-Blockidentität als `date + type + start + end` implementieren.
- [ ] Im additiven PDF-Import neue Blöcke ergänzen statt ganze Tage zu überspringen.
- [ ] Identische PDF-Blöcke nicht erneut speichern.
- [ ] Leeren vorhandenen Kommentar mit nichtleerem PDF-Kommentar ergänzen.
- [ ] Bei verschiedenen nichtleeren Kommentaren vorhandenen Kommentar behalten und `comment_hints` erhöhen.
- [ ] Abweichende bestehende GLZ-Anker nicht überschreiben.
- [ ] Bei GLZ-Konflikt Zeitblock trotzdem ohne kollidierenden Override speichern.
- [ ] `glz_override_conflicts` im PDF-Importresultat ausgeben.
- [ ] `imported_entries`, `skipped_duplicates`, `glz_override_conflicts` und `comment_hints` im PDF-Importresultat ausgeben.
- [ ] Overwrite-Modus: bestehende Tagesblöcke löschen und PDF-Blöcke normal einfügen.

## Standalone: Einstellungen und Tageslogik

- [ ] `Store.getSettings()` um `christmas_eve_and_new_years_eve_off: true` ergänzen.
- [ ] Vue-Settings-Objekt um die Jahresendoption ergänzen.
- [ ] Einstellungsdialog um einen Switch für Heiligabend und Silvester als arbeitsfreie Tage ergänzen.
- [ ] `getHolidayName()` so erweitern, dass Heiligabend und Silvester optional berücksichtigt werden.
- [ ] In `getDayInfo()` bei fehlendem Altbestand die Jahresendoption standardmäßig als aktiv behandeln.
- [ ] Gesetzliche Feiertage weiterhin mit Vorrang vor Sondertagen behandeln.
- [ ] Lokale Datumshilfen `toLocalIsoDate()` und `fromLocalIsoDate()` ergänzen.
- [ ] UTC-anfällige Datumsmuster mindestens in Tageslogik, GLZ, automatischer Umwandlung, Monats-/Jahresdaten, Serienplanung, PDF-Import und Sondertagslogik ersetzen.

## Standalone: GLZ und Serienplanung

- [ ] `getGlzCarryover()` ohne Anchor ab dem ersten gespeicherten Eintrag des Zieljahres berechnen.
- [ ] Bei fehlendem passenden Eintrag bis zum Zielmonat GLZ-Saldo `0.0` liefern.
- [ ] Deterministisches Verhalten bei mehreren Anchors am selben Tag sicherstellen.
- [ ] Serienplanungs-UI von Montag–Freitag auf Montag–Sonntag erweitern.
- [ ] `saveSeriesPlan()` ausschließlich über `getDayInfo()` echte Arbeitstage auswählen lassen.
- [ ] Freie Sondertage, gesetzliche Feiertage und inaktive Wochentage überspringen.
- [ ] Aktive Wochenenden und Sondertage mit positiver Sollzeit zulassen.

## Standalone: JSON- und PDF-Import

- [ ] Echte Kalenderdatumsprüfung für den Austauschimport ergänzen.
- [ ] Strikte Austauschzeitvalidierung ergänzen: ausschließlich `""` oder exaktes `HH:MM`.
- [ ] Endliche Zahlen mit `Number.isFinite()` erzwingen.
- [ ] Nur `manual`, `pdf` oder `null` als `glz_override_source` akzeptieren.
- [ ] Negative Sonderstunden ablehnen.
- [ ] `mergePortableExport()` auf partielle Einzelobjektvalidierung mit Detailcodes umstellen.
- [ ] `portableExportToStore()` dieselben Validatoren beziehungsweise bereits normalisierte Daten verwenden lassen.
- [ ] Testbare reine Hilfsfunktion `mergePdfEntries(existingEntries, pdfEntries)` oder gleichwertig einführen.
- [ ] Additiven Standalone-PDF-Import blockweise statt tageweise implementieren.
- [ ] PDF-Duplikate per `type + start + end` erkennen.
- [ ] PDF-Kommentar- und GLZ-Konfliktregeln wie in Docker implementieren.
- [ ] Nur bei realen Änderungen Browserdaten speichern.
- [ ] PDF-Blöcke nach Startzeit sortieren, ohne Nachtschichten fachlich falsch zu behandeln.
- [ ] Nutzerfeedback um fachliche PDF-Importzähler erweitern.

## Tests

- [ ] Docker-`MockSettings` um die Jahresendoption erweitern.
- [ ] Docker-Shared-Holiday-Adapter bei fehlendem Flag auf `true` setzen.
- [ ] Docker-API-Test für Settings-Default und Speichern der Jahresendoption ergänzen.
- [ ] Docker-Tests für strikten partiellen JSON-Import ergänzen.
- [ ] Docker-Tests für echte ungültige Kalenderdaten, ungültige Austauschzeiten und nicht-endliche Zahlen ergänzen.
- [ ] Docker-Tests für negative Sonderstunden und ungültige GLZ-Quellen ergänzen.
- [ ] Docker-Tests für valide Nachbarobjekte bei ungültigen Einzelobjekten und Detailcodes ergänzen.
- [ ] Docker-Tests für ungültige JSON-Container ergänzen.
- [ ] Docker-Tests für Serienplanung an aktivem Wochenende sowie für Feiertage und freie Sondertage ergänzen.
- [ ] Docker-PDF-Parser-Test mit Fake-PDF für `22:00–02:00` ergänzen.
- [ ] Docker-PDF-Merge-Tests mit `monkeypatch(parse_pdf_content)` ergänzen.
- [ ] Standalone-Tests für Jahresendfälle aus den Shared-Cases ergänzen.
- [ ] Standalone-Tests für strikten partiellen JSON-Import und Detailcodes ergänzen.
- [ ] Standalone-Test für GLZ ohne Anchor ab erstem Eintrag des Zieljahres ergänzen.
- [ ] Standalone-Test für Serienplanung mit aktivem Wochenende ergänzen.
- [ ] Standalone-Test für die PDF-Merge-Hilfsfunktion ergänzen.
- [ ] Neue PDF-Tests ausschließlich mit Fakes, Mocks und `monkeypatch` umsetzen.
- [ ] Docker-Tests ausschließlich mit `cd Docker` und `python run_tests.py` ausführen.
- [ ] Standalone-Tests ausschließlich mit `cd StandAlone` und `python run_tests.py` ausführen.

## Dokumentation und Betrieb

- [ ] Root-README um klare Architekturübersicht beider Varianten ergänzen.
- [ ] Docker-README um die Jahresendoption, JSON-Importregeln und PDF-Merge-Verhalten ergänzen.
- [ ] Standalone-README um die Jahresendoption, Browser-Backup/Restore und JSON-Validierung ergänzen.
- [ ] Dokumentation zu Datenmodell und Austauschformat aktualisieren.
- [ ] Migrationsdokumentation um Version V4 und das Backup-Verhalten ergänzen.
- [ ] Backup- und Restore-Anleitung für SQLite-Volume und externe Sicherungen vervollständigen.
- [ ] Dokumentation zum Risiko lokaler Browser-Speicherung und zu regelmäßigen JSON-Backups ergänzen.
- [ ] Release-Prozess für Änderungen am gemeinsamen Vertrag und an Shared-Testfällen dokumentieren.

## Abschlussprüfungen nach Umsetzung

- [ ] `git status --short` separat ausführen und prüfen.
- [ ] `git diff --check` separat ausführen und prüfen.
- [ ] `git diff --stat` separat ausführen und prüfen.
- [ ] Abschlussbericht mit geänderten Dateien, Testresultaten, Migration, Rückwärtskompatibilität und ausgelassenen privaten Testdateien erstellen.
