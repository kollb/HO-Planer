import pytest
import os
from datetime import date
# HIER ANPASSEN: Importiere deine Parse-Funktion
# z.B. from logic import parse_pdf_text, extract_data_from_pdf
from app import parse_pdf_content # Beispielname

PRIVATE_DIR = os.path.join(os.path.dirname(__file__), "testfiles")

def get_pdf_path(filename):
    """Hilfsfunktion: Liefert Pfad oder überspringt Test, wenn Datei fehlt."""
    path = os.path.join(PRIVATE_DIR, filename)
    if not os.path.exists(path):
        pytest.skip(f"Private PDF '{filename}' nicht gefunden. Test übersprungen.")
    return path

def test_pdf_import_standard_month():
    """
    Szenario A: Standard-Monat (Juni 2025)
    Prüft: Home Office, Büro und normale Zeiten.
    """
    pdf_path = get_pdf_path("standard.pdf")
    
    # Wir lesen die Datei als Bytes (wie Flask es tun würde)
    with open(pdf_path, "rb") as f:
        # Rufe deine Logik-Funktion auf
        # Ergebnis sollte eine Liste von Dictionaries oder Objekten sein
        results = parse_pdf_content(f) 

    # 1. Prüfe generelle Struktur
    assert len(results) > 0, "Keine Einträge gefunden"
    
    # [cite_start]2. Prüfe einen spezifischen Tag: 02.06.2025 (Mo) -> Mobil/Telearb. [cite: 19]
    # Suche den Eintrag für den 2. Juni
    entry_2_jun = next((e for e in results if e['date'] == date(2025, 6, 2)), None)
    
    assert entry_2_jun is not None
    assert entry_2_jun['type'] == 'home'  # Oder wie dein Code "Mobil" nennt
    assert entry_2_jun['start'] == '07:40'
    assert entry_2_jun['end'] == '16:30'

    # [cite_start]3. Prüfe einen Büro-Tag: 05.06.2025 (Do) -> anwesend [cite: 19]
    entry_5_jun = next((e for e in results if e['date'] == date(2025, 6, 5)), None)
    assert entry_5_jun['type'] == 'office'
    assert entry_5_jun['start'] == '07:49'
    assert entry_5_jun['end'] == '16:35'

def test_pdf_import_complex_split():
    """
    Szenario B: Komplexer Monat (Mai 2025)
    Prüft: Fortbildung + Reisezeit an einem Tag (Split-Buchung).
    """
    pdf_path = get_pdf_path("complex.pdf")
    
    with open(pdf_path, "rb") as f:
        results = parse_pdf_content(f)

    # [cite_start]Prüfe den 09.05.2025 (Fr) [cite: 73]
    # Erwartung: 2 Einträge (Fortbildung 09:30-18:00, Reisezeit 18:00-23:59)
    entries_9_may = [e for e in results if e['date'] == date(2025, 5, 9)]
    
    assert len(entries_9_may) >= 2, "Split-Einträge für 09.05. fehlen"
    
    # Sortieren nach Startzeit
    entries_9_may.sort(key=lambda x: x['start'])
    
    # Erster Teil: Fortbildung
    assert entries_9_may[0]['type'] == 'dr' # Oder 'fortbildung'/'travel' je nach Mapping
    assert entries_9_may[0]['start'] == '09:30'
    assert entries_9_may[0]['end'] == '18:00'
    
    # Zweiter Teil: Reisezeit
    assert entries_9_may[1]['type'] == 'dr' 
    assert entries_9_may[1]['start'] == '18:00'
    # Hinweis: Manche Parser machen aus 23:59 -> 24:00 oder lassen es. Prüfe deine Logik.
    assert '23:59' in entries_9_may[1]['end'] 

def test_pdf_import_error_handling():
    """
    Szenario C: Fehler-Fall (Feb 2026)
    Prüft: 'BUCHUNG FEHLT' wird erkannt und nicht ignoriert.
    """
    pdf_path = get_pdf_path("error.pdf")
    
    with open(pdf_path, "rb") as f:
        results = parse_pdf_content(f)

    # [cite_start]Prüfe 13.02.2026 (Fr) [cite: 125]
    entry_13_feb = next((e for e in results if e['date'] == date(2026, 2, 13)), None)
    
    assert entry_13_feb is not None
    # Deine Logik sollte das entweder als speziellen Typ speichern oder einen Kommentar setzen
    # Beispiel-Annahme:
    assert "fehlt" in (entry_13_feb.get('comment') or "").lower() 
    # ODER wenn du den Typ leer lässt:
    # assert entry_13_feb['type'] == ''