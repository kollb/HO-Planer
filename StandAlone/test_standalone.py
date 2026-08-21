import pytest
import json
import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

SHARED_BREAK_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "breaks.json"
SHARED_HOLIDAY_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "holidays.json"
SHARED_IMPORT_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "json-import.json"

BASE_URL = "http://localhost:8000/ho-planer.html"
PRIVATE_DIR = "testfiles"

# --- FIXTURES ---
@pytest.fixture(autouse=True)
def setup_viewport(page: Page):
    """Zwingt Playwright in eine Desktop-Auflösung (1280x800), damit keine UI-Elemente responsive ausgeblendet werden."""
    page.set_viewport_size({"width": 1280, "height": 800})
    yield

@pytest.fixture(autouse=True)
def clean_storage(page: Page):
    """Löscht vor jedem Test den LocalStorage, um mit einem frischen Zustand zu starten."""
    page.goto(BASE_URL)
    page.evaluate("localStorage.clear()")
    page.reload()
    yield

# --- LOGIK TESTS (JS Funktionen) ---
def test_js_normalize_time_input(page: Page):
    test_cases = [("830", "08:30"), ("08:00", "08:00"), ("9", "09:00"), ("2400", None)]
    for inp, expected in test_cases:
        result = page.evaluate(f"normalizeTimeInput('{inp}')")
        assert result == expected if expected else result is None

def test_js_calculate_net_hours(page: Page):
    test_cases = [
        ("08:00", "12:00", 4.0),
        ("08:00", "14:00", 6.0),
        ("08:00", "14:05", 6.0),   
        ("08:00", "14:30", 6.0),   
        ("08:00", "15:00", 6.5),   
        ("08:00", "17:00", 8.5),   
        ("08:00", "17:35", 9.0),   
        ("08:00", "18:00", 9.25),  
    ]
    for start, end, expected in test_cases:
        result = page.evaluate(f"calculateNetHours('{start}', '{end}')")
        assert abs(result - expected) < 0.01

def test_shared_break_cases(page: Page):
    """Standalone erfüllt dieselben zentral definierten Pausenfälle wie Docker."""
    cases = json.loads(SHARED_BREAK_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        result = page.evaluate("entries => calculateTotalDailyNet(entries)", case["entries"])
        assert result == case["expected_net_hours"], case["id"]


def test_statutory_holiday_overrides_custom_holiday(page: Page):
    """Gesetzliche Feiertage haben Vorrang vor eigenen Sondertagen."""
    result = page.evaluate("""() => {
        window.vm.customHolidays = {
            '2023-12-25': { date: '2023-12-25', name: 'Wäldchestag', hours: 6.0 }
        };
        return window.vm.getDayInfo(new Date(2023, 11, 25));
    }""")

    assert result['is_workday'] is False
    assert result['target'] == 0
    assert result['holiday_name'] == '1. Weihnachtstag'
    assert result['is_short_day'] is False


def test_portable_json_import_is_additive(page: Page):
    """Der gemeinsame JSON-Import erfüllt den zentral definierten additiven Referenzfall."""
    case = json.loads(SHARED_IMPORT_CASES.read_text(encoding="utf-8"))["cases"][0]
    payload = {
        "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00Z",
        "settings": {}, "custom_holidays": [], "entries": case["incoming_entries"],
    }
    first = page.evaluate("payload => mergePortableExport(payload)", payload)
    second = page.evaluate("payload => mergePortableExport(payload)", payload)
    stored = page.evaluate("() => Store.getEntries()['2098-07-15']")
    assert first['imported_entries'] == case["expected"]["imported_entries"]
    assert first['skipped_entries'] == case["expected"]["skipped_entries"]
    assert second['skipped_entries'] == 1
    assert len(stored) == 1


# --- GUI TESTS (V2 UI) ---
def test_unfinished_actual_entries_count_only_for_future_days(page: Page):
    """Heute ist ein Ist-Tag; nur zukünftige unvollständige Ist-Einträge erhalten Sollzeit."""
    dates = page.evaluate("""() => {
        const today = new Date();
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        const toYmd = value => value.toISOString().split('T')[0];
        return { today: toYmd(today), tomorrow: toYmd(tomorrow) };
    }""")

    page.evaluate("""({ today, tomorrow }) => {
        localStorage.setItem('bbk_data', JSON.stringify({
            settings: {
                weekly_hours: 39,
                active_weekdays: [0, 1, 2, 3, 4],
                ho_quota_percent: 60,
                hide_weekends: false,
                default_start_time: '08:00',
                auto_convert_planned: true
            },
            entries: {
                [today]: [
                    { type: 'home', start: '', end: '', comment: '' },
                    { type: 'dr', start: '', end: '', comment: '' }
                ],
                [tomorrow]: [{ type: 'office', start: '', end: '', comment: '' }]
            },
            customHolidays: {}
        }));
    }""", dates)
    page.reload()

    result = page.evaluate("""({ today, tomorrow }) => {
        const dayItems = Object.fromEntries(
            window.vm.items.filter(item => item.row_type === 'day').map(item => [item.date, item])
        );
        return {
            todayNet: dayItems[today].total_net,
            tomorrowNet: dayItems[tomorrow].total_net,
            tomorrowTarget: dayItems[tomorrow].daily_target
        };
    }""", dates)

    assert result['todayNet'] == 0
    assert result['tomorrowNet'] == result['tomorrowTarget']

# --- GUI TESTS (V2 UI) ---
def test_v2_gui_create_standard_entry(page: Page):
    """Testet das Inline-Editing der V2 Timeline."""
    # Erste Zeile in der Timeline greifen
    row = page.locator(".tl-row").first
    
    # Status auf Büro setzen
    row.locator("select.hover-select").select_option(value="office")
    
    # GLZ Override Feld füllen
    override_input = row.locator(".glz-input").first
    expect(override_input).to_be_visible()
    override_input.fill("12.5")
    override_input.press("Tab") # Change-Event auslösen
    
    # Prüfen, ob die Formatierung greift (+12,50)
    expect(override_input).to_have_value("+12,50")

def test_v2_gui_split_entry(page: Page):
    """Prüft, ob der Split-Button eine neue Zeile erzeugt."""
    # Greife den Wrapper für den heutigen Tag
    day_container = page.locator(".position-relative").first
    
    initial_count = day_container.locator(".tl-row").count()
    
    # Klick auf das Plus-Icon für diesen Tag
    day_container.locator(".mdi-plus-circle").first.click()
    
    # Zählen, ob eine neue Zeile dazu kam
    new_count = day_container.locator(".tl-row").count()
    assert new_count == initial_count + 1

def test_v2_gui_settings_custom_holiday(page: Page):
    # Einstellungen über das Icon in der Kopfzeile öffnen
    page.locator("button[title='Einstellungen']").click()
    today = page.evaluate("new Date().toISOString().split('T')[0]")
    
    dialog = page.locator(".v-dialog .v-card").filter(has_text="Einstellungen")
    expect(dialog).to_be_visible()

    dialog.locator("input[type='date']").first.fill(today)
    page.get_by_label("Bez.").fill("TestFeiertag")
    page.get_by_label("Std.").fill("0")
    
    dialog.locator(".mdi-content-save").locator("..").click()
    expect(dialog.get_by_text("TestFeiertag").first).to_be_visible()
    
    dialog.locator("div.d-flex.align-center").filter(has_text="TestFeiertag").locator(".mdi-pencil").click()
    page.get_by_label("Bez.").fill("Geändert")
    dialog.locator(".mdi-content-save").locator("..").click()
    
    expect(dialog.get_by_text("Geändert").first).to_be_visible()
    
    page.get_by_text("Speichern & Schließen").click()
    expect(dialog).not_to_be_visible()

def test_v2_gui_switch_views(page: Page):
    # Bento-Grid prüfen
    expect(page.locator(".bento-grid").first).to_be_visible()
    
    page.locator(".view-btn").filter(has_text="Jahr").click()
    expect(page.locator("th").filter(has_text="Urlaub")).to_be_visible()
    expect(page.locator("canvas#donutChart")).to_be_attached()
    
    page.locator(".view-btn").filter(has_text="Timeline").click()
    expect(page.locator(".tl-panel").first).to_be_visible()

def test_v2_gui_pdf_import_dialog_check(page: Page):
    pdf_path = os.path.join(PRIVATE_DIR, "standard.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Private PDF fehlt.")

    page.goto(BASE_URL)
    page.locator('input[type="file"][accept=".pdf"]').set_input_files(pdf_path)
    expect(page.get_by_text("PDF Import (Lokal)")).to_be_visible()

def test_v2_pdf_import_standard_month(page: Page):
    pdf_path = os.path.join(PRIVATE_DIR, "standard.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Private PDF 'standard.pdf' nicht gefunden.")

    page.goto(BASE_URL)
    page.locator('input[type="file"][accept=".pdf"]').set_input_files(pdf_path)

    page.get_by_text("Import starten").click()
    expect(page.locator(".v-snackbar__content")).to_contain_text("importiert")

    # Auf Juni 2025 navigieren (Monat 5 in JS = Juni)
    page.evaluate("window.vm.currentDate = new Date(2025, 5, 1); window.vm.loadMonthData();")
    
    # Zeile für den 2. Juni suchen
    row = page.locator(".position-relative").filter(has_text=re.compile(r"^2\.")).first
    expect(row).to_contain_text("Mo")
    
    # Werte prüfen
    expect(row.locator("select")).to_have_value("home")
    
    # GEFIXT: Sucht jetzt nach den neuen Text-Platzhaltern "Start" und "Ende"
    expect(row.locator("input[placeholder='Start']")).to_have_value("07:40")
    expect(row.locator("input[placeholder='Ende']")).to_have_value("16:30")

def test_v2_pdf_import_missing_booking(page: Page):
    pdf_path = os.path.join(PRIVATE_DIR, "error.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Private PDF 'error.pdf' nicht gefunden.")

    page.goto(BASE_URL)
    page.locator('input[type="file"][accept=".pdf"]').set_input_files(pdf_path)
    
    page.get_by_text("Import starten").click()
    expect(page.locator(".v-snackbar__content")).to_contain_text("importiert")

    # Auf Februar 2026 navigieren (Monat 1 in JS = Februar)
    page.evaluate("window.vm.currentDate = new Date(2026, 1, 1); window.vm.loadMonthData();")

    # Zeile für den 13. Februar suchen
    row = page.locator(".position-relative").filter(has_text=re.compile(r"^13\.")).first
    expect(row).to_contain_text("Fr")
    
    # Neues Wording prüfen
    comment_field = row.locator("input[placeholder='Notiz...']")
    expect(comment_field).to_have_value(re.compile("Fehlt im PDF", re.IGNORECASE))