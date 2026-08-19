import pytest
import os
from datetime import date
from app import parse_pdf_content 

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
    Prüft: Home Office, Büro, normale Zeiten und GLZ Override Struktur.
    """
    pdf_path = get_pdf_path("standard.pdf")
    
    with open(pdf_path, "rb") as f:
        results = parse_pdf_content(f) 

    # 1. Prüfe generelle Struktur
    assert len(results) > 0, "Keine Einträge gefunden"
    
    # 2. Prüfe einen spezifischen Tag
    entry_2_jun = next((e for e in results if e['date'] == date(2025, 6, 2)), None)
    
    assert entry_2_jun is not None
    assert entry_2_jun['type'] == 'home' 
    assert entry_2_jun['start'] == '07:40'
    assert entry_2_jun['end'] == '16:30'
    # NEU: Das Dictionary muss zwingend den Schlüssel glz_override enthalten
    assert 'glz_override' in entry_2_jun

    # 3. Prüfe einen Büro-Tag
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

    # Prüfe den 09.05.2025 (Fr)
    # Erwartung: 2 Einträge (Fortbildung 09:30-18:00, Reisezeit 18:00-23:59)
    entries_9_may = [e for e in results if e['date'] == date(2025, 5, 9)]
    
    assert len(entries_9_may) >= 2, "Split-Einträge für 09.05. fehlen"
    
    # Sortieren nach Startzeit
    entries_9_may.sort(key=lambda x: x['start'])
    
    # Erster Teil: Fortbildung
    assert entries_9_may[0]['type'] == 'dr' 
    assert entries_9_may[0]['start'] == '09:30'
    assert entries_9_may[0]['end'] == '18:00'
    
    # Zweiter Teil: Reisezeit
    assert entries_9_may[1]['type'] == 'dr' 
    assert entries_9_may[1]['start'] == '18:00'
    assert '23:59' in entries_9_may[1]['end'] 

def test_pdf_import_error_handling():
    """
    Szenario C: Fehler-Fall (Feb 2026)
    Prüft: 'BUCHUNG FEHLT' wird erkannt und nicht ignoriert.
    """
    pdf_path = get_pdf_path("error.pdf")
    
    with open(pdf_path, "rb") as f:
        results = parse_pdf_content(f)

    # Prüfe 13.02.2026 (Fr)
    entry_13_feb = next((e for e in results if e['date'] == date(2026, 2, 13)), None)
    
    assert entry_13_feb is not None
    assert "fehlt" in (entry_13_feb.get('comment') or "").lower()