# HO-Planer 🏠🏢

Ein Tool zur Planung, Erfassung und Auswertung von Home-Office- und Büro-Tagen mit automatischer Quotenberechnung.

## Features

### 📅 Planung & Erfassung
* **Detaillierte Statuserfassung:** Unterscheide präzise zwischen *Home Office*, *Büro*, *Dienstreise*, *Gleitzeitabbau*, *Krankheit* und *Urlaub*.
* **Split-Buchungen:** Der Tag war zweigeteilt? Kein Problem. Erfasse z.B. vormittags Home Office und nachmittags Büro in einem einzigen Tag.
* **Serien-Planer:** Plane wiederkehrende Muster (z.B. "Jeden Freitag Home Office") für einen gewählten Zeitraum im Voraus.
* **Intelligente Automatisierung:** Markiere Tage als "Geplant". Sobald der Tag vergangen ist, wandelt das System ihn automatisch in einen tatsächlichen Eintrag um und trägt die Standard-Arbeitszeit ein.

### 📊 Quote & Budget
* **Live-Budget:** Sieh auf einen Blick, wie viele Home-Office-Tage dir im aktuellen Monat noch zustehen (basierend auf der eingestellten Quote, z.B. 60%).
* **Visuelle Warnungen:** Ein farbiger Balken zeigt an, ob du dich im grünen Bereich befindest oder deine Quote überschreitest.
* **Jahresübersicht:** Eine tabellarische Auswertung zeigt dir Summen für jeden Monat (Tage im HO, Tage im Büro, Urlaubstage).

### ⚙️ Automatik & Logik
* **PDF Import:** Lade deinen offiziellen Zeitnachweis (PDF) hoch. Das Tool extrahiert automatisch Arbeitszeiten und den Status (z.B. "Telearb.", "Mobil", "Dienstreise") und trägt sie in den Kalender ein.
* **Pausenabzug:** Die Netto-Arbeitszeit wird automatisch berechnet. Pausen werden gemäß gesetzlicher Regelungen (z.B. ab 6h oder 9h Arbeit) automatisch abgezogen.
* **Feiertage:** Kennt alle Feiertage (Hessen) und berücksichtigt diese bei der Berechnung der Soll-Stunden. Du kannst zudem eigene freie Tage (z.B. Wäldchestag, Betriebsausflug) definieren.

### 🎨 Bedienung
* **Verschiedene Ansichten:** Wechsle zwischen einer kompakten Listenansicht, einem Monats-Kalender und der Jahresstatistik.
* **Dark Mode:** Augenschonendes Design, das sich umschalten lässt.
* **Standalone-Option:** Möglichkeit, Daten lokal als JSON zu speichern und zu laden (via FileSystem API).

## Installation

1.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```

## Starten der App

Führe einfach die `app.py` aus:

```bash
python app.py