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
- Aktive Wochentage bestimmen die Sollzeitverteilung; Samstag und Sonntag können aktiv sein.
- Eigene Sondertage mit `hours = 0` sind arbeitsfrei. Eigene Sondertage mit `hours > 0` sind Arbeitstage mit eigener Sollzeit.
- Ein eigener Sondertag ist nur ein kurzer Tag (`is_short_day: true`), wenn `0 < hours < weekly_hours / Anzahl_aktiver_Wochentage`. Eine eigene Sollzeit in Höhe oder oberhalb der regulären Tages-Sollzeit ist kein kurzer Tag.
- Unvollständige Einträge der Typen `home`, `office` und `dr` zählen nur für zukünftige Tage mit Sollzeit. Für heute und vergangene Tage zählen sie mit 0 Stunden.
- Unvollständige `planned`-Einträge erhalten weiterhin Sollzeit.
- Ein GLZ-Override dient als Anker für die weitere Saldenberechnung. Seine Quelle ist `manual` oder `pdf`.

## Austauschformat und Import

- Das verbindliche Schema ist `json-export.schema.json` mit `format: ho-planer-export` und `version: 1`.
- Der Standardimport ist additiv und übernimmt keine Einstellungen.
- Die Identität eines Eintrags besteht aus `date`, `type`, `start`, `end` und `comment`.
- Identische Einträge werden übersprungen; abweichende Einträge am selben Tag werden ergänzt.
- Abweichende GLZ-Overrides und eigene Feiertage werden im Standardmodus nicht still überschrieben.
- Der Docker-Überschreibmodus erstellt vor einem Import ein SQLite-Backup.
