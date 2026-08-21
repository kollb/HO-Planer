# Gemeinsames Datenmodell

Die Varianten verwenden unterschiedliche Persistenztechniken, aber dieselben fachlichen Entitäten.

## Einstellungen

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `weekly_hours` | Zahl | Wochen-Sollstunden |
| `active_weekdays` | Liste 0–6 | Aktive Wochentage, Montag = 0 |
| `ho_quota_percent` | Zahl | HO-Budget in Prozent |
| `hide_weekends` | Boolean | Darstellungsoption |
| `default_start_time` | `HH:MM` | Startzeit für automatische Umwandlungen |
| `auto_convert_planned` | Boolean | Automatische Planungsumwandlung |

## Arbeitszeiteintrag

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `date` | `YYYY-MM-DD` | Kalendertag |
| `type` | Enum | `home`, `office`, `dr`, `planned`, `sick`, `vacation`, `glz` oder leer |
| `start` | `HH:MM` oder leer | Beginn |
| `end` | `HH:MM` oder leer | Ende |
| `comment` | Text | Freitext |
| `glz_override` | Zahl oder `null` | optionaler GLZ-Anker |
| `glz_override_source` | `manual`, `pdf` oder `null` | Herkunft des Ankers |

## Eigener Feiertag

| Feld | Typ | Bedeutung |
| --- | --- | --- |
| `date` | `YYYY-MM-DD` | Kalendertag |
| `name` | Text | Bezeichnung |
| `hours` | Zahl ≥ 0 | Sollzeit am Sondertag; 0 bedeutet frei |

## Persistenzzuordnung

- **Docker:** SQLite über SQLAlchemy; lokale Datenbank-IDs bleiben intern und werden nicht exportiert.
- **Standalone:** `localStorage` für den Arbeitsbestand sowie IndexedDB/File System Access API für verknüpfte lokale Dateien.
- **Austausch:** ausschließlich das versionierte JSON-Format; JSON ersetzt SQLite nicht.
