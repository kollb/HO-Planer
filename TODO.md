# TODO – HO-Planer

Diese Liste enthält ausschließlich noch offene Arbeiten. Ein Punkt wird erst nach Umsetzung und erfolgreicher Prüfung abgehakt.

## Priorität P0 – bestätigte Testblocker und Datenintegrität

- [X] **Standalone-Teststarter unter Windows reparieren:** Der aktuelle Lauf mit `py StandAlone/run_tests.py` bricht vor dem Serverstart mit `UnicodeEncodeError` an Emoji-Konsolenausgaben ab. Ausgabe ASCII-/codepage-sicher machen und danach die vollständige Suite ausführen.
- [X] **Standalone-Testumgebung reproduzierbar machen:** Im aktuell verwendeten `py`-Interpreter fehlt zudem `pytest`; Teststarter müssen fehlende Testpakete und Browser-Binaries eindeutig vor dem Start melden.
- [X] **Fachliche Fehler zuerst absichern:** echte Kalenderdaten validieren, Austauschzeiten strikt validieren und nicht-endliche Zahlen, negative Sonderstunden sowie ungültige GLZ-Quellen beim JSON-Import ablehnen – in Docker und Standalone identisch.
- [X] **Datenverlust beim PDF-Import verhindern:** Nachtschichten akzeptieren und PDF-Import blockweise/additiv mergen, statt durch Tageslogik gültige Daten zu verwerfen oder bestehende Einträge zu überschreiben.
- [X] **Parität herstellen:** Jahresendoption, Feiertagshelper, Serienplanung und GLZ-Ankerverhalten in beiden Varianten über gemeinsame Referenzfälle absichern.

## [ ] GUI-Modernisierung und Bedienkomfort

> Ausgenommen auf Wunsch: separate Accessibility-Maßnahmen sowie Druckansicht und PDF-Export. PDF- und JSON-Importvorschauen bleiben Bestandteil der Planung.

### [ ] Gemeinsames Material-3-Designsystem

- [X] Gemeinsame CSS-Design-Tokens für Light- und Dark-Mode definieren: Hintergrund, Oberflächen, Text, Primär-, Status-, Border-, Radius-, Schatten- und Abstandswerte.
- [X] Bestehende harte Farb-, Radius- und Schattenwerte in Docker- und Standalone-Oberfläche schrittweise auf die zentralen Tokens umstellen.
- [X] Theme-Umschalter mit persistierter Auswahl ergänzen; Docker speichert die Auswahl serverseitig in den Einstellungen, Standalone lokal.
- [X] Cards, Chips, Tabellen, Eingabefelder und Dialoge mit konsistenter Typografie, Abständen und Material-3-Oberflächen vereinheitlichen.

### [X] Navigation und responsive Bedienung

- [X] Responsive App-Bar mit Navigation Drawer für Ansichten und häufige Aktionen ergänzen.
- [X] Bestehende Navigation für Timeline, Kalender und Jahr im Drawer sowie in der mobilen Bottom-Navigation konsistent abbilden.
- [X] Mobile Bottom-Navigation auf Ansichtswechsel beschränken und Aktionsbefehle über ein Bottom-Sheet bereitstellen.
- [X] Bestehende Direktaktionen in der App-Bar nach Einführung des Drawers konsolidieren, ohne Import, Planung oder Einstellungen zu verlieren.

### [ ] Monats-, Kalender- und Jahresansicht

- [X] Monatstabelle mit klaren Zustandsfarben für Homeoffice, Büro, Urlaub, Krankheit, Dienstreise, Feiertage und geplante Einträge vereinheitlichen.
- [X] Sticky Tabellenkopf und kompakte Tageszusammenfassung für Sollzeit, Istzeit, GLZ-Delta, Status und Splits ergänzen.
- [X] Arbeitszeitwarnungen in Listen- und Kalenderansicht einheitlich darstellen.
- [X] Mobilansicht der Monatstabelle als Tageskarten mit großen Bearbeitungsaktionen umsetzen.
- [X] Kalenderzellen um Feiertagsnamen, Planungsstatus, Stunden- und Split-Zusammenfassung erweitern.
- [X] Jahresansicht um Feiertagsvorschau, verplante/offene Arbeitstage, Homeoffice-Quote und klickbare Monatsnavigation erweitern.

### [ ] Dashboard und Schnellaktionen

- [X] Dashboard-Karten für Arbeitstage, Soll-/Istzeit, GLZ-Saldo, Homeoffice-Quote und Restbudget vereinheitlichen.
- [X] Übersichtliche Diagramme für monatliche Homeoffice-Nutzung und Jahresverlauf ergänzen, ohne bestehende Kennzahlen zu verändern.
- [X] Budgetüberschreitung in Dashboard und Planungsdialog sichtbar, aber nicht blockierend anzeigen.
- [X] Floating Action Button mit „Tag erfassen“, „Serienplanung“, „PDF importieren“, „JSON importieren“ und „Einstellungen“ ergänzen.
- [X] Schnelleingabe für den heutigen Tag implementieren; bei Monatswechsel zuerst die aktuelle Monatsansicht laden.

### [ ] Dialoge, Validierung und Vorlagen

- [X] Tagesbearbeitungsdialog in klar gegliederte Eingabeabschnitte für Status, Zeiten, Notiz und GLZ-Abgleich aufteilen.
- [X] Clientseitige Inline-Validierung für Datum, Zeitformat, endliche Zahlen und Serienzeiträume ergänzen; Docker-Servervalidierung bleibt maßgeblich.
- [ ] Plausibilitätsinformation für Arbeitszeit über sechs Stunden und rechnerische Pausenregel ergänzen, ohne ein neues Pausen-Datenmodell einzuführen.
- [ ] Wochenvorlagen „Standardwoche“, „Bürowoche“, „Homeoffice-Woche“ und „Urlaubswoche“ als bestätigungspflichtige Vorbelegung der bestehenden Serienplanung umsetzen.
- [ ] Wochenvorlagen an aktive Wochentage, Feiertage, Sondertage und die bestehende Zukunftslogik für geplantes Homeoffice anbinden.

### [ ] Tagesdaten kopieren und verschieben

- [X] Im Tagesdialog eine Kopier-/Verschiebeaktion mit auswählbarem Zieldatum ergänzen.
- [X] Vor Kopieren/Verschieben Zielkonflikte ermitteln und klar zwischen Abbruch, Zusammenführen und explizitem Überschreiben wählen lassen.
- [X] Docker: atomaren API-Endpunkt für Kopieren/Verschieben inklusive Validierung und Konfliktantwort implementieren.
- [X] Standalone: atomare Store-Operation mit einem Persistiervorgang implementieren.
- [X] Beim Verschieben Quelldaten erst nach erfolgreicher Zielübernahme entfernen.
- [X] Tests für leeres Ziel, Konflikte, Kopieren, Verschieben und Fehlerfälle ergänzen.

### [ ] Importvorschau und Konfliktauflösung

- [ ] PDF-Import in Parser-/Vorschau-/Übernahme-Schritte aufteilen, ohne die bestehende additive Merge-Logik zu verändern.
- [X] JSON-Import mit Vorschau für gültige Daten, übersprungene Objekte, Duplikate, Feiertags- und GLZ-Konflikte ergänzen.
- [ ] PDF-Vorschau mit erkannten Tagen, Blöcken, Duplikaten, Kommentarhinweisen, GLZ-Konflikten und potenziellen Überschreibungen ergänzen.
- [X] Übernahme erst nach expliziter Nutzerbestätigung durchführen und bei der finalen Speicherung erneut validieren.
- [X] Docker: sichere Vorschau-/Übernahme-API entwerfen, ohne unverifizierte Browserdaten direkt zu persistieren.
- [X] Standalone: Vorschau aus bestehenden Parser- und Merge-Hilfen ableiten, persistieren erst nach Bestätigung.

### [ ] Bedienungssicherheit und Datenpflege

- [ ] Einheitliche Lade-, Leer- und Fehlerzustände mit Wiederholen-Aktion für API- und Speicherfehler in Docker und Standalone ergänzen.
- [ ] Vor Ansichts-, Monats- oder Dialogwechseln auf ungespeicherte Änderungen hinweisen und Speichern, Verwerfen oder Abbrechen anbieten.
- [ ] Kurzzeitige Rückgängig-Aktion für Löschen, Kopieren, Verschieben und Serienplanung über die bestehende Benachrichtigungsoberfläche umsetzen.
- [ ] Serienplanung vor dem Speichern als Vorschau darstellen: erzeugte, übersprungene, konfliktbehaftete und potenziell geänderte Tage auflisten.
- [ ] Nach Importen, Serienplanung sowie Kopier-/Verschiebevorgängen eine Änderungszusammenfassung mit erstellt, ergänzt, übersprungen und Konflikten anzeigen.
- [ ] Eigene Feiertage mit Jahresfilter, Bearbeiten, Löschen und Duplikatprüfung übersichtlich verwalten.
- [ ] Einstellungen in die Bereiche Arbeitszeit, Homeoffice, Feiertage, Darstellung und Datenverwaltung gliedern.
- [ ] Nicht veränderndes Datenintegritäts-Prüfwerkzeug für ungültige oder inkonsistente lokale beziehungsweise serverseitige Einträge bereitstellen.
- [ ] Monats- und Jahresdaten zwischenspeichern und nach Änderungen oder expliziter Aktualisierung gezielt invalidieren.
- [ ] Kompakte Versionshinweise für relevante Datenformat- und Funktionsänderungen nach Updates anzeigen.

### [ ] Qualitätssicherung

- [ ] Tests für Theme-Persistenz, Schnellaktionen, Wochenvorlagen, Inline-Validierungen, Kopieren/Verschieben, Importvorschau, Rückgängig-Aktionen und Datenintegritätsprüfung ergänzen.
- [ ] Beide Oberflächen auf Funktionsparität prüfen; Abweichungen zwischen API- und Standalone-Persistenz dokumentieren und absichern.
- [ ] Beide Teststarter nach Änderungen erneut ausführen und fachliche Testfehler getrennt von Infrastrukturfehlern auswerten.

## Fachliche Parität und gemeinsame Verträge

- [X] `shared/contracts/data-model.md` um `christmas_eve_and_new_years_eve_off` ergänzen (Boolean, Standard `true`).
- [X] `shared/contracts/json-export.schema.json` um `settings.christmas_eve_and_new_years_eve_off` ergänzen, ohne das Feld für alte Exporte verpflichtend zu machen.
- [X] `shared/contracts/business-rules.md` um die konfigurierbare Behandlung von Heiligabend und Silvester ergänzen.
- [X] Im Fachvertrag festhalten: Ohne GLZ-Anker beginnt die Berechnung beim ersten gespeicherten Eintrag des Zieljahres.
- [X] Im Fachvertrag festhalten: Serienplanung erzeugt Einträge nur an echten Arbeitstagen gemäß zentraler Tageslogik.
- [X] Im Fachvertrag den strikten, partiellen JSON-Import inklusive neutraler Detailcodes beschreiben.
- [X] Im Fachvertrag die PDF-Blockidentität `date + type + start + end` sowie Kommentar- und GLZ-Konfliktregeln beschreiben.
- [X] `shared/test-cases/holidays.json` um Jahresendfälle mit aktivierter und deaktivierter Jahresendoption erweitern.
- [X] Shared-GLZ-Testfall ohne Anchor ergänzen: Berechnung ab erstem Eintrag des Zieljahres.
- [X] Shared-JSON-Importfälle für ungültige Einzelobjekte und erwartete Detailcodes ergänzen.
- [X] Gemeinsame Referenzfälle für Serienplanung an aktiven Wochenenden, Feiertagen und Sondertagen ergänzen.
- [X] Gemeinsame Referenzfälle für PDF-Merge, Kommentarergänzung und GLZ-Override-Konflikte ergänzen, sofern in beiden Testarchitekturen nutzbar.
- [X] `shared/test-cases/holidays-calendar.json` als vollständigen Feiertagskalender 2020–2040 ergänzen; beide Varianten prüfen Datum und Namen gegen dieselbe Datei.
- [X] Feiertagsnamen der Docker-Bibliothek auf die Standalone-Schreibweise normalisieren, damit beide Oberflächen denselben Namen anzeigen.
- [X] Jahresendoption im Docker-Test über den Produktivhelper auswerten, statt Heiligabend und Silvester im Test selbst einzutragen.
- [X] Docker-Auswerter der Serienplanung auf die Standalone-Zusicherungen ziehen: Sollzeit, Startzeit, abgeleitete Endzeit und wirkungsfreie Vorschau.
- [X] `shared/test-cases/glz.json` um `evaluation_settings`, `carryover_target` und `expected_carryover` erweitern; beide Varianten rechnen jeden Fall auf denselben Saldo.
- [X] `shared/test-cases/pdf-night-shifts.json` für die Mitternachtsgrenze ergänzen und in beiden Varianten auswerten.

## Docker: Einstellungen, Feiertage und Migration

- [X] In `Docker/models.py` das Settings-Feld `christmas_eve_and_new_years_eve_off` mit Default `true` ergänzen.
- [X] In `Docker/migrate.py` Migration V4 für `settings.christmas_eve_and_new_years_eve_off` implementieren.
- [X] Sicherstellen, dass Migration V4 auch läuft, wenn `work_entry` nicht existiert.
- [X] Bestehende SQLite-Settings bei Migration V4 rückwärtskompatibel auf `true` setzen.
- [X] Vor jeder tatsächlichen Schemaänderung genau ein SQLite-Backup erzeugen.
- [X] Migration V4 in `schema_migrations` erfassen.
- [X] Zentralen Docker-Helper für Hessen-Feiertage und die optionale Jahresendregel einführen.
- [X] Alle Docker-Aufrufer auf den zentralen Feiertagshelper umstellen.
- [X] Veraltete Verwendung von `state='HE'` auf `subdiv='HE'` vereinheitlichen.
- [X] `GET /api/settings` um die Jahresendoption erweitern.
- [X] `POST /api/settings` um die Jahresendoption erweitern.
- [X] Robuste Bool-Normalisierung für Settings-Requests einführen; insbesondere darf `"false"` nicht als `true` interpretiert werden.
- [X] Numerische Docker-Settings (`weekly_hours`, `ho_quota_percent`) auf endliche, fachlich zulässige Werte prüfen und aktive Wochentage nicht leer speichern; ungültige Settings kontrolliert mit HTTP 400 ablehnen.
- [X] Alte Settings-Clients ohne Feld kompatibel mit Default `true` behandeln.

## Docker: GUI und Eingabeverarbeitung

- [X] Docker-Sondertage auf genau einen Datensatz pro Datum begrenzen: Beim Bearbeiten darf eine Verschiebung auf ein bereits belegtes Datum keine Duplikate erzeugen; Datenmodell, API und Migrations-/Bereinigungsstrategie auf die Standalone-Semantik eines Sondertags je Datum ausrichten.
- [X] Docker-Sondertagsdialog vor dem Speichern auf echte Kalenderdaten, nichtleere Namen sowie endliche, nichtnegative Stunden prüfen und Validierungsfehler sichtbar anzeigen; die API muss dieselben Werte mit HTTP 400 ablehnen.
- [X] Docker-Schreibvorgänge für Einträge, Einstellungen, Sondertage, Löschen und Serienplanung auf HTTP-Status und Netzwerkfehler prüfen: lokale Änderungen erst nach Erfolg übernehmen oder bei Fehler zurückrollen und eine sichtbare Fehlermeldung anzeigen.
- [X] **GLZ- und Notizänderungen in der Docker-Timeline zuverlässig speichern:** Zeitfelder übergeben den Eintrag inzwischen an `debouncedSave(item.date, entry)`, die Handler für GLZ-Override und Notiz jedoch weiterhin nicht. Dadurch erhält `saveSingleEntry()` nach dem Timeout keinen Eintrag und Änderungen können mit einem JavaScript-Fehler verloren gehen. Den Eintrag durchgängig übergeben und Fehler im UI sichtbar melden.
- [X] Beim automatischen Setzen von Start-/Endzeit in `onEntryChange()` das tatsächliche Tagesziel (`item.daily_target`) statt des allgemeinen Wochen-Tagesziels verwenden; Sondertage mit positiver, abweichender Sollzeit dürfen keine falschen Standard-Endzeiten erhalten.

## Docker: Serienplanung

- [X] Docker-Serienplanungsoberfläche von Montag–Freitag auf Montag–Sonntag erweitern, damit im Arbeitszeitmodell aktivierte Wochenendtage auch über die GUI geplant werden können.

- [X] Alle schreibenden Docker-API-Endpunkte auf objektförmige JSON-Request-Bodies prüfen (`/api/entry`, `/api/settings`, `/api/custom-holidays`, `/api/plan/series`), damit Listen, Strings und `null` kontrolliert mit HTTP 400 statt über `.get()` mit HTTP 500 behandelt werden.
- [X] `plan_series()` auf ungültige Request-Bodies prüfen.
- [X] Serienplanung mit Ende vor Start mit HTTP 400 ablehnen.
- [X] `weekdays` ausschließlich als Liste eindeutiger echter Integer `0..6` akzeptieren.
- [X] Python-Boolean-Werte in `weekdays` explizit ablehnen.
- [X] Feiertagsmap für den Serienzeitraum nur einmal erzeugen.
- [X] Serienplanung ausschließlich über `get_day_info()` entscheiden lassen, ob ein Datum ein Arbeitstag ist.
- [X] Gesetzliche Feiertage, freie Sondertage und inaktive Wochentage bei Serienplanung überspringen.
- [X] Aktive Wochenendtage und Sondertage mit positiver Sollzeit bei Serienplanung zulassen.
- [X] Bestehende Overwrite-Semantik in der Serienplanung beibehalten und per API-Test absichern.
- [X] Zukunfts-`home` weiterhin als `planned` anlegen und per API-Test absichern.

## Docker: JSON-Import

- [X] `is_valid_date()` auf echte ISO-Kalenderdaten härten und die Validierung für sämtliche API-Eingaben mit Datum anwenden, insbesondere `/api/entry` und `/api/custom-holidays`.
- [X] Separate strikte Austauschzeitvalidierung einführen: ausschließlich `""` oder `HH:MM`.
- [X] UI-tolerante Zeitnormalisierung für normale Formulare beibehalten, aber negative Stunden und Minuten in Docker und Standalone konsequent ablehnen.
- [X] Reguläre Docker-`POST /api/entry`-Anfragen mit explizit übermittelten, nach der Normalisierung ungültigen Zeiten mit HTTP 400 ablehnen, statt sie stillschweigend als leere Zeit zu speichern; absichtlich leere Zeitfelder bleiben zulässig.
- [X] `normalized_import_entry()` auf strukturierte Fehlercodes umstellen.
- [X] Nicht-endliche Zahlen (`NaN`, `Infinity`, `-Infinity`) beim Austauschimport ablehnen.
- [X] `glz_override_source` nur für `manual`, `pdf` oder `null` akzeptieren.
- [X] Ungültige GLZ-Overridequellen nicht stillschweigend in `null` umwandeln.
- [X] Negative Sonderstunden beim Import ablehnen.
- [X] Auch reguläre Docker-API-Eingaben für Sondertage und GLZ-Overrides auf endliche, fachlich erlaubte Zahlen prüfen; `NaN`, Unendlich, negative Sonderstunden und nichtnumerische Werte kontrolliert mit HTTP 400 ablehnen.
- [X] Fehlende oder nicht-listige `entries` als ungültigen Container ablehnen.
- [X] Fehlende oder nicht-listige `custom_holidays` als ungültigen Container ablehnen.
- [X] Falsches Format, falsche Version und ungültiges JSON als ungültigen Container ablehnen.
- [X] Bei gültigem Container valide Einzelobjekte importieren und ungültige einzeln überspringen.
- [X] Neutrale Importdetails wie `entries[2]: invalid_date` zurückgeben.
- [X] Standardimport additiv halten und keine Settings importieren; per API-Test abgesichert.

## Docker: PDF-Import

- [X] Falsche PDF-Parser-Markierung für Nachtschichten mit Ende vor Start entfernen.
- [X] PDF-Nachtschichten wie `22:00–02:00` als gültig behandeln.
- [X] Testbare Docker-Hilfslogik zum Mergen bestehender und importierter PDF-Blöcke erstellen.
- [X] PDF-Blockidentität als `date + type + start + end` implementieren.
- [X] Im additiven PDF-Import neue Blöcke ergänzen statt ganze Tage zu überspringen.
- [X] Identische PDF-Blöcke nicht erneut speichern.
- [X] Leeren vorhandenen Kommentar mit nichtleerem PDF-Kommentar ergänzen.
- [X] Bei verschiedenen nichtleeren Kommentaren vorhandenen Kommentar behalten und `comment_hints` erhöhen.
- [X] Abweichende bestehende GLZ-Anker nicht überschreiben.
- [X] Bei GLZ-Konflikt Zeitblock trotzdem ohne kollidierenden Override speichern.
- [X] `glz_override_conflicts` im PDF-Importresultat ausgeben.
- [X] `imported_entries`, `skipped_duplicates`, `glz_override_conflicts` und `comment_hints` im PDF-Importresultat ausgeben.
- [X] Overwrite-Modus: bestehende Tagesblöcke löschen und PDF-Blöcke normal einfügen.

## Standalone: Einstellungen und Tageslogik

- [X] Standalone-Sondertagsdialog vor dem Speichern auf echte Kalenderdaten, nichtleere Namen sowie endliche, nichtnegative Stunden prüfen und Validierungsfehler sichtbar anzeigen.
- [X] Standalone-`onEntryChange()` beim automatischen Setzen von Start-/Endzeit auf `day.daily_target` statt `calcDailyTarget` umstellen, damit Sondertage mit positiver abweichender Sollzeit korrekt vorbelegt werden.
- [X] `Store.getSettings()` um `christmas_eve_and_new_years_eve_off: true` ergänzen.
- [X] Vue-Settings-Objekt um die Jahresendoption ergänzen.
- [X] Standalone-Settings vor dem Speichern auf endliche, fachlich zulässige Wochenstunden, HO-Quote und mindestens einen aktiven Wochentag prüfen; ungültige Werte sichtbar zurückweisen.
- [X] Einstellungsdialog um einen Switch für Heiligabend und Silvester als arbeitsfreie Tage ergänzen.
- [X] `getHolidayName()` so erweitern, dass Heiligabend und Silvester optional berücksichtigt werden.
- [X] In `getDayInfo()` bei fehlendem Altbestand die Jahresendoption standardmäßig als aktiv behandeln.
- [X] Gesetzliche Feiertage weiterhin mit Vorrang vor Sondertagen behandeln.
- [X] Lokale Datumshilfen `toLocalIsoDate()` und `fromLocalIsoDate()` ergänzen.
- [X] UTC-anfällige Datumsmuster mindestens in Tageslogik, GLZ, automatischer Umwandlung, Monats-/Jahresdaten, Serienplanung, PDF-Import und Sondertagslogik ersetzen.

## Standalone: GLZ und Serienplanung

- [X] `getGlzCarryover()` ohne Anchor ab dem ersten gespeicherten Eintrag des Zieljahres berechnen.
- [X] Bei fehlendem passenden Eintrag bis zum Zielmonat GLZ-Saldo `0.0` liefern.
- [X] Deterministisches Verhalten bei mehreren Anchors am selben Tag sicherstellen: Der zuletzt gespeicherte Anchor gewinnt in beiden Varianten.
- [X] Serienplanungs-UI von Montag–Freitag auf Montag–Sonntag erweitern.
- [X] `saveSeriesPlan()` ausschließlich über `getDayInfo()` echte Arbeitstage auswählen lassen.
- [X] Freie Sondertage, gesetzliche Feiertage und inaktive Wochentage überspringen.
- [X] Aktive Wochenenden und Sondertage mit positiver Sollzeit zulassen.

## Standalone: JSON- und PDF-Import

- [X] Echte Kalenderdatumsprüfung für den Austauschimport ergänzen.
- [X] Strikte Austauschzeitvalidierung ergänzen: ausschließlich `""` oder exaktes `HH:MM`.
- [X] Endliche Zahlen mit `Number.isFinite()` erzwingen.
- [X] Nur `manual`, `pdf` oder `null` als `glz_override_source` akzeptieren.
- [X] Negative Sonderstunden ablehnen.
- [X] `mergePortableExport()` auf partielle Einzelobjektvalidierung mit Detailcodes umstellen.
- [X] `portableExportToStore()` dieselben Validatoren beziehungsweise bereits normalisierte Daten verwenden lassen.
- [X] Testbare reine Hilfsfunktion `mergePdfEntries(existingEntries, pdfEntries)` oder gleichwertig einführen.
- [X] Additiven Standalone-PDF-Import blockweise statt tageweise implementieren.
- [X] PDF-Duplikate per `type + start + end` erkennen.
- [X] PDF-Kommentar- und GLZ-Konfliktregeln wie in Docker implementieren.
- [X] Nur bei realen Änderungen Browserdaten speichern.
- [X] PDF-Blöcke nach Startzeit sortieren, ohne Nachtschichten fachlich falsch zu behandeln.
- [X] Nutzerfeedback um fachliche PDF-Importzähler erweitern.

## Tests

- [X] Docker-`MockSettings` um die Jahresendoption erweitern.
- [X] Docker-Shared-Holiday-Adapter bei fehlendem Flag auf `true` setzen.
- [X] Docker-API-Test für Settings-Default und Speichern der Jahresendoption ergänzen.
- [X] Docker-API- und GUI-Tests für Sondertagsvalidierung, Datumskollisionen beim Bearbeiten und sichtbare Fehlerbehandlung bei fehlgeschlagenen Schreiboperationen ergänzen.
- [X] Standalone-Tests für Sondertagsvalidierung und die automatische Zeitvorbelegung anhand eines positiven Sondertags mit abweichendem Tagesziel ergänzen.
- [X] Docker-Tests für strikten partiellen JSON-Import ergänzen.
- [X] Docker-Test zur Zeitnormalisierung korrigieren: Das tolerierte Format `12:3` wird separat mit dem Ergebnis `12:03` geprüft.
- [X] Docker-Tests für echte ungültige Kalenderdaten, ungültige Austauschzeiten und nicht-endliche Zahlen ergänzen.
- [X] Docker-Tests für negative Zeitwerte, negative Sonderstunden und ungültige GLZ-Quellen ergänzen.
- [X] Docker-API-Tests für nicht-objektförmige JSON-Request-Bodies sowie ungültige Sondertagsstunden und GLZ-Overrides ergänzen.
- [X] Docker-Tests für valide Nachbarobjekte bei ungültigen Einzelobjekten und Detailcodes ergänzen.
- [X] Docker-Tests für ungültige JSON-Container ergänzen.
- [X] Docker-Tests für Serienplanung an aktivem Wochenende sowie für Feiertage und freie Sondertage ergänzen.
- [X] Docker-PDF-Parser-Test mit Fake-PDF für `22:00–02:00` ergänzen.
- [X] Docker-PDF-Parser-Warnung bei Zeiten mit unbekanntem Status und den Testvertrag vereinheitlichen: Der Test erwartet derzeit `unbekannten Status`, der Parser meldet `Zeiten ohne bekannten Status`; fachlich eindeutige, nutzerverständliche Formulierung festlegen und absichern.
- [X] Docker-PDF-Merge-Tests mit `monkeypatch(parse_pdf_content)` ergänzen.
- [X] Docker-API-Tests pro Test isolieren: Testdatenbank beziehungsweise Transaktionen zuverlässig zurücksetzen, damit fehlgeschlagene Tests keine Daten hinterlassen und keine Reihenfolgeabhängigkeiten entstehen.
- [X] Standalone-Test `test_shared_holiday_cases` reparieren: `case` ist ein reserviertes JavaScript-Schlüsselwort und darf nicht als Arrow-Function-Parameter in `page.evaluate()` verwendet werden; Parameter und Zugriffe z. B. in `testCase` umbenennen.
- [X] Standalone-Tests für Jahresendfälle aus den Shared-Cases ergänzen.
- [X] Standalone-Tests von UTC-abhängigen Tageswerten wie `toISOString().split('T')[0]` auf lokale ISO-Datumshilfen umstellen, damit Tages- und Zukunftstests in allen Zeitzonen stabil bleiben.
- [X] Standalone-Testfixture neben LocalStorage auch IndexedDB beziehungsweise gespeicherte File-Handles isolieren oder löschen, damit persistente Browserzustände keine Testreihenfolge beeinflussen.
- [X] Standalone-Tests für strikten partiellen JSON-Import und Detailcodes ergänzen.
- [X] Standalone-Test für GLZ ohne Anchor ab erstem Eintrag des Zieljahres ergänzen.
- [X] Standalone-Test für Serienplanung mit aktivem Wochenende ergänzen.
- [X] Standalone-Test für die PDF-Merge-Hilfsfunktion ergänzen.
- [X] Neue PDF-Tests ausschließlich mit Fakes, Mocks und `monkeypatch` umsetzen.
- [X] Standalone-Teststarter vom aufrufenden Arbeitsverzeichnis entkoppeln: HTTP-Server und `pytest` mit dem Verzeichnis von `run_tests.py` als `cwd` oder mit absoluten Pfaden starten, damit `py StandAlone/run_tests.py` auch aus dem Repository-Root `ho-planer.html` und `test_standalone.py` findet.
- [X] Standalone-Teststarter: feste Wartezeit durch aktive Erreichbarkeitsprüfung des HTTP-Servers ersetzen und bei Fehlstart eine aussagekräftige Fehlermeldung liefern.
- [X] Standalone-Teststarter nach `terminate()` zuverlässig auf Prozessende warten und bei Timeout beenden; Portbelegung sowie Server-stdout/stderr für die Fehlerdiagnose sichtbar machen.
- [X] Standalone-Teststarter unter Windows codepage-unabhängig machen (keine Emoji-bedingten `UnicodeEncodeError` in Konsolenausgaben).
- [X] Testanleitung für Windows um den verfügbaren `py`-Launcher als Alternative zu `python` ergänzen.
- [X] Lokale Testvoraussetzungen eindeutig dokumentieren: Docker benötigt alle Einträge aus `Docker/requirements.txt`; Standalone benötigt `pytest-playwright` (nicht nur `playwright`) sowie die installierten Chromium-Browser-Binaries.
- [X] Für Standalone eine versionierte Testabhängigkeitsdatei oder einen äquivalenten reproduzierbaren Installationsweg bereitstellen, der `pytest-playwright` explizit enthält.
- [X] Lokalen Preflight für beide Teststarter ergänzen, der fehlende Python-Pakete und bei GUI-Tests fehlende Playwright-Browser vor dem Serverstart verständlich meldet.
- [X] Docker-Teststarter unter Windows weiter gegen Prozess-, Port- und Logdatei-Leaks absichern und bei einem tatsächlichen Serverfehler Exitcode sowie vollständige Serverausgabe ausgeben.
- [X] Standalone-Teststarter vor dem Testlauf den konfigurierten Browserpfad prüfen und bei fehlender Browser-Binary mit einer eindeutigen Infrastrukturmeldung beenden.
- [ ] Beide Teststarter nach Änderungen erneut ausführen und fachliche Testfehler getrennt von Infrastrukturfehlern auswerten.

## Dokumentation und Betrieb

- [X] Standalone für abgeschottete oder Offline-Umgebungen belastbar machen: externer CDN-Online-Modus prüft Vue, Vuetify, Chart.js und PDF.js beim Start und zeigt bei fehlenden Abhängigkeiten eine sichtbare Fehlermeldung; für echte Offline-Nutzung bleibt lokales versioniertes Bundling erforderlich.
- [X] Standalone-README präzisieren: PDF-Datenverarbeitung erfolgt lokal im Browser, die aktuelle Anwendung lädt jedoch Laufzeitbibliotheken und den PDF-Worker über CDNs.
- [X] Root-README um klare Architekturübersicht beider Varianten ergänzen.
- [X] Docker-README um die Jahresendoption, JSON-Importregeln und PDF-Merge-Verhalten ergänzen.
- [X] Standalone-README um die Jahresendoption, Browser-Backup/Restore und JSON-Validierung ergänzen.
- [X] Dokumentation zu Datenmodell und Austauschformat aktualisieren.
- [X] Migrationsdokumentation um Version V4 und das Backup-Verhalten ergänzen.
- [X] Backup- und Restore-Anleitung für SQLite-Volume und externe Sicherungen vervollständigen.
- [X] Dokumentation zum Risiko lokaler Browser-Speicherung und zu regelmäßigen JSON-Backups ergänzen.
- [X] Release-Prozess für Änderungen am gemeinsamen Vertrag und an Shared-Testfällen dokumentieren.

## Abschlussprüfungen nach Umsetzung

- [X] `git status --short` separat ausführen und prüfen.
- [X] `git diff --check` separat ausführen und prüfen.
- [X] `git diff --stat` separat ausführen und prüfen.
- [ ] Abschlussbericht mit geänderten Dateien, Testresultaten, Migration, Rückwärtskompatibilität und ausgelassenen privaten Testdateien erstellen.
