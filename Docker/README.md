# HO-Planer 🏠🏢

Schluss mit unübersichtlichen Excel-Listen und manuellem Ausrechnen von Home-Office-Quoten. Der HO-Planer ist ein privates Dashboard zur Planung, Erfassung und Auswertung von Arbeitszeiten, Home-Office-Budgets und Gleitzeitsalden.

Verfügbar als Full-Stack Web-App (Docker/Python).

## 💡 Was das Teil kann (Features)

### 📅 Smarte Zeiterfassung & Planung
* **Split-Buchungen:** Vormittags Home Office, nachmittags im Büro? Lässt sich pro Tag beliebig aufteilen.
* **Serien-Planer:** Wiederkehrende Muster (z.B. "Jeden Freitag Home Office") mit wenigen Klicks für ganze Monate im Voraus eintragen.
* **Auto-Umwandlung:** In der Zukunft liegende Tage können als "Geplant" markiert werden. Verstreicht das Datum, wandelt das System den Eintrag automatisch in echte Arbeitszeit (inkl. Standard-Startzeit) um.

### ⚖️ Arbeitszeitgesetz (ArbZG) Out-of-the-box
Nie wieder manuell Pausen abziehen. Das Tool rechnet mit einer intelligenten "Treppen-Logik":
* Präsenz bis 6 Stunden: Kein Abzug.
* Präsenz zwischen 6h und 6,5h: Nettozeit wird auf exakt 6.0h gedeckelt (Kappungsgrenze).
* Präsenz bis 9,5h: 30 Minuten gesetzliche Pause werden automatisch abgezogen.
* Präsenz ab 9,75h: Volle 45 Minuten Pause werden abgezogen.

### 💰 Budgets & Gleitzeit (GLZ)
* **Live-Quote:** Zeigt sofort an, wie viele HO-Tage im aktuellen Monat noch ins Budget passen (z.B. bei 60% Quote) – inkl. visuellem Fortschrittsbalken.
* **Gleitzeit-Tracking:** Berechnet den GLZ-Saldo fortlaufend über Monate und Jahre hinweg. 
* **PDF Sync-Anker:** Um Rundungsfehler auszugleichen, kann an jedem beliebigen Tag ein "Offizieller PDF Saldo" gesetzt werden, ab dem das System neu weiterrechnet.

### 📄 Automatischer PDF-Import
Kein Bock auf manuelles Abtippen? Lade deinen offiziellen Zeitnachweis hoch.
Der Parser erkennt automatisch:
* Monat & Jahr
* Arbeitszeiten (Start/Ende)
* Status-Kürzel (Telearb., Mobil, Dienstreise, Krank, Urlaub)
* Den offiziellen Gleitzeitsaldo am Tag der Buchung

### 📊 Dashboard & Visualisierung
* **Interaktive Charts:** Chart.js Integration für die Jahresansicht (Donut-Chart für die Verteilung, Bar-Chart für den monatlichen HO-Verlauf).
* **Feiertags-Engine:** Kennt bewegliche und feste Feiertage (Hessen) und zieht diese bei der Soll-Zeit-Berechnung ab. Eigene Feiertage (Betriebsausflug, Wäldchestag) sind frei konfigurierbar.

---

## 🚀 Installation & Setup

Das Projekt ist flexibel und lässt sich auf drei verschiedene Arten nutzen.

### Option 1: Docker (Empfohlen für Server / NAS)
Die beste Wahl, wenn du das Tool dauerhaft im Heimnetzwerk hosten willst.

```bash
# Image bauen
docker build -t ho-planer .

# Container starten (Port 5000)
# Der Volume-Mount sichert die SQLite DB und Auto-Backups
docker run -d -p 5000:5000 -v $(pwd)/data:/app/data --name ho-planer-app ho-planer
```
Die App erreichst du dann unter `http://localhost:5000`.

### Betrieb im NAS/LAN

Die Anwendung ist für ein vertrauenswürdiges lokales Netzwerk vorgesehen. Keine Router-Portweiterleitung für Port `5000` einrichten; die NAS-Firewall auf die benötigten lokalen Netze beschränken. `-p 5000:5000` bindet den Port in der Regel an alle Host-Netzwerkschnittstellen. Für ausschließlich lokalen Zugriff verwende stattdessen `-p 127.0.0.1:5000:5000`; andere LAN-Geräte können dann nicht zugreifen.

`/app/data` enthält SQLite-Datenbank, Logs und Backups und muss persistent sowie für den Container beschreibbar sein. Backups im gleichen Volume schützen nicht gegen einen NAS- oder Volume-Ausfall; sichere sie zusätzlich außerhalb des Hosts. Details stehen unter [Migration, Backup und Wiederherstellung](docs/migrations-and-backups.md).

### Option 2: Python / Lokal (Für Entwickler)
Wenn du den Code anpassen oder das Tool nativ auf deinem Rechner laufen lassen möchtest.

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt

# App starten
python app.py
```
Die App erreichst du dann unter `http://localhost:5000`.

---

## 🔄 Gemeinsamer fachlicher Vertrag

Docker und Standalone haben unterschiedliche Laufzeitumgebungen, verwenden aber denselben versionierten Datenvertrag und dieselben Referenzfälle für Fachregeln:

- [`../shared/contracts/business-rules.md`](../shared/contracts/business-rules.md): verbindliche Berechnungs- und Importregeln
- [`../shared/contracts/data-model.md`](../shared/contracts/data-model.md): gemeinsames Datenmodell
- [`../shared/contracts/json-export.schema.json`](../shared/contracts/json-export.schema.json): JSON-Austauschformat, Version 1
- [`../shared/test-cases/`](../shared/test-cases/): gemeinsame Referenzfälle für Pausen, Feiertage, unvollständige Einträge, GLZ und Import

Die SQLite-Datenbank bleibt die produktive Datenhaltung der Docker-Variante. JSON dient nur Export, Import und Austausch.

- [Zentrale Testanleitung](../docs/testing.md)
- [Migration, Backup und Wiederherstellung](docs/migrations-and-backups.md)

## 🛠️ Tech Stack
* **Frontend:** Vue.js 3, Vuetify 3, Chart.js, PDF.js (für den Standalone-Import)
* **Backend:** Flask (Python), SQLAlchemy, SQLite, pdfplumber
* **Testing:** Pytest & Playwright


Docker 

docker build .
docker push derplm/ho-tracker:latest