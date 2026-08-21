# HO-Planer (Standalone Edition) 🏠🏢

Ein privates Dashboard zur Planung, Erfassung und Auswertung von Arbeitszeiten, Home-Office-Budgets und Gleitzeitsalden. 

Das Besondere an dieser Edition: **Es ist nur eine einzige HTML-Datei.**

## 🚀 Quickstart (Nutzung)

1. Lade dir die Datei `ho-planer.html` herunter.
2. Mach einen Doppelklick darauf (öffnet sich in Chrome, Edge, Firefox, Safari etc.).
3. Fertig. Du kannst das Tool direkt nutzen.

### 💾 Wo liegen meine Daten?
Da es keinen Server gibt, speichert die App deine Einträge sicher im `localStorage` und der `IndexedDB` deines Browsers. 
* **Tipp für Backups:** Über das Menü kannst du deine Daten jederzeit als `.json`-Datei auf deine Festplatte exportieren und auch wieder nahtlos einlesen (nutzt die moderne File-System API). 

---

## 💡 Features

### 📅 Smarte Zeiterfassung & Planung
* **Split-Buchungen:** Vormittags Home Office, nachmittags im Büro? Lässt sich pro Tag beliebig aufteilen.
* **Serien-Planer:** Wiederkehrende Muster (z.B. "Jeden Freitag Home Office") mit wenigen Klicks für ganze Monate im Voraus eintragen.
* **Auto-Umwandlung:** In der Zukunft liegende Tage können als "Geplant" markiert werden. Verstreicht das Datum, wandelt das System den Eintrag automatisch in echte Arbeitszeit (inkl. Standard-Startzeit) um.

### ⚖️ Arbeitszeitgesetz (ArbZG) integriert
Du musst keine Pausen mehr selbst ausrechnen. Die Logik arbeitet mit einer automatischen "Treppen-Kappungsgrenze":
* **Bis 6h Präsenz:** Kein Abzug.
* **Zwischen 6h und 6,5h:** Nettozeit friert bei exakt 6.0h ein.
* **Bis 9,5h Präsenz:** 30 Minuten gesetzliche Pause werden abgezogen.
* **Ab 9,75h Präsenz:** Volle 45 Minuten Pause werden abgezogen.

### 💰 Budgets & Gleitzeit (GLZ)
* **Live-Quote:** Zeigt dir an, wie viele HO-Tage im aktuellen Monat noch in dein Budget passen (z.B. bei 60% Vertrag) – inkl. Fortschrittsbalken.
* **Gleitzeit-Tracking:** Rechnet deinen GLZ-Saldo fortlaufend mit. Du kannst an jedem beliebigen Tag einen "Offiziellen PDF Saldo" setzen, ab dem das System den Stand neu synchronisiert.

### 📄 Automatischer PDF-Import (100% Lokal)
Lade deinen offiziellen Zeitnachweis (PDF) hoch. Das Tool liest das Dokument über `pdf.js` **komplett lokal in deinem Browser** aus (kein Upload ins Internet!).
Erkannt werden:
* Arbeitszeiten (Start/Ende)
* Statustexte (Telearb., Mobil, Dienstreise, Krank, Urlaub)
* Der offizielle Gleitzeitsaldo an den jeweiligen Tagen

### 📊 Dashboard & Visualisierung
* **Interaktive Charts:** Jahresansicht mit Chart.js (Donut-Chart für die Verteilung der gearbeiteten Tage, Bar-Chart für den monatlichen Home-Office-Verlauf).
* **Feiertags-Engine:** Berücksichtigt automatisch alle Feiertage in Hessen bei der Soll-Zeit-Berechnung. Eigene freie Tage (Betriebsausflug, Wäldchestag) lassen sich frei hinzufügen.

---

## 🔄 Gemeinsamer fachlicher Vertrag

Docker und Standalone haben unterschiedliche Laufzeitumgebungen, verwenden aber denselben versionierten Datenvertrag und dieselben Referenzfälle für Fachregeln:

- [`../shared/contracts/business-rules.md`](../shared/contracts/business-rules.md): verbindliche Berechnungs- und Importregeln
- [`../shared/contracts/data-model.md`](../shared/contracts/data-model.md): gemeinsames Datenmodell
- [`../shared/contracts/json-export.schema.json`](../shared/contracts/json-export.schema.json): JSON-Austauschformat, Version 1
- [`../shared/test-cases/`](../shared/test-cases/): gemeinsame Referenzfälle für Pausen, Feiertage, unvollständige Einträge, GLZ und Import

Die Browser-Speicherung bleibt die produktive Datenhaltung der Standalone-Variante. JSON dient für Export, Import und den Austausch mit Docker.

- [Zentrale Testanleitung](../docs/testing.md)

## 🛠️ Tech Stack
Da diese Variante ohne Backend auskommt, passiert die gesamte Magie im Frontend:
* **UI/Framework:** Vue.js 3 & Vuetify 3 (über CDN geladen)
* **Charts:** Chart.js
* **PDF-Parsing:** PDF.js (Mozilla)
* **Persistenz:** LocalStorage & IndexedDB, File-System API
