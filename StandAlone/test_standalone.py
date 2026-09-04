import json
import os
import re
from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

SHARED_BREAK_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "breaks.json"
SHARED_HOLIDAY_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "holidays.json"
SHARED_HOLIDAY_CALENDAR = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "holidays-calendar.json"
SHARED_IMPORT_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "json-import.json"
SHARED_INCOMPLETE_ENTRY_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "incomplete-entries.json"
SHARED_GLZ_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "glz.json"
SHARED_SERIES_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "series-planning.json"
SHARED_PDF_MERGE_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "pdf-merge.json"
SHARED_NIGHT_SHIFT_CASES = Path(__file__).resolve().parents[1] / "shared" / "test-cases" / "pdf-night-shifts.json"

BASE_URL = "http://localhost:8000/ho-planer.html"
PRIVATE_DIR = "testfiles"

# Aktionen liegen an genau einer Stelle: im Menü des Floating Action Buttons.
QUICK_ACTION_FAB = ".quick-action-fab"
QUICK_ACTION_ITEMS = ".v-menu .v-list-item"


def open_quick_actions(page: Page):
    """Öffnet das Aktionsmenü des FAB und liefert seine Einträge."""
    page.locator(QUICK_ACTION_FAB).click()
    items = page.locator(QUICK_ACTION_ITEMS)
    expect(items.first).to_be_visible()
    return items

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
    page.evaluate("""async () => {
        localStorage.clear();
        await new Promise((resolve, reject) => {
            const request = indexedDB.deleteDatabase('bbk_tracker_db');
            request.onsuccess = request.onerror = request.onblocked = () => resolve();
        });
    }""")
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


def test_shared_holiday_cases(page: Page):
    """Standalone erfüllt die zentral definierten Feiertags- und Wochenendfälle."""
    cases = json.loads(SHARED_HOLIDAY_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        result = page.evaluate("""testCase => {
            const date = new Date(`${testCase.date}T12:00:00`);
            window.vm.settings = {
                ...window.vm.settings,
                weekly_hours: testCase.weekly_hours,
                active_weekdays: testCase.active_weekdays,
                christmas_eve_and_new_years_eve_off: testCase.christmas_eve_and_new_years_eve_off !== false,
            };
            window.vm.customHolidays = testCase.custom_holiday
                ? { [testCase.date]: { date: testCase.date, ...testCase.custom_holiday } }
                : {};
            return window.vm.getDayInfo(date);
        }""", case)
        for field, expected in case["expected"].items():
            assert result[field] == expected, case["id"]


def test_shared_holiday_calendar_matches_reference(page: Page):
    """Der Feiertagshelper trifft den gemeinsamen Kalender über 21 Jahre."""
    calendar_doc = json.loads(SHARED_HOLIDAY_CALENDAR.read_text(encoding="utf-8"))
    expected_statutory = calendar_doc["statutory_holidays"]
    expected_year_end = calendar_doc["year_end_option"]["days_when_enabled"]

    found = page.evaluate("""({ from, to }) => {
        const withOption = {};
        const withoutOption = {};
        for (let year = from; year <= to; year++) {
            for (let month = 0; month < 12; month++) {
                const days = new Date(year, month + 1, 0).getDate();
                for (let day = 1; day <= days; day++) {
                    const dateObj = new Date(year, month, day);
                    const iso = toLocalIsoDate(dateObj);
                    const enabled = getHolidayName(dateObj, true);
                    if (enabled) withOption[iso] = enabled;
                    const disabled = getHolidayName(dateObj, false);
                    if (disabled) withoutOption[iso] = disabled;
                }
            }
        }
        return { withOption, withoutOption };
    }""", calendar_doc["years"])

    assert found["withOption"] == {**expected_statutory, **expected_year_end}
    assert found["withoutOption"] == expected_statutory


def test_year_end_option_switches_workday_and_target(page: Page):
    """Heiligabend und Silvester sind nur bei aktiver Jahresendoption arbeitsfrei."""
    calendar_doc = json.loads(SHARED_HOLIDAY_CALENDAR.read_text(encoding="utf-8"))

    for iso_date, expected_name in calendar_doc["year_end_option"]["days_when_enabled"].items():
        weekday = date.fromisoformat(iso_date).weekday()
        if weekday > 4:
            continue  # Am Wochenende trägt bereits der inaktive Wochentag die Freistellung.

        result = page.evaluate("""isoDate => {
            const dateObj = new Date(`${isoDate}T12:00:00`);
            const read = yearEndOff => {
                window.vm.settings = {
                    ...window.vm.settings,
                    weekly_hours: 39,
                    active_weekdays: [0, 1, 2, 3, 4],
                    christmas_eve_and_new_years_eve_off: yearEndOff,
                };
                window.vm.customHolidays = {};
                return window.vm.getDayInfo(dateObj);
            };
            return { enabled: read(true), disabled: read(false) };
        }""", iso_date)

        assert result["enabled"]["is_workday"] is False, iso_date
        assert result["enabled"]["target"] == 0.0, iso_date
        assert result["enabled"]["holiday_name"] == expected_name, iso_date
        assert result["disabled"]["is_workday"] is True, iso_date
        assert result["disabled"]["target"] == pytest.approx(39.0 / 5), iso_date


def test_standalone_settings_validation(page: Page):
    invalid = page.evaluate("""() => normalizeSettingsValues({
        weekly_hours: Infinity, ho_quota_percent: 60, active_weekdays: [0], default_start_time: '08:00'
    })""")
    assert "error" in invalid

    valid = page.evaluate("""() => normalizeSettingsValues({
        weekly_hours: 39, ho_quota_percent: 60, active_weekdays: [0, 1, 2, 3, 4], default_start_time: '8:00'
    })""")
    assert valid["settings"]["default_start_time"] == "08:00"


def test_standalone_theme_validation(page: Page):
    defaulted = page.evaluate("""() => normalizeSettingsValues({
        weekly_hours: 39, ho_quota_percent: 60, active_weekdays: [0, 1, 2, 3, 4], default_start_time: '08:00'
    })""")
    assert defaulted["settings"]["theme"] == "dark"

    light = page.evaluate("""() => normalizeSettingsValues({
        weekly_hours: 39, ho_quota_percent: 60, active_weekdays: [0, 1, 2, 3, 4], default_start_time: '08:00', theme: 'light'
    })""")
    assert light["settings"]["theme"] == "light"

    invalid = page.evaluate("""() => normalizeSettingsValues({
        weekly_hours: 39, ho_quota_percent: 60, active_weekdays: [0, 1, 2, 3, 4], default_start_time: '08:00', theme: 'blue'
    })""")
    assert "error" in invalid


def test_standalone_theme_persists_and_is_applied(page: Page):
    result = page.evaluate("""() => {
        window.vm.settings = { ...window.vm.settings, theme: 'light' };
        window.vm.saveSettings();
        return {
            applied: document.documentElement.dataset.theme,
            stored: JSON.parse(localStorage.getItem('bbk_data')).settings.theme,
        };
    }""")
    assert result == {"applied": "light", "stored": "light"}

    page.reload()
    assert page.locator("html").get_attribute("data-theme") == "light"


def test_standalone_custom_holiday_validation(page: Page):
    invalid = page.evaluate("() => normalizePortableHoliday({ date: '2024-02-30', name: '', hours: -1 })")
    assert invalid["error"] == "invalid_date"

    valid = page.evaluate("() => normalizePortableHoliday({ date: '2024-02-29', name: 'Sondertag', hours: 2 })")
    assert valid["holiday"] == {"date": "2024-02-29", "name": "Sondertag", "hours": 2}


def test_shared_series_planning_cases(page: Page):
    """Standalone plant ausschließlich an Arbeitstagen nach den gemeinsamen Referenzfällen."""
    cases = json.loads(SHARED_SERIES_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        result = page.evaluate("""testCase => {
            Store.set({
                settings: {
                    weekly_hours: testCase.weekly_hours,
                    active_weekdays: testCase.active_weekdays,
                    ho_quota_percent: 60,
                    hide_weekends: false,
                    default_start_time: '08:00',
                    auto_convert_planned: true,
                    christmas_eve_and_new_years_eve_off: true,
                },
                entries: {},
                customHolidays: testCase.custom_holiday
                    ? { [testCase.start]: { date: testCase.start, ...testCase.custom_holiday } }
                    : {},
            });
            window.vm.loadData();
            window.vm.seriesDialog = {
                show: false,
                start: testCase.start,
                end: testCase.end,
                weekdays: testCase.weekdays,
                type: testCase.type,
                overwrite: false,
            };
            window.vm.saveSeriesPlan();
            const previewEntries = JSON.parse(JSON.stringify(Store.getEntries()));
            const preview = window.vm.seriesPreview.data;
            window.vm.confirmSeriesPlan();
            const entries = Store.getEntries();
            const plannedDates = Object.keys(entries).filter(date => entries[date].length > 0).sort();
            const info = window.vm.getDayInfo(new Date(`${testCase.start}T12:00:00`));
            return { plannedDates, entries, previewEntries, preview, target: info.target };
        }""", case)
        assert result["plannedDates"] == case["expected"]["planned_dates"], case["id"]
        assert result["previewEntries"] == {}, case["id"]
        assert result["preview"]["created_dates"] == case["expected"]["planned_dates"], case["id"]
        if "target" in case["expected"]:
            assert result["target"] == case["expected"]["target"], case["id"]
            entry = result["entries"][case["start"]][0]
            assert entry["start"] == "08:00", case["id"]
            expected_end = page.evaluate("""target => {
                const minutes = 8 * 60 + calculateGrossTimeNeeded(target) * 60;
                return `${Math.floor(minutes / 60).toString().padStart(2, '0')}:${Math.round(minutes % 60).toString().padStart(2, '0')}`;
            }""", case["expected"]["target"])
            assert entry["end"] == expected_end, case["id"]


def test_series_plan_preview_and_confirm_are_atomic(page: Page):
    result = page.evaluate("""() => {
        Store.set({
            settings: { weekly_hours: 39, active_weekdays: [0, 1, 2, 3, 4], default_start_time: '08:00' },
            entries: { '2098-07-14': [{ type: 'vacation', start: '', end: '', comment: '' }] },
            customHolidays: {},
        });
        window.vm.loadData();
        const weekdays = ['2098-07-14', '2098-07-15'].map(value => (new Date(`${value}T12:00:00`).getDay() + 6) % 7);
        window.vm.seriesDialog = { show: true, start: '2098-07-14', end: '2098-07-15', weekdays, type: 'office', overwrite: false };
        let persistCount = 0;
        Store.onPersist = () => { persistCount += 1; };
        window.vm.saveSeriesPlan();
        const preview = window.vm.seriesPreview.data;
        const afterPreview = JSON.parse(JSON.stringify(Store.getEntries()));
        window.vm.seriesDialog.overwrite = true;
        window.vm.confirmSeriesPlan();
        return { preview, afterPreview, entries: Store.getEntries(), persistCount };
    }""")
    assert result["preview"]["skipped_existing_dates"] == ["2098-07-14"]
    assert result["preview"]["created_dates"] == ["2098-07-15"]
    assert result["afterPreview"] == {"2098-07-14": [{"type": "vacation", "start": "", "end": "", "comment": ""}]}
    assert result["persistCount"] == 1
    assert result["entries"]["2098-07-14"][0]["type"] == "office"
    assert result["entries"]["2098-07-15"][0]["type"] == "office"


def test_copy_or_move_plan_handles_conflicts_duplicates_glz_and_atomic_move(page: Page):
    result = page.evaluate("""() => {
        Store.set({ settings: {}, customHolidays: {}, entries: {
            '2098-07-14': [
                { type: 'home', start: '22:00', end: '02:00', comment: 'Nachtschicht', glz_override: 3, glz_override_source: 'manual' },
                { type: 'office', start: '08:00', end: '16:00', comment: 'Gleich', glz_override: null, glz_override_source: null },
            ],
            '2098-07-15': [
                { type: 'office', start: '08:00', end: '16:00', comment: 'Gleich', glz_override: null, glz_override_source: null },
                { type: 'vacation', start: '', end: '', comment: '', glz_override: 1, glz_override_source: 'manual' },
            ],
            '2098-07-16': [
                { type: 'sick', start: '', end: '', comment: 'Ersetzen', glz_override: null, glz_override_source: null },
            ],
        }});
        window.vm.loadData();
        let persistCount = 0;
        Store.onPersist = () => { persistCount += 1; };
        const payload = { source_date: '2098-07-14', target_date: '2098-07-15', operation: 'move', conflict_mode: 'cancel' };
        const conflict = window.vm.buildCopyOrMovePlan(payload);
        const beforeConfirm = JSON.parse(JSON.stringify(Store.getEntries()));
        const plan = window.vm.buildCopyOrMovePlan({ ...payload, conflict_mode: 'merge' });
        const beforeFinish = JSON.parse(JSON.stringify(Store.getEntries()));
        window.vm.finishTransfer(plan);
        const afterMove = Store.getEntries();
        const overwrite = window.vm.buildCopyOrMovePlan({ source_date: '2098-07-15', target_date: '2098-07-16', operation: 'copy', conflict_mode: 'overwrite' });
        const invalidConflictMode = (() => {
            try { window.vm.buildCopyOrMovePlan({ source_date: '2098-07-15', target_date: '2098-07-16', operation: 'copy', conflict_mode: 'invalid' }); return false; } catch (_) { return true; }
        })();
        const invalidOperation = (() => {
            try { window.vm.buildCopyOrMovePlan({ source_date: '2098-07-15', target_date: '2098-07-16', operation: 'invalid', conflict_mode: 'merge' }); return false; } catch (_) { return true; }
        })();
        return { conflict, beforeConfirm, beforeFinish, afterMove, persistCount, plan, overwrite, invalidConflictMode, invalidOperation };
    }""")
    assert result["conflict"]["conflict"] is True
    assert result["beforeConfirm"] == result["beforeFinish"]
    assert "2098-07-14" in result["beforeFinish"]
    assert "2098-07-14" not in result["afterMove"]
    assert result["persistCount"] == 1
    assert result["plan"]["copied_entries"] == 1
    assert result["plan"]["skipped_duplicates"] == 1
    assert result["plan"]["glz_override_conflicts"] == 1
    moved = next(entry for entry in result["afterMove"]["2098-07-15"] if entry["comment"] == "Nachtschicht")
    assert moved["start"] == "22:00" and moved["end"] == "02:00"
    assert moved["glz_override"] is None and moved["glz_override_source"] is None
    assert result["overwrite"]["replaced_entries"] == 1
    assert all(entry["type"] != "sick" for entry in result["overwrite"]["entries"]["2098-07-16"])
    assert result["invalidConflictMode"] is True
    assert result["invalidOperation"] is True


def test_series_plan_rejects_empty_type_without_persisting(page: Page):
    result = page.evaluate("""() => {
        Store.set({ settings: { weekly_hours: 39, active_weekdays: [0, 1, 2, 3, 4] }, entries: {}, customHolidays: {} });
        window.vm.loadData();
        let persistCount = 0;
        Store.onPersist = () => { persistCount += 1; };
        window.vm.seriesDialog = { show: true, start: '2098-07-14', end: '2098-07-14', weekdays: [1], type: '', overwrite: false };
        window.vm.saveSeriesPlan();
        return { entries: Store.getEntries(), persistCount, preview: window.vm.seriesPreview.data };
    }""")
    assert result["entries"] == {}
    assert result["persistCount"] == 0
    assert result["preview"] is None

    result = page.evaluate("""() => {
        window.vm.settings.default_start_time = '08:00';
        const day = { date: '2024-02-29', daily_target: 4, entries: [{ type: 'home', start: '', end: '' }] };
        window.vm.onEntryChange(day, day.entries[0]);
        return day.entries[0].end;
    }""")
    assert result == "12:00"


def test_glz_carryover_without_anchor_starts_at_first_target_year_entry(page: Page):
    case = next(item for item in json.loads(SHARED_GLZ_CASES.read_text(encoding="utf-8"))["cases"]
                if item["id"] == "no-anchor-starts-at-first-entry-in-target-year")
    result = page.evaluate("""testCase => {
        Store.set({ settings: { weekly_hours: 39, active_weekdays: [0, 1, 2, 3, 4] }, entries: {}, customHolidays: {} });
        Store.saveDayEntries(testCase.entries[0].date, [testCase.entries[0]]);
        window.vm.loadData();
        const calculatedDates = [];
        const originalGetDayInfo = window.vm.getDayInfo;
        window.vm.getDayInfo = date => {
            calculatedDates.push(toLocalIsoDate(date));
            return originalGetDayInfo.call(window.vm, date);
        };
        window.vm.getGlzCarryover(testCase.carryover_target.year, testCase.carryover_target.month);
        window.vm.getDayInfo = originalGetDayInfo;
        return calculatedDates[0];
    }""", case)
    assert result == case["expected_first_calculation_date"]


def test_shared_glz_carryover_cases(page: Page):
    """Standalone rechnet jeden gemeinsamen GLZ-Fall auf den erwarteten Saldo."""
    document = json.loads(SHARED_GLZ_CASES.read_text(encoding="utf-8"))

    for case in document["cases"]:
        result = page.evaluate("""({ testCase, evaluation }) => {
            const entries = {};
            for (const entry of testCase.entries) {
                (entries[entry.date] = entries[entry.date] || []).push(entry);
            }
            Store.set({
                settings: {
                    weekly_hours: evaluation.weekly_hours,
                    active_weekdays: evaluation.active_weekdays,
                    christmas_eve_and_new_years_eve_off: evaluation.christmas_eve_and_new_years_eve_off,
                },
                entries,
                customHolidays: {},
            });
            window.vm.loadData();
            const carryover = window.vm.getGlzCarryover(
                testCase.carryover_target.year, testCase.carryover_target.month);

            // Der Anker ist der Startwert der Fortschreibung und muss als solcher
            // gespeichert bleiben; sonst begaenne die Berechnung an anderer Stelle.
            let anchor = null;
            if (testCase.expected_anchor) {
                const stored = Store.getEntries()[testCase.expected_anchor.date] || [];
                const match = [...stored].reverse().find(entry => entry.glz_override != null);
                if (match) {
                    anchor = { value: match.glz_override, source: match.glz_override_source };
                }
            }
            return { carryover, anchor };
        }""", {"testCase": case, "evaluation": document["evaluation_settings"]})

        assert round(result["carryover"], 2) == case["expected_carryover"], case["id"]
        if "expected_anchor" in case:
            assert result["anchor"] is not None, case["id"]
            assert result["anchor"]["value"] == case["expected_anchor"]["value"], case["id"]
            assert result["anchor"]["source"] == case["expected_anchor"]["source"], case["id"]


def test_glz_carryover_uses_last_anchor_stored_on_same_day(page: Page):
    result = page.evaluate("""() => {
        Store.set({
            settings: { weekly_hours: 39, active_weekdays: [0, 1, 2, 3, 4] },
            entries: {
                '2098-04-30': [
                    { type: 'home', start: '', end: '', glz_override: 1.5, glz_override_source: 'manual' },
                    { type: 'office', start: '', end: '', glz_override: 4.0, glz_override_source: 'pdf' },
                ],
            },
            customHolidays: {},
        });
        window.vm.loadData();
        return window.vm.getGlzCarryover(2098, 5);
    }""")
    assert result == 4.0



def test_glz_carryover_without_entries_is_zero(page: Page):
    result = page.evaluate("""() => {
        Store.set({ settings: { weekly_hours: 39, active_weekdays: [0, 1, 2, 3, 4] }, entries: {}, customHolidays: {} });
        window.vm.loadData();
        return window.vm.getGlzCarryover(2024, 2);
    }""")
    assert result == 0.0


def test_browser_import_rejects_invalid_business_values(page: Page):
    payload = {
        "format": "ho-planer-export", "version": 1, "settings": {}, "custom_holidays": [],
        "entries": [
            {"date": "2024-02-30", "type": "home", "start": "", "end": ""},
            {"date": "2024-02-29", "type": "home", "start": "08:0", "end": "16:00"},
            {"date": "2024-02-29", "type": "home", "start": "08:00", "end": "16:00", "glz_override": "NaN"},
            {"date": "2024-02-29", "type": "home", "start": "08:00", "end": "16:00", "glz_override_source": "unknown"},
        ],
    }
    result = page.evaluate("payload => mergePortableExport(payload)", payload)
    assert result["invalid_entries"] == 4


def test_merge_portable_export_persists_only_real_changes(page: Page):
    result = page.evaluate("""() => {
        Store.set({ settings: {}, entries: {
            '2098-07-15': [{ type: 'home', start: '08:00', end: '16:30', comment: 'JSON-Test', glz_override: null, glz_override_source: null }]
        }, customHolidays: {} });
        let persistCount = 0;
        Store.onPersist = () => { persistCount += 1; };
        const payload = {
            format: 'ho-planer-export', version: 1, settings: {}, custom_holidays: [],
            entries: [{ date: '2098-07-15', type: 'home', start: '08:00', end: '16:30', comment: 'JSON-Test', glz_override: null, glz_override_source: null }]
        };
        const importResult = mergePortableExport(payload);
        Store.onPersist = null;
        return { changed: importResult.changed, persistCount };
    }""")
    assert result == {"changed": False, "persistCount": 0}


def test_shared_json_import_cases(page: Page):
    """Der Browser-Import erfüllt alle zentral definierten additiven Importfälle."""
    cases = json.loads(SHARED_IMPORT_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        page.evaluate("() => Store.set({ settings: {}, entries: {}, customHolidays: {} })")
        for entry in case["existing_entries"]:
            page.evaluate("entry => Store.saveDayEntries(entry.date, [{ ...entry }])", entry)
        if case.get("existing_custom_holidays"):
            page.evaluate(
                "holidays => { const data = Store.get(); data.customHolidays = { ...data.customHolidays, ...holidays }; Store.set(data); }",
                {holiday["date"]: {"date": holiday["date"], "name": holiday["name"], "hours": holiday.get("hours", 0)}
                 for holiday in case["existing_custom_holidays"]},
            )
        payload = {
            "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00Z",
            "settings": {},
            "custom_holidays": case.get("incoming_custom_holidays", []),
            "entries": case["incoming_entries"],
        }
        result = page.evaluate("payload => mergePortableExport(payload)", payload)
        assert result["imported_entries"] == case["expected"]["imported_entries"], case["id"]
        assert result["skipped_entries"] == case["expected"]["skipped_entries"], case["id"]
        if "invalid_entries" in case["expected"]:
            assert result["invalid_entries"] == case["expected"]["invalid_entries"], case["id"]
        # Sondertage: derselbe Zählername in beiden Varianten.
        if "imported_custom_holidays" in case["expected"]:
            assert result["imported_custom_holidays"] == case["expected"]["imported_custom_holidays"], case["id"]
        if "holiday_conflicts" in case["expected"]:
            assert result["holiday_conflicts"] == case["expected"]["holiday_conflicts"], case["id"]
        if "details" in case["expected"]:
            assert result["details"] == case["expected"]["details"], case["id"]


def test_shared_pdf_merge_cases(page: Page):
    """Standalone erfüllt die gemeinsamen Regeln zum additiven PDF-Blockmerge."""
    cases = json.loads(SHARED_PDF_MERGE_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        result = page.evaluate("""testCase => mergePdfEntries(
            testCase.existing_entries,
            testCase.pdf_entries.map(entry => ({ ...entry, glz_override_source: entry.glz_override === null ? null : 'pdf' })),
        )""", case)
        expected = case["expected"]
        assert result["imported_entries"] == expected["imported_entries"], case["id"]
        for field in ("skipped_duplicates", "comment_hints", "glz_override_conflicts"):
            assert result[field] == expected[field], case["id"]
        added_entries = result["entries"][len(case["existing_entries"]):]
        assert added_entries == [
            {**entry, "glz_override_source": None if entry["glz_override"] is None else "pdf"}
            for entry in expected["added_entries"]
        ], case["id"]
        if "existing_comments" in expected:
            assert [entry["comment"] for entry in result["entries"][:len(case["existing_entries"])]] == expected["existing_comments"], case["id"]


def test_shared_pdf_night_shift_cases(page: Page):
    """Standalone erhält Uhrzeiten an der Mitternachtsgrenze nach den gemeinsamen Fällen."""
    cases = json.loads(SHARED_NIGHT_SHIFT_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        result = page.evaluate("rowText => pdfTimesFromRow(rowText)", case["row_text"])
        assert result == case["expected_times"], case["id"]


def test_shared_glz_anchor_round_trip(page: Page):
    """GLZ-Anker behalten beim Browser-Export und -Import Wert sowie Quelle."""
    cases = json.loads(SHARED_GLZ_CASES.read_text(encoding="utf-8"))["cases"]
    # Zwei Referenzfälle enthalten bewusst keinen Anker: ohne Anker beginnt die
    # Berechnung beim ersten Eintrag des Zieljahres. Geprüft wird das in
    # test_glz_carryover_without_anchor_starts_at_first_target_year_entry;
    # hier zählen nur die Ankerfälle.
    anchor_cases = [case for case in cases if "expected_anchor" in case]
    assert len(anchor_cases) == 3, "Die Ankerfälle der gemeinsamen Referenzdatei fehlen."

    for case in anchor_cases:
        page.evaluate("() => Store.set({ settings: {}, entries: {}, customHolidays: {} })")
        payload = {
            "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00Z",
            "settings": {}, "custom_holidays": [], "entries": case["entries"],
        }
        page.evaluate("payload => mergePortableExport(payload)", payload)
        exported = page.evaluate("() => buildPortableExport()")
        anchor = case["expected_anchor"]
        exported_anchor = next(entry for entry in exported["entries"] if entry["date"] == anchor["date"] and entry["glz_override"] == anchor["value"])
        assert exported_anchor["glz_override_source"] == anchor["source"], case["id"]


def test_shared_incomplete_entry_cases(page: Page):
    """Standalone erfüllt alle zentral definierten Regeln für unvollständige Einträge."""
    cases = json.loads(SHARED_INCOMPLETE_ENTRY_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        is_future = case["relative_day"] == "future"
        result = page.evaluate(
            """({ entry, target, isFuture }) => calculateTotalDailyNet([entry], target, isFuture)""",
            {"entry": {"type": case["type"], "start": "", "end": ""}, "target": 7.8, "isFuture": is_future},
        )
        expected = 7.8 if case["expected_mode"] == "target" else 0
        assert result == expected, case["id"]


# --- GUI TESTS (V2 UI) ---
def test_unfinished_actual_entries_count_only_for_future_days(page: Page):
    """Heute ist ein Ist-Tag; nur zukünftige unvollständige Ist-Einträge erhalten Sollzeit."""
    dates = page.evaluate("""() => {
        const today = new Date();
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        return { today: toLocalIsoDate(today), tomorrow: toLocalIsoDate(tomorrow) };
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

def test_add_custom_holiday_rejects_invalid_input_before_persisting(page: Page):
    result = page.evaluate("""() => {
        window.vm.customHolidays = {};
        window.vm.newCustomHoliday = { _oldDate: null, date: '2024-02-30', name: 'Ungültig', hours: 0 };
        window.vm.addCustomHoliday();
        const invalidDateRejected = Object.keys(window.vm.customHolidays).length === 0;

        window.vm.newCustomHoliday = { _oldDate: null, date: '2024-02-29', name: '  ', hours: 0 };
        window.vm.addCustomHoliday();
        const emptyNameRejected = Object.keys(window.vm.customHolidays).length === 0;

        window.vm.newCustomHoliday = { _oldDate: null, date: '2024-02-29', name: 'Testtag', hours: -1 };
        window.vm.addCustomHoliday();
        const negativeHoursRejected = Object.keys(window.vm.customHolidays).length === 0;

        window.vm.newCustomHoliday = { _oldDate: null, date: '2024-02-29', name: 'Testtag', hours: 4 };
        window.vm.addCustomHoliday();
        return { invalidDateRejected, emptyNameRejected, negativeHoursRejected, saved: window.vm.customHolidays['2024-02-29'] };
    }""")
    assert result == {
        "invalidDateRejected": True,
        "emptyNameRejected": True,
        "negativeHoursRejected": True,
        "saved": {"date": "2024-02-29", "name": "Testtag", "hours": 4},
    }


def test_v2_gui_settings_custom_holiday(page: Page):
    # Einstellungen über das Aktionsmenü öffnen
    open_quick_actions(page).filter(has_text="Einstellungen").click()
    today = page.evaluate("toLocalIsoDate(new Date())")
    
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
    # Jahresansicht: Monatstabelle mit den vier Kennzahlen und Balkendiagramm
    expect(page.locator("th").filter(has_text="Homeoffice-Quote")).to_be_visible()
    expect(page.locator("th").filter(has_text="Planung")).to_be_visible()
    expect(page.locator("canvas#barChart")).to_be_attached()
    
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

# --- Angleichung an die Docker-Oberfläche -------------------------------

def test_kopfzeile_enthält_keine_doppelten_aktionen(page: Page):
    """Die Kopfzeile trägt Orientierung, nicht die Aktionen."""
    app_bar = page.locator(".v-app-bar")
    for label in ("PDF", "Serien", "Einstellungen", "Aktionen öffnen"):
        expect(app_bar.locator(f"[title*='{label}']")).to_have_count(0)

    # Speicherstatus und Farbschema bleiben sichtbar
    expect(app_bar.locator("[title*='Farbschema']")).to_be_visible()
    expect(page.locator(".v-app-bar .dot")).to_be_visible()


def test_aktionsmenü_bietet_jede_aktion_einmal(page: Page):
    actions = open_quick_actions(page)
    for label in ("Tag erfassen", "Serienplanung", "PDF importieren", "JSON importieren", "JSON exportieren", "Einstellungen"):
        expect(actions.filter(has_text=label)).to_be_visible()
    expect(actions).to_have_count(6)


def test_drawer_ist_gegliedert(page: Page):
    page.locator("button[aria-label='Navigation öffnen']").click()
    drawer = page.locator(".v-navigation-drawer")
    expect(drawer).to_be_visible()
    for group in ("Ansichten", "Erfassen & planen", "Daten", "Darstellung & System"):
        expect(drawer.locator(".v-list-subheader").filter(has_text=group)).to_be_visible()
    expect(drawer.locator(".v-list-item").filter(has_text="Datei öffnen/anlegen")).to_be_visible()


def test_theme_umschalter_wechselt_und_bleibt(page: Page):
    first = page.evaluate("() => document.documentElement.dataset.theme")
    page.locator(".v-app-bar button[aria-label*='Farbschema']").click()
    second = page.evaluate("() => document.documentElement.dataset.theme")
    assert second in ("light", "dark")
    assert second != first
    assert page.evaluate("() => Store.getSettings().theme") == second


def test_mobile_tageskarte_ist_das_bedienelement(page: Page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    page.wait_for_timeout(800)

    expect(page.locator(".tl-day-edit")).to_have_count(0)
    card = page.locator(".tl-day-card").first
    expect(card).to_have_attribute("role", "button")
    card.locator(".tl-date-cell").first.click()
    expect(page.locator(".v-dialog .v-card").first).to_be_visible()


# --- Wochenkopf ---------------------------------------------------------

def test_wochenkopf_steht_vor_seinen_tagen(page: Page):
    """Die Zusammenfassung eröffnet die Woche, statt sie abzuschließen."""
    blocks = []
    for item in page.evaluate("() => window.vm.items"):
        if item["row_type"] == "summary":
            blocks.append({"week": item["iso_week"], "dates": []})
        elif blocks:
            blocks[-1]["dates"].append(item["date"])

    assert len(blocks) >= 4, "Der Monat muss mehrere Wochenköpfe enthalten."
    for block in blocks:
        assert block["dates"], f"KW {block['week']} hat keine Tage"
        for date_str in block["dates"]:
            iso = page.evaluate("d => { const x = new Date(d + 'T12:00:00'); return getISOWeek(x); }", date_str)
            assert iso == block["week"], date_str


def test_wochenkopf_über_den_tagen(page: Page):
    page.evaluate("() => { window.vm.loadData(); }")
    page.wait_for_timeout(500)
    header = page.locator(".tl-week-sum").first
    expect(header).to_be_visible()
    assert header.bounding_box()["y"] < page.locator(".tl-day-card").first.bounding_box()["y"]

    expect(header.locator(".tl-week-sum__week")).to_contain_text("KW")
    expect(header.locator(".tl-week-sum__hours")).to_contain_text("von")


def test_wochenkopf_bleibt_beim_scrollen_sichtbar(page: Page):
    page.evaluate("() => { window.vm.loadData(); }")
    page.wait_for_timeout(500)
    header = page.locator(".tl-week-sum").first
    expect(header).to_be_visible()

    page.mouse.wheel(0, 500)
    page.wait_for_timeout(500)
    box = header.bounding_box()
    assert box["y"] > 0, "Der Kopf ist beim Scrollen aus dem Blickfeld gewandert."
    assert box["y"] < 200, "Der Kopf klebt nicht unter der Kopfzeile."


def test_wochenköpfe_stapeln_sicht_nicht(page: Page):
    """Köpfe dürfen nicht gleichzeitig auf derselben Höhe kleben.

    Ohne eigenen Abschnitt pro Woche sammeln sich alle Köpfe an derselben
    Klebeposition und überdecken sich gegenseitig.
    """
    # Erst warten, bis die Timeline steht: sonst ist die Dokumenthöhe noch die
    # der leeren Seite und der Scroll-Wert damit wirkungslos.
    expect(page.locator(".tl-week").first).to_be_visible()
    # Nicht nur eine Position: die Dokumenthöhe hängt von Daten und Einstellungen
    # ab, deshalb wird über den ganzen Scrollbereich geprüft.
    hoehe = page.evaluate("() => window.innerHeight")
    for anteil in (0, 0.25, 0.5, 0.75, 1.0):
        page.evaluate(f"() => window.scrollTo(0, Math.round(document.documentElement.scrollHeight * {anteil}))")
        page.wait_for_timeout(250)
        tops = page.evaluate(
            "() => [...document.querySelectorAll('.tl-week-sum')]"
            ".map(h => Math.round(h.getBoundingClientRect().top))"
        )
        # Der Fehler, den der Wochenblock behebt: kein Kopf darf auf der Höhe
        # eines anderen kleben.
        assert len(set(tops)) == len(tops), f"Zwei Köpfe auf derselben Höhe: {tops}"
        # Beim Übergang von einem Block zum nächsten sitzt der folgende Kopf
        # kurz zwischen Klebe- und Normalposition - entscheidend ist, dass
        # oben immer Orientierung steht.
        assert any(40 <= top <= hoehe for top in tops), f"Kein Kopf sichtbar: {tops}"


def test_jede_woche_bildet_einen_block(page: Page):
    """Variante C: Rahmen fasst Kopf und Tage einer Woche zusammen."""
    page.evaluate("() => { window.vm.loadData(); }")
    expect(page.locator(".tl-week").first).to_be_visible()
    blocks = page.evaluate(
        "() => [...document.querySelectorAll('.tl-week')].map(b => ({"
        "  kopf: b.querySelector('.tl-week-sum') ? b.querySelector('.tl-week-sum').innerText.trim().split('\\n')[0] : null,"
        "  tage: [...b.querySelectorAll('.tl-day-card')].map(c => c.dataset.kw),"
        "}))"
    )
    assert len(blocks) >= 4, "Der Monat muss mehrere Wochenblöcke enthalten."
    for block in blocks:
        assert block["kopf"] and block["kopf"].startswith("KW ")
        woche = block["kopf"].split()[1]
        assert block["tage"], f"{block['kopf']} enthält keine Tage"
        assert set(block["tage"]) == {woche}, f"Block {woche} enthält fremde Tage: {block['tage']}"


def test_jeder_tag_trägt_seine_kalenderwoche(page: Page):
    """Variante B: die Kalenderwoche ist Merkmal des Tages, nicht nur des Kopfes."""
    page.evaluate("() => { window.vm.loadData(); }")
    expect(page.locator(".tl-week").first).to_be_visible()
    for anteil in (0, 0.25, 0.5, 0.75, 1.0):
        page.evaluate(f"() => window.scrollTo(0, Math.round(document.documentElement.scrollHeight * {anteil}))")
        page.wait_for_timeout(250)
        zeilen = page.evaluate(
            "() => [...document.querySelectorAll('.tl-day-card')]"
            ".filter(c => { const r = c.getBoundingClientRect(); return r.bottom > 130 && r.top < window.innerHeight - 60; })"
            ".map(c => c.dataset.kw + '|' + (c.querySelector('.tl-date-kw') ? c.querySelector('.tl-date-kw').textContent.trim() : ''))"
        )
        assert zeilen, f"Keine Tageszeile sichtbar bei Scroll-Anteil {anteil}"
        for zeile in zeilen:
            woche, text = zeile.split("|")
            assert text == f"KW {woche}", f"KW-Merkmal falsch oder fehlend: {zeile!r}"
