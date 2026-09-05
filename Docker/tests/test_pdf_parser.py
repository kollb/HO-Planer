import json
import pytest
import os
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from app import MAX_PDF_PAGES, merge_pdf_entries, parse_pdf_content, pdf_times_from_row

SHARED_NIGHT_SHIFT_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "pdf-night-shifts.json"


class FakePdf:
    def __init__(self, page_count):
        self.pages = [object()] * page_count

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False


def test_pdf_import_rejects_too_many_pages(monkeypatch):
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakePdf(MAX_PDF_PAGES + 1))

    with pytest.raises(ValueError, match='mehr als'):
        parse_pdf_content(object())


class FakePage:
    def __init__(self, text, tables=None):
        self.text = text
        self.tables = tables or []

    def extract_text(self):
        return self.text

    def extract_tables(self):
        return self.tables


class FakeContentPdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback):
        return False


def test_pdf_parser_marks_unknown_status_instead_of_office(monkeypatch):
    page = FakePage(
        'Monat: Februar 2026',
        [[['03 DI Unbekannter Status 08:00 16:00']]],
    )
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, report = parse_pdf_content(object(), include_report=True)

    assert entries[0]['type'] == ''
    assert 'unbekannter Status' in entries[0]['comment']
    assert any('unbekannten Status' in warning for warning in report['warnings'])


def test_pdf_parser_uses_text_fallback_and_reports_odd_time(monkeypatch):
    page = FakePage('Monat: Februar 2026\n03 DI Mobil 08:00 12:00 13:00')
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, report = parse_pdf_content(object(), include_report=True)

    assert entries[0]['type'] == 'home'
    assert entries[0]['start'] == '08:00'
    assert entries[0]['end'] == '12:00'
    assert any('Text-Fallback' in warning for warning in report['warnings'])
    assert any('ungerade Anzahl' in warning for warning in report['warnings'])


def test_pdf_parser_requires_glz_context(monkeypatch):
    page = FakePage(
        'Monat: Februar 2026',
        [[['03 DI Mobil 08:00 16:00 12,50']]],
    )
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, report = parse_pdf_content(object(), include_report=True)

    assert entries[0]['glz_override'] is None
    assert any('ohne GLZ-Kontext' in warning for warning in report['warnings'])


def test_pdf_parser_accepts_night_shift(monkeypatch):
    page = FakePage(
        'Monat: Februar 2026',
        [[['03 DI Mobil 22:00 02:00']]],
    )
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, report = parse_pdf_content(object(), include_report=True)

    assert entries[0]['type'] == 'home'
    assert entries[0]['start'] == '22:00'
    assert entries[0]['end'] == '02:00'
    assert not any('Endzeit vor Startzeit' in warning for warning in report['warnings'])


def test_merge_pdf_entries_adds_blocks_and_preserves_existing_data():
    existing = [
        SimpleNamespace(type='home', start_time='08:00', end_time='12:00', comment='Bestehend', glz_override=2.0),
        SimpleNamespace(type='office', start_time='13:00', end_time='17:00', comment='', glz_override=None),
    ]
    incoming = [
        {'type': 'home', 'start': '08:00', 'end': '12:00', 'comment': 'Neu', 'glz_override': 3.0},
        {'type': 'dr', 'start': '18:00', 'end': '22:00', 'comment': 'Reise', 'glz_override': 3.0},
    ]

    result = merge_pdf_entries(existing, incoming)

    assert result['skipped_duplicates'] == 1
    assert result['comment_hints'] == 1
    assert result['glz_override_conflicts'] == 2
    assert result['entries_to_add'] == [
        {'type': 'dr', 'start': '18:00', 'end': '22:00', 'comment': 'Reise', 'glz_override': None}
    ]
    assert existing[0].comment == 'Bestehend'

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

def test_shared_pdf_night_shift_cases():
    """Docker erhält Uhrzeiten an der Mitternachtsgrenze nach den gemeinsamen Fällen."""
    cases = json.loads(SHARED_NIGHT_SHIFT_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        assert pdf_times_from_row(case["row_text"]) == case["expected_times"], case["id"]


def test_pdf_night_shift_blocks_survive_parsing(monkeypatch):
    """Ein an Mitternacht endender Block bleibt bis in den Importdatensatz erhalten."""
    cases = {
        case["id"]: case
        for case in json.loads(SHARED_NIGHT_SHIFT_CASES.read_text(encoding="utf-8"))["cases"]
    }
    case = cases["night-shift-ending-at-midnight-is-kept"]
    page = FakePage('Monat: Februar 2026', [[[case["row_text"]]]])
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, report = parse_pdf_content(object(), include_report=True)

    assert len(entries) == 1
    assert (entries[0]['start'], entries[0]['end']) == tuple(case["expected_times"])
    assert not any('ungerade' in warning for warning in report['warnings'])


def test_pdf_placeholder_row_stays_discarded(monkeypatch):
    """Eine Zeile aus reinen Platzhaltern erzeugt weiterhin keinen Zeitblock."""
    cases = {
        case["id"]: case
        for case in json.loads(SHARED_NIGHT_SHIFT_CASES.read_text(encoding="utf-8"))["cases"]
    }
    case = cases["placeholder-only-row-is-discarded"]
    page = FakePage('Monat: Februar 2026', [[[case["row_text"]]]])
    monkeypatch.setattr('app.pdfplumber.open', lambda _file: FakeContentPdf([page]))

    entries, _report = parse_pdf_content(object(), include_report=True)

    assert [entry for entry in entries if entry['start'] or entry['end']] == []
