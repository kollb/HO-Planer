# Sicherheitshinweise

Der HO-Planer verarbeitet persönliche Zeitdaten. Hinweise auf Schwachstellen
nehmen wir ernst und bevorzugt vertraulich entgegen.

## Unterstützte Versionen

| Stand | Unterstützt |
| --- | --- |
| Release `v1.1` und neuer (Tag `v*`) | ja |
| Aktueller Stand von `main` | ja |
| Ältere Stände | nein |

Es gibt keine parallelen Wartungszweige: Sicherheitskorrekturen gehen in `main`
und erscheinen mit dem nächsten Release.

## Schwachstelle melden

Bitte **kein öffentliches Issue** für Sicherheitsprobleme.

1. Über den Reiter *Security* → *Report a vulnerability* einen privaten
   Sicherheitshinweis eröffnen (Private Vulnerability Reporting).
2. Falls das nicht möglich ist: eine E-Mail an die Betreiber des Repositories
   mit Betreff `[SECURITY] HO-Planer`.

Bitte schildere betroffene Variante (Docker oder Standalone), Version bzw.
Commit, Schritte zur Reproduktion und die Wirkung. Wir bestätigen den Eingang
und melden uns mit einer Einschätzung.

## Nicht sicherheitsrelevant

Fehler ohne Sicherheitswirkung gehören in ein normales Issue.

## Hinweise zum Betrieb

- Private PDFs und lokale Testdaten gehören nicht ins Repository (`pdf/` und
  `Docker/tests/testfiles/` sind bewusst ignoriert).
- Die Standalone-Variante speichert ihre Daten im Browser bzw. in der
  verbundenen Datei; Backups liegen in der Verantwortung der Nutzenden.
- Das Container-Image wird als `derplm/ho-tracker:latest` veröffentlicht.
