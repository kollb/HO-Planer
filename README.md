# HO-Planer

Dieses Repository enthält zwei technische Varianten derselben Arbeitszeit-, Home-Office- und Gleitzeit-Anwendung:

- [`Docker/`](Docker/): Flask-, SQLite- und Docker-Variante für NAS oder Server.
- [`StandAlone/`](StandAlone/): einzelne HTML-Datei für die lokale Nutzung im Browser ohne Server.

## Architekturübersicht

| Aspekt | Docker-Variante | Standalone-Variante |
| --- | --- | --- |
| Laufzeit | Flask-Anwendung im Docker-Container oder lokal mit Python | einzelne HTML-Datei im Browser, ohne eigenen Server |
| Persistenz | SQLite unter `/app/data/database.db` in einem persistenten Docker-Volume | Browser-`localStorage`; ergänzend IndexedDB und File System Access API für lokale Dateien |
| Betrieb | für vertrauenswürdiges LAN/NAS; Datenbank, Logs und Backups müssen extern gesichert werden | für eine einzelne Browser-Installation; Browserdaten können durch Bereinigung, Profilwechsel oder Geräteverlust verloren gehen |
| Datenaustausch | versionierter JSON-Export/-Import | derselbe versionierte JSON-Export/-Import |
| Laufzeitabhängigkeiten | Python-Pakete im Container | aktuell zusätzlich CDNs für UI-, Diagramm- und PDF-Bibliotheken; für den Erststart ist Internetzugriff erforderlich |

## Gemeinsame Verträge

Die Laufzeitumgebungen unterscheiden sich bewusst: Python/Flask und Browser-JavaScript können Fachcode nicht unmittelbar als dieselbe Bibliothek ausführen. Fachliche Gleichheit wird deshalb über versionierte, gemeinsame Verträge und Referenzfälle abgesichert:

- [`shared/contracts/business-rules.md`](shared/contracts/business-rules.md): fachliche Berechnungs- und Importregeln.
- [`shared/contracts/data-model.md`](shared/contracts/data-model.md): gemeinsame Entitäten und Feldbedeutungen.
- [`shared/contracts/json-export.schema.json`](shared/contracts/json-export.schema.json): versioniertes JSON-Austauschformat.
- [`shared/test-cases/`](shared/test-cases/): von beiden Varianten verwendbare Referenzfälle.

JSON ist ein Austausch-, Export- und Importformat. Die Docker-Variante verwendet SQLite weiterhin als produktive Datenhaltung; die Standalone-Variante speichert lokal im Browser.

## Dokumentation

- Installation und Nutzung: [`Docker/README.md`](Docker/README.md), [`StandAlone/README.md`](StandAlone/README.md)
- [Testanleitung](docs/testing.md)
- Docker-Migration, Backup und Wiederherstellung: [`Docker/docs/migrations-and-backups.md`](Docker/docs/migrations-and-backups.md)
- Automatisierung: [`.github/workflows/`](.github/workflows/)

Die produktive Docker-Oberfläche ist `/` (`Docker/static/index.html`). Sie basiert auf der früheren Beta-Oberfläche; `/beta` leitet aus Kompatibilitätsgründen auf `/` weiter.
