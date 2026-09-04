# Fachliche Regeln

Diese Spezifikation ist der gemeinsame fachliche Vertrag für die Docker- und die Standalone-Variante. Sie beschreibt bestehendes Verhalten; Änderungen daran benötigen eine bewusste fachliche Entscheidung.

## Arbeitszeit und Pausen

- Zeitlich erfasste Arbeitsblöcke der Typen `home`, `office`, `dr` und `planned` werden pro Kalendertag brutto summiert.
- Die ArbZG-Pausenlogik wird genau einmal auf diese Summe angewendet:
  - bis einschließlich 6,00 Stunden Brutto: keine Pause,
  - über 6,00 bis einschließlich 6,50 Stunden: 6,00 Stunden Netto,
  - über 6,50 bis einschließlich 9,50 Stunden: 30 Minuten Pause,
  - über 9,50 bis einschließlich 9,75 Stunden: 9,00 Stunden Netto,
  - über 9,75 Stunden: 45 Minuten Pause.
- Die Tagesnettozeit wird proportional zur Bruttozeit auf die zeitlich erfassten Blöcke verteilt. Das erhält die HO-/Büro-Verteilung in Auswertungen.
- Endet ein Block vor seinem Start, wird er als Nachtschicht behandelt.

## Sollzeit, Planung und GLZ

- Gesetzliche Feiertage in Hessen haben Vorrang vor eigenen Sondertagen.
- Heiligabend und Silvester sind standardmäßig arbeitsfrei. Die Einstellung `christmas_eve_and_new_years_eve_off` kann diese Zusatzregel deaktivieren; gesetzliche Feiertage bleiben davon unberührt.
- Beide Varianten ermitteln Feiertage unabhängig voneinander: Docker über eine Feiertagsbibliothek, Standalone über eine eigene Osterformel. Sie müssen für jedes Datum denselben Feiertag mit demselben Namen liefern. Verbindlich ist der vollständige Kalender in `shared/test-cases/holidays-calendar.json`; er umfasst die Jahre 2020 bis 2040 mit zehn gesetzlichen Feiertagen je Jahr sowie Heiligabend und Silvester als schaltbare Jahresendtage.
- Verbindliche Feiertagsnamen sind `Neujahr`, `Karfreitag`, `Ostermontag`, `Tag der Arbeit`, `Christi Himmelfahrt`, `Pfingstmontag`, `Fronleichnam`, `Tag der Deutschen Einheit`, `1. Weihnachtstag`, `2. Weihnachtstag` sowie `Heiligabend` und `Silvester`. Abweichende Bezeichnungen einer Feiertagsbibliothek werden auf diese Schreibweise normalisiert.
- Die Jahresendoption wird ausschließlich vom zentralen Feiertagshelper ausgewertet. Tests dürfen Heiligabend und Silvester nicht selbst in die Feiertagsliste eintragen, weil sie sonst nur die Testlogik prüfen.
- Aktive Wochentage bestimmen die Sollzeitverteilung; Samstag und Sonntag können aktiv sein.
- Serienplanung erzeugt Einträge nur für ausgewählte Wochentage, die gemäß zentraler Tageslogik echte Arbeitstage sind. Gesetzliche Feiertage, freie Sondertage und inaktive Wochentage werden übersprungen; aktive Wochenendtage und Sondertage mit positiver Sollzeit bleiben planbar.
- Ein geplanter Eintrag beginnt zur eingestellten Standardstartzeit. Seine Endzeit ergibt sich aus der Tagessollzeit zuzüglich der dafür nötigen Pause gemäß `calculate_gross_time_needed`; maßgeblich ist die tatsächliche Sollzeit des Tages, nicht die allgemeine Wochen-Tagessollzeit. Verbindliche Referenzfälle liegen in `shared/test-cases/series-planning.json`; beide Varianten prüfen daraus geplante Datumswerte, Sollzeit, Startzeit und abgeleitete Endzeit.
- Die Vorschau der Serienplanung verändert keine Daten. Erst die Bestätigung speichert; Vorschau und Bestätigung melden dieselben Datumswerte.
- Eigene Sondertage mit `hours = 0` sind arbeitsfrei. Eigene Sondertage mit `hours > 0` sind Arbeitstage mit eigener Sollzeit.
- Ein eigener Sondertag ist nur ein kurzer Tag (`is_short_day: true`), wenn `0 < hours < weekly_hours / Anzahl_aktiver_Wochentage`. Eine eigene Sollzeit in Höhe oder oberhalb der regulären Tages-Sollzeit ist kein kurzer Tag.
- Unvollständige Einträge der Typen `home`, `office` und `dr` zählen nur für zukünftige Tage mit Sollzeit. Für heute und vergangene Tage zählen sie mit 0 Stunden.
- Unvollständige `planned`-Einträge erhalten weiterhin Sollzeit.
- Ein GLZ-Override dient als Anker für die weitere Saldenberechnung. Seine Quelle ist `manual` oder `pdf`.
- Der Anker ist der Startwert der Fortschreibung, nicht deren Ergebnis: Ab dem Tag nach dem Anker läuft der Saldo mit Soll- und Istzeiten weiter.
- Liegen an einem Tag mehrere Anker, ist der zuletzt gespeicherte maßgeblich.
- Ohne GLZ-Anker beginnt die Saldenberechnung beim ersten gespeicherten Eintrag des Zieljahres. Gibt es bis zum Zielmonat keinen solchen Eintrag, beträgt der GLZ-Saldo `0.0`.
- Verbindliche Referenzfälle liegen in `shared/test-cases/glz.json`. Jeder Fall nennt mit `evaluation_settings` die Auswertungsbasis, mit `carryover_target` den Zielmonat und mit `expected_carryover` den erwarteten Saldo. Beide Varianten müssen jeden Fall auf denselben Saldo rechnen und zusätzlich Wert und Quelle des erwarteten Ankers erhalten.

## Austauschformat und Import

- Das verbindliche Schema ist `json-export.schema.json` mit `format: ho-planer-export` und `version: 1`.
- Der Standardimport ist additiv und übernimmt keine Einstellungen.
- Die Identität eines Eintrags besteht aus `date`, `type`, `start`, `end` und `comment`.
- Identische Einträge werden übersprungen; abweichende Einträge am selben Tag werden ergänzt.
- Abweichende GLZ-Overrides und eigene Feiertage werden im Standardmodus nicht still überschrieben.
- Der Docker-Überschreibmodus erstellt vor einem Import ein SQLite-Backup.
- Ein Austauschdatum muss ein echtes ISO-Kalenderdatum im Format `YYYY-MM-DD` sein. Austauschzeiten sind ausschließlich leer oder im exakten Format `HH:MM` zulässig.
- GLZ-Overrides und Sonderstunden müssen endliche Zahlen sein. Sonderstunden dürfen nicht negativ sein; als GLZ-Overridequellen sind nur `manual`, `pdf` oder `null` zulässig.
- Ein gültiger Importcontainer wird partiell verarbeitet: Ungültige Einzelobjekte werden übersprungen, valide Nachbarobjekte bleiben importierbar. Für ungültige Einträge liefern beide Varianten neutrale Detailcodes im Format `entries[index]: code`, beispielsweise `invalid_date`, `invalid_time`, `invalid_glz_override` oder `invalid_glz_override_source`.
- Für eigene Feiertage gilt dieselbe Regel mit dem Präfix `custom_holidays[index]:` und den Codes `invalid_object`, `invalid_date`, `invalid_name` sowie `invalid_hours`. Beide Varianten prüfen in derselben Reihenfolge (Datum, Name, Stunden) und melden damit identische Codes.
- Verbindliche Referenzfälle liegen in `shared/test-cases/json-import.json`. Docker und Standalone führen dieselbe Datei aus; ein Fall ist erst erledigt, wenn er in beiden Suiten grün ist.

## PDF-Import

- PDF-Zeitblöcke sind additiv. Ihre Identität besteht aus `date`, `type`, `start` und `end`; der Kommentar ist kein Identitätsmerkmal.
- Im Zeitnachweis bedeutet `00:00` zweierlei: eine unbebuchte Spalte oder die Mitternachtsgrenze einer Nachtschicht. Verworfen werden ausschließlich Zeilen, die nur aus solchen Platzhaltern bestehen. Jede andere Uhrzeit bleibt erhalten, damit Nachtschichten wie `22:00–00:00` oder `00:00–08:00` nicht als ungerade Zeitfolge verloren gehen. Verbindliche Referenzfälle liegen in `shared/test-cases/pdf-night-shifts.json`.
- Ein identischer PDF-Block wird nicht erneut gespeichert. Fehlt beim bestehenden Block ein Kommentar, wird ein nichtleerer PDF-Kommentar ergänzt; bei zwei verschiedenen nichtleeren Kommentaren bleibt der bestehende Kommentar erhalten und der Import meldet einen Kommentarhinweis.
- Ein bestehender GLZ-Override wird nicht überschrieben. Bei abweichendem PDF-Override bleibt der Zeitblock importierbar, jedoch ohne kollidierenden Override; der Import meldet einen GLZ-Konflikt.
- Ein Überschreibimport ersetzt weiterhin alle Tagesblöcke durch die importierten PDF-Blöcke.
