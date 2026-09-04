import pytest
import json
from pathlib import Path
from datetime import date, timedelta
from types import SimpleNamespace
import io

from app import (
    app, db, Settings, WorkEntry, CustomHoliday, get_glz_carryover,
    get_local_now, merge_pdf_entries, parse_pdf_content,
)

SHARED_IMPORT_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "json-import.json"
SHARED_INCOMPLETE_ENTRY_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "incomplete-entries.json"
SHARED_GLZ_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "glz.json"
SHARED_SERIES_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "series-planning.json"
SHARED_PDF_MERGE_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "pdf-merge.json"

@pytest.fixture
def client():
    app.config['TESTING'] = True

    def reset_database():
        with app.app_context():
            WorkEntry.query.delete()
            CustomHoliday.query.delete()
            Settings.query.delete()
            db.session.add(Settings())
            db.session.commit()

    # Jeder API-Test startet unabhängig von Reihenfolge oder fehlgeschlagenem Vorgänger.
    # Der Teststarter setzt HO_PLANER_DATA_DIR zusätzlich auf ein temporäres Verzeichnis.
    reset_database()
    with app.test_client() as client:
        yield client
    reset_database()

def test_index_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"HO Planer" in response.data


def test_pdf_import_requires_file(client):
    response = client.post('/api/import/pdf')
    assert response.status_code == 400


def test_pdf_import_rejects_non_pdf_content(client):
    response = client.post(
        '/api/import/pdf',
        data={'file': (io.BytesIO(b'not a PDF'), 'test.pdf')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400


def test_pdf_import_requires_pdf_extension(client):
    response = client.post(
        '/api/import/pdf',
        data={'file': (io.BytesIO(b'%PDF-'), 'test.txt')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400


def test_pdf_parser_keeps_overnight_time_range(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Monat: Juli 2098\n15 MO Mobil 22:00 02:00"

        def extract_tables(self):
            return []

    class FakePdf:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.pdfplumber.open", lambda _file: FakePdf())

    entries, report = parse_pdf_content(io.BytesIO(b"%PDF- fake"), include_report=True)

    assert report["importable_entries"] == 1
    assert entries == [{
        "date": date(2098, 7, 15), "type": "home", "start": "22:00", "end": "02:00",
        "comment": "", "glz_override": None,
    }]


def test_pdf_parser_warns_about_unknown_status(monkeypatch):
    class FakePage:
        def extract_text(self):
            return "Monat: Juli 2098\n16 DI Unbekannt 08:00 16:00"

        def extract_tables(self):
            return []

    class FakePdf:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.pdfplumber.open", lambda _file: FakePdf())

    entries, report = parse_pdf_content(io.BytesIO(b"%PDF- fake"), include_report=True)

    assert entries[0]["comment"] == "⚠️ PDF-Prüfung erforderlich: unbekannter Status"
    assert "Tag 16: unbekannter Status; Zeiten als Prüfeintrag übernommen." in report["warnings"]


def test_pdf_import_merges_fake_parser_entries(client, monkeypatch):
    import_date = "2098-07-15"
    existing = WorkEntry(
        date=import_date, type="home", start_time="08:00", end_time="12:00",
        comment="Bestehend", glz_override=2.0, glz_override_source="manual",
    )
    with app.app_context():
        db.session.add(existing)
        db.session.commit()

    def fake_parse_pdf_content(_file, include_report=False):
        entries = [
            {"date": date(2098, 7, 15), "type": "home", "start": "08:00", "end": "12:00", "comment": "Neu", "glz_override": 3.0},
            {"date": date(2098, 7, 15), "type": "dr", "start": "22:00", "end": "02:00", "comment": "Nachtschicht", "glz_override": 3.0},
        ]
        report = {"pages": 1, "warnings": []}
        return (entries, report) if include_report else entries

    monkeypatch.setattr("app.parse_pdf_content", fake_parse_pdf_content)
    try:
        response = client.post(
            "/api/import/pdf",
            data={"file": (io.BytesIO(b"%PDF- fake"), "nachweis.pdf")},
            content_type="multipart/form-data",
        )
        result = response.get_json()
        assert response.status_code == 200
        assert result["imported_entries"] == 1
        assert result["skipped_duplicates"] == 1
        assert result["comment_hints"] == 1
        assert result["glz_override_conflicts"] == 2

        with app.app_context():
            saved = WorkEntry.query.filter_by(date=import_date).order_by(WorkEntry.id).all()
            assert [(entry.type, entry.start_time, entry.end_time, entry.comment, entry.glz_override) for entry in saved] == [
                ("home", "08:00", "12:00", "Bestehend", 2.0),
                ("dr", "22:00", "02:00", "Nachtschicht", None),
            ]
    finally:
        with app.app_context():
            WorkEntry.query.filter_by(date=import_date).delete()
            db.session.commit()


@pytest.mark.parametrize("endpoint", [
    "/api/entry",
    "/api/settings",
    "/api/custom-holidays",
    "/api/plan/series",
])
@pytest.mark.parametrize("payload", [[], "invalid", None])
def test_writing_endpoints_reject_non_object_json_bodies(client, endpoint, payload):
    response = client.post(
        endpoint,
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_get_settings(client):
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert "weekly_hours" in response.get_json()


@pytest.mark.parametrize('payload', [
    [],
    {"weekly_hours": "NaN"},
    {"weekly_hours": 0},
    {"ho_quota_percent": 101},
    {"active_weekdays": []},
    {"active_weekdays": [0, 0]},
    {"active_weekdays": [True]},
    {"default_start_time": "25:00"},
    {"hide_weekends": "maybe"},
    {"theme": "blue"},
    {"theme": True},
])
def test_settings_rejects_invalid_values(client, payload):
    assert client.post('/api/settings', json=payload).status_code == 400


def test_settings_normalizes_boolean_strings(client):
    response = client.post('/api/settings', json={
        "weekly_hours": 39,
        "ho_quota_percent": 60,
        "active_weekdays": [0, 1, 2, 3, 4],
        "default_start_time": "8:00",
        "hide_weekends": "false",
        "auto_convert_planned": "true",
    })
    assert response.status_code == 200
    settings = client.get('/api/settings').get_json()
    assert settings["default_start_time"] == "08:00"
    assert settings["hide_weekends"] is False
    assert settings["auto_convert_planned"] is True


def test_settings_defaults_and_saves_year_end_option(client):
    assert client.get('/api/settings').get_json()["christmas_eve_and_new_years_eve_off"] is True
    response = client.post('/api/settings', json={
        "weekly_hours": 39, "ho_quota_percent": 60, "active_weekdays": [0, 1, 2, 3, 4],
        "default_start_time": "08:00", "hide_weekends": False, "auto_convert_planned": True,
        "christmas_eve_and_new_years_eve_off": False,
    })
    assert response.status_code == 200
    assert client.get('/api/settings').get_json()["christmas_eve_and_new_years_eve_off"] is False


def test_settings_defaults_and_saves_theme(client):
    assert client.get('/api/settings').get_json()["theme"] == "dark"
    response = client.post('/api/settings', json={"theme": "light"})
    assert response.status_code == 200
    assert client.get('/api/settings').get_json()["theme"] == "light"


@pytest.mark.parametrize('payload', [
    [],
    {"start": "2024-02-01", "end": "2024-02-02", "weekdays": [0], "type": "home", "overwrite": "maybe"},
    {"start": "2024-02-02", "end": "2024-02-01", "weekdays": [0], "type": "home"},
    {"start": "2024-02-01", "end": "2024-02-02", "weekdays": [], "type": "home"},
    {"start": "2024-02-01", "end": "2024-02-02", "weekdays": [True], "type": "home"},
    {"start": "2024-02-01", "end": "2024-02-02", "weekdays": [0], "type": ""},
])
@pytest.mark.parametrize('endpoint', ['/api/plan/series', '/api/plan/series/preview'])
def test_series_plan_rejects_invalid_values(client, endpoint, payload):
    assert client.post(endpoint, json=payload).status_code == 400


def test_shared_series_planning_cases(client):
    """Docker plant ausschließlich an Arbeitstagen nach den gemeinsamen Referenzfällen."""
    cases = json.loads(SHARED_SERIES_CASES.read_text(encoding="utf-8"))["cases"]
    dates = {date for case in cases for date in (case["start"], case["end"])}
    try:
        for case in cases:
            with app.app_context():
                WorkEntry.query.filter(WorkEntry.date.in_([case["start"], case["end"]])).delete(synchronize_session=False)
                CustomHoliday.query.filter(CustomHoliday.date.in_([case["start"], case["end"]])).delete(synchronize_session=False)
                db.session.commit()

            settings_response = client.post('/api/settings', json={
                "weekly_hours": case["weekly_hours"],
                "ho_quota_percent": 60,
                "active_weekdays": case["active_weekdays"],
                "default_start_time": "08:00",
                "hide_weekends": False,
                "auto_convert_planned": True,
                "christmas_eve_and_new_years_eve_off": True,
            })
            assert settings_response.status_code == 200, case["id"]
            if "custom_holiday" in case:
                holiday_response = client.post('/api/custom-holidays', json={
                    "date": case["start"], **case["custom_holiday"],
                })
                assert holiday_response.status_code == 200, case["id"]

            response = client.post('/api/plan/series', json={
                "start": case["start"], "end": case["end"], "weekdays": case["weekdays"],
                "type": case["type"], "overwrite": False,
            })
            assert response.status_code == 200, case["id"]
            with app.app_context():
                planned_dates = [entry.date for entry in WorkEntry.query.filter(
                    WorkEntry.date >= case["start"], WorkEntry.date <= case["end"]
                ).all()]
            assert planned_dates == case["expected"]["planned_dates"], case["id"]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_(dates)).delete(synchronize_session=False)
            CustomHoliday.query.filter(CustomHoliday.date.in_(dates)).delete(synchronize_session=False)
            db.session.commit()


def test_series_plan_preserves_or_overwrites_day_entries_and_plans_future_home(client):
    planned_date = date(2098, 7, 15)
    date_string = planned_date.isoformat()
    settings_response = client.post('/api/settings', json={
        "weekly_hours": 39,
        "ho_quota_percent": 60,
        "active_weekdays": list(range(7)),
        "default_start_time": "08:00",
        "hide_weekends": False,
        "auto_convert_planned": True,
        "christmas_eve_and_new_years_eve_off": True,
    })
    assert settings_response.status_code == 200

    with app.app_context():
        db.session.add_all([
            WorkEntry(date=date_string, type="office", start_time="08:00", end_time="12:00"),
            WorkEntry(date=date_string, type="dr", start_time="13:00", end_time="16:00"),
        ])
        db.session.commit()

    payload = {
        "start": date_string,
        "end": date_string,
        "weekdays": [planned_date.weekday()],
        "type": "home",
    }
    assert client.post('/api/plan/series', json={**payload, "overwrite": False}).status_code == 200
    with app.app_context():
        assert WorkEntry.query.filter_by(date=date_string).count() == 2

    assert client.post('/api/plan/series', json={**payload, "overwrite": True}).status_code == 200
    with app.app_context():
        entries = WorkEntry.query.filter_by(date=date_string).all()
        assert [(entry.type, entry.start_time, entry.end_time) for entry in entries] == [("planned", "", "")]


@pytest.mark.parametrize('payload', [
    {"date": "2024-02-30", "type": "home", "start": "", "end": ""},
    {"date": "2024-02-29", "type": "home", "start": "08:0", "end": ""},
    {"date": "2024-02-29", "type": "home", "start": "-1:00", "end": ""},
    {"date": "2024-02-29", "type": "home", "start": "", "end": "", "glz_override": "NaN"},
    {"date": "2024-02-29", "type": "home", "start": "", "end": "", "glz_override": 1, "glz_override_source": "unknown"},
])
def test_entry_rejects_invalid_business_values(client, payload):
    assert client.post('/api/entry', json=payload).status_code == 400


@pytest.mark.parametrize('payload', [
    {"date": "2024-02-30", "name": "Sondertag", "hours": 0},
    {"date": "2024-02-29", "name": "", "hours": 0},
    {"date": "2024-02-29", "name": "Sondertag", "hours": -1},
    {"date": "2024-02-29", "name": "Sondertag", "hours": "Infinity"},
])
def test_custom_holiday_rejects_invalid_business_values(client, payload):
    assert client.post('/api/custom-holidays', json=payload).status_code == 400

def test_custom_holiday_move_replaces_occupied_date(client):
    assert client.post('/api/custom-holidays', json={"date": "2024-02-01", "name": "Erster", "hours": 0}).status_code == 200
    assert client.post('/api/custom-holidays', json={"date": "2024-02-02", "name": "Zweiter", "hours": 0}).status_code == 200
    holidays = client.get('/api/custom-holidays').get_json()
    first_id = next(holiday["id"] for holiday in holidays if holiday["date"] == "2024-02-01")

    response = client.post('/api/custom-holidays', json={"id": first_id, "date": "2024-02-02", "name": "Erster", "hours": 4})
    assert response.status_code == 200
    holidays = client.get('/api/custom-holidays').get_json()
    assert holidays == [{"id": next(holiday["id"] for holiday in holidays), "date": "2024-02-02", "name": "Erster", "hours": 4}]


def test_series_preview_reports_changes_without_persisting(client):
    response = client.post('/api/plan/series/preview', json={
        "start": "2098-07-14", "end": "2098-07-16",
        "weekdays": [date(2098, 7, day).weekday() for day in range(14, 17)],
        "type": "office", "overwrite": False,
    })
    assert response.status_code == 200
    preview = response.get_json()
    assert preview["success"] is True
    assert preview["created_dates"] == ["2098-07-14", "2098-07-15", "2098-07-16"]
    with app.app_context():
        assert WorkEntry.query.count() == 0


def test_series_preview_revalidates_existing_entries_and_reports_overwrite(client):
    date_string = "2098-07-14"
    with app.app_context():
        db.session.add(WorkEntry(date=date_string, type="vacation"))
        db.session.commit()

    payload = {"start": date_string, "end": date_string, "weekdays": [date(2098, 7, 14).weekday()], "type": "office", "overwrite": True}
    preview = client.post('/api/plan/series/preview', json=payload)
    assert preview.status_code == 200
    assert preview.get_json()["overwritten_dates"] == [date_string]

    with app.app_context():
        db.session.add(WorkEntry(date=date_string, type="sick"))
        db.session.commit()

    confirmed = client.post('/api/plan/series', json=payload)
    assert confirmed.status_code == 200
    with app.app_context():
        entries = WorkEntry.query.filter_by(date=date_string).all()
        assert [(entry.type, entry.start_time, entry.end_time) for entry in entries] == [("office", "08:00", "16:18")]


def test_series_preview_reports_skipped_existing_and_excluded_dates(client):
    existing_date = "2098-07-14"
    holiday_date = "2098-07-15"
    inactive_date = "2098-07-16"
    try:
        settings_response = client.post('/api/settings', json={
            "weekly_hours": 39,
            "ho_quota_percent": 60,
            "active_weekdays": [date(2098, 7, 14).weekday()],
            "default_start_time": "08:00",
            "hide_weekends": False,
            "auto_convert_planned": True,
            "christmas_eve_and_new_years_eve_off": True,
        })
        assert settings_response.status_code == 200
        with app.app_context():
            db.session.add(WorkEntry(date=existing_date, type="vacation"))
            db.session.add(CustomHoliday(date=holiday_date, name="Freier Sondertag", hours=0))
            db.session.commit()

        preview = client.post('/api/plan/series/preview', json={
            "start": existing_date,
            "end": inactive_date,
            "weekdays": [date(2098, 7, day).weekday() for day in range(14, 17)],
            "type": "office",
            "overwrite": False,
        })
        assert preview.status_code == 200
        report = preview.get_json()
        assert report["created_dates"] == []
        assert report["skipped_existing_dates"] == [existing_date]
        assert report["excluded_dates"] == [holiday_date, inactive_date]
        with app.app_context():
            assert WorkEntry.query.filter_by(date=existing_date).count() == 1
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_([existing_date, holiday_date, inactive_date])).delete(synchronize_session=False)
            CustomHoliday.query.filter_by(date=holiday_date).delete()
            db.session.commit()


def test_copy_or_move_requires_explicit_conflict_resolution_and_preserves_entries(client):
    source_date = "2098-07-15"
    target_date = "2098-07-16"
    try:
        with app.app_context():
            db.session.add_all([
                WorkEntry(date=source_date, type="home", start_time="22:00", end_time="02:00", comment="Nachtschicht"),
                WorkEntry(date=target_date, type="office", start_time="08:00", end_time="16:00", comment="Bestehend"),
            ])
            db.session.commit()

        conflict = client.post('/api/entry/copy-or-move', json={
            "source_date": source_date, "target_date": target_date, "operation": "move",
        })
        assert conflict.status_code == 409
        assert conflict.get_json()["conflict"] is True
        assert conflict.get_json()["source_entries"] == 1
        assert conflict.get_json()["target_entries"] == 1

        merged = client.post('/api/entry/copy-or-move', json={
            "source_date": source_date, "target_date": target_date, "operation": "move", "conflict_mode": "merge",
        })
        assert merged.status_code == 200
        with app.app_context():
            assert WorkEntry.query.filter_by(date=source_date).count() == 0
            target_entries = WorkEntry.query.filter_by(date=target_date).order_by(WorkEntry.id).all()
            assert [(entry.type, entry.start_time, entry.end_time, entry.comment) for entry in target_entries] == [
                ("office", "08:00", "16:00", "Bestehend"),
                ("home", "22:00", "02:00", "Nachtschicht"),
            ]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_([source_date, target_date])).delete(synchronize_session=False)
            db.session.commit()


def test_copy_or_move_overwrite_replaces_target_without_deleting_source_for_copy(client):
    source_date = "2098-07-17"
    target_date = "2098-07-18"
    try:
        with app.app_context():
            db.session.add_all([
                WorkEntry(date=source_date, type="home", start_time="08:00", end_time="16:00"),
                WorkEntry(date=target_date, type="vacation"),
            ])
            db.session.commit()

        response = client.post('/api/entry/copy-or-move', json={
            "source_date": source_date, "target_date": target_date, "operation": "copy", "conflict_mode": "overwrite",
        })
        assert response.status_code == 200
        assert response.get_json()["replaced_entries"] == 1
        with app.app_context():
            assert WorkEntry.query.filter_by(date=source_date).count() == 1
            target_entries = WorkEntry.query.filter_by(date=target_date).all()
            assert [(entry.type, entry.start_time, entry.end_time) for entry in target_entries] == [("home", "08:00", "16:00")]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_([source_date, target_date])).delete(synchronize_session=False)
            db.session.commit()


def test_copy_or_move_rejects_invalid_conflict_mode_without_mutation(client):
    source_date = "2098-07-19"
    target_date = "2098-07-20"
    try:
        with app.app_context():
            db.session.add(WorkEntry(date=source_date, type="home", start_time="08:00", end_time="16:00"))
            db.session.commit()
        response = client.post('/api/entry/copy-or-move', json={
            "source_date": source_date, "target_date": target_date, "operation": "copy", "conflict_mode": "invalid",
        })
        assert response.status_code == 400
        with app.app_context():
            assert WorkEntry.query.filter_by(date=source_date).count() == 1
            assert WorkEntry.query.filter_by(date=target_date).count() == 0
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_([source_date, target_date])).delete(synchronize_session=False)
            db.session.commit()


def test_copy_or_move_merge_skips_duplicates_and_preserves_target_glz_anchor(client):
    source_date = "2098-07-21"
    target_date = "2098-07-22"
    try:
        with app.app_context():
            db.session.add_all([
                WorkEntry(date=source_date, type="home", start_time="08:00", end_time="16:00", comment="Gleich"),
                WorkEntry(date=source_date, type="office", start_time="17:00", end_time="19:00", glz_override=3.0, glz_override_source="manual"),
                WorkEntry(date=target_date, type="home", start_time="08:00", end_time="16:00", comment="Gleich"),
                WorkEntry(date=target_date, type="vacation", glz_override=1.0, glz_override_source="manual"),
            ])
            db.session.commit()
        response = client.post('/api/entry/copy-or-move', json={
            "source_date": source_date, "target_date": target_date, "operation": "copy", "conflict_mode": "merge",
        })
        assert response.status_code == 200
        report = response.get_json()
        assert report["copied_entries"] == 1
        assert report["skipped_duplicates"] == 1
        assert report["glz_override_conflicts"] == 1
        with app.app_context():
            target_entries = WorkEntry.query.filter_by(date=target_date).order_by(WorkEntry.id).all()
            assert len(target_entries) == 3
            assert target_entries[1].glz_override == 1.0
            copied = next(entry for entry in target_entries if entry.type == "office")
            assert copied.glz_override is None
            assert copied.glz_override_source is None
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_([source_date, target_date])).delete(synchronize_session=False)
            db.session.commit()


def test_create_and_read_entry(client):
    # 1. Eintrag erstellen (POST)
    payload = {
        "date": "2024-01-15",
        "type": "office",
        "start": "08:00",
        "end": "16:00",
        "comment": "Test Büro"
    }
    res_post = client.post('/api/entry', json=payload)
    assert res_post.status_code == 200
    assert res_post.get_json()["success"] is True

    # 2. Prüfen ob er in der Datenbank ist
    res_get = client.get('/api/month/2024/01')
    data = res_get.get_json()
    day_item = next((item for item in data['items'] if item.get('date') == '2024-01-15'), None)
    assert day_item is not None
    assert day_item['entries'][0]['type'] == 'office'
    
    # 3. Cleanup: Testdaten wieder löschen, um die echte DB nicht zu vermüllen
    with app.app_context():
        WorkEntry.query.filter_by(date="2024-01-15").delete()
        db.session.commit()

def test_shared_incomplete_entry_cases(client):
    """Docker erfüllt alle zentral definierten Regeln für unvollständige Einträge."""
    cases = json.loads(SHARED_INCOMPLETE_ENTRY_CASES.read_text(encoding="utf-8"))["cases"]
    today = get_local_now().date()
    dates = {"past": today - timedelta(days=1), "today": today, "future": today + timedelta(days=1)}
    created_ids = []

    try:
        for case in cases:
            entry_date = dates[case["relative_day"]]
            response = client.post("/api/entry", json={
                "date": entry_date.isoformat(), "type": case["type"], "start": "", "end": "",
                "comment": f"Referenzfall {case['id']}",
            })
            assert response.status_code == 200, case["id"]
            created_ids.append((case, entry_date, response.get_json()["id"]))

        month_cache = {}
        for case, entry_date, entry_id in created_ids:
            key = (entry_date.year, entry_date.month)
            if key not in month_cache:
                response = client.get(f"/api/month/{entry_date.year}/{entry_date.month:02d}")
                assert response.status_code == 200, case["id"]
                month_cache[key] = {item["date"]: item for item in response.get_json()["items"] if item.get("row_type") == "day"}
            day = month_cache[key][entry_date.isoformat()]
            entry = next(item for item in day["entries"] if item["id"] == entry_id)
            expected = day["daily_target"] if case["expected_mode"] == "target" else 0
            assert entry["net"] == expected, case["id"]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.id.in_([entry_id for _, _, entry_id in created_ids])).delete(synchronize_session=False)
            db.session.commit()

def test_glz_override_save_and_carryover(client):
    """Prüft ob der GLZ Override gespeichert wird und zukünftige Tage beeinflusst."""
    payload = {
        "date": "2024-01-10",
        "type": "home",
        "start": "08:00",
        "end": "16:00",
        "glz_override": 12.5
    }
    client.post('/api/entry', json=payload)

    res_jan = client.get('/api/month/2024/01')
    jan_data = res_jan.get_json()
    
    day_10 = next((i for i in jan_data['items'] if i.get('date') == '2024-01-10'), None)
    assert day_10 is not None
    assert day_10['entries'][0]['glz_override'] == 12.5
    
    # Cleanup
    with app.app_context():
        WorkEntry.query.filter_by(date="2024-01-10").delete()
        db.session.commit()

def test_json_export_and_additive_import(client):
    """Das gemeinsame Austauschformat ergänzt nur neue Einträge und meldet GLZ-Konflikte."""
    unique_date = "2098-07-15"
    payload = {
        "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00+00:00",
        "settings": {"weekly_hours": 39}, "custom_holidays": [],
        "entries": [{"date": unique_date, "type": "home", "start": "08:00", "end": "16:30", "comment": "JSON-Test", "glz_override": 4.5, "glz_override_source": "manual"}]
    }
    try:
        exported = client.get('/api/export/json')
        assert exported.status_code == 200
        assert exported.get_json()['format'] == 'ho-planer-export'
        assert exported.get_json()['version'] == 1

        response = client.post('/api/import/json', data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')}, content_type='multipart/form-data')
        assert response.status_code == 200
        assert response.get_json()['imported_entries'] == 1

        duplicate = client.post('/api/import/json', data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')}, content_type='multipart/form-data')
        assert duplicate.status_code == 200
        assert duplicate.get_json()['skipped_entries'] == 1
    finally:
        with app.app_context():
            WorkEntry.query.filter_by(date=unique_date).delete()
            db.session.commit()


@pytest.mark.parametrize('payload', [
    {"format": "ho-planer-export", "version": 1, "custom_holidays": []},
    {"format": "ho-planer-export", "version": 1, "entries": []},
    {"format": "ho-planer-export", "version": 1, "entries": {}, "custom_holidays": []},
    {"format": "ho-planer-export", "version": 1, "entries": [], "custom_holidays": {}},
])
def test_json_import_rejects_missing_or_non_list_containers(client, payload):
    response = client.post(
        '/api/import/json',
        data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400


@pytest.mark.parametrize('payload', [
    {"format": "unsupported", "version": 1, "entries": [], "custom_holidays": []},
    {"format": "ho-planer-export", "version": 2, "entries": [], "custom_holidays": []},
])
def test_json_import_rejects_unsupported_format_or_version(client, payload):
    response = client.post(
        '/api/import/json',
        data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400


def test_json_import_rejects_invalid_json(client):
    response = client.post(
        '/api/import/json',
        data={'file': (io.BytesIO(b'{invalid json'), 'export.json')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 400


def test_json_import_ignores_exported_settings_and_rejects_negative_holiday_hours(client):
    settings_before = client.get('/api/settings').get_json()
    payload = {
        "format": "ho-planer-export",
        "version": 1,
        "settings": {"weekly_hours": 1, "active_weekdays": [6]},
        "entries": [],
        "custom_holidays": [{"date": "2098-07-15", "name": "Ungültig", "hours": -1}],
    }
    response = client.post(
        '/api/import/json',
        data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')},
        content_type='multipart/form-data',
    )
    assert response.status_code == 200
    result = response.get_json()
    assert result["settings_imported"] is False
    assert result["holiday_conflicts"] == 1
    assert client.get('/api/settings').get_json()["weekly_hours"] == settings_before["weekly_hours"]


def test_json_import_skips_invalid_objects_with_detail_codes(client):
    payload = {
        "format": "ho-planer-export", "version": 1, "settings": {}, "custom_holidays": [],
        "entries": [
            {"date": "2024-02-30", "type": "home", "start": "", "end": ""},
            {"date": "2024-02-29", "type": "home", "start": "08:00", "end": "16:00", "glz_override": "Infinity"},
            {"date": "2024-02-29", "type": "home", "start": "08:00", "end": "16:00", "glz_override_source": "unknown"},
            {"date": "2024-02-29", "type": "home", "start": "08:00", "end": "16:00", "glz_override": 2, "glz_override_source": "manual"},
        ],
    }
    try:
        response = client.post('/api/import/json', data={'file': (io.BytesIO(json.dumps(payload).encode('utf-8')), 'export.json')}, content_type='multipart/form-data')
        result = response.get_json()
        assert response.status_code == 200
        assert result['imported_entries'] == 1
        assert result['invalid_entries'] == 3
        assert result['details'] == ['entries[0]: invalid_date', 'entries[1]: invalid_glz_override', 'entries[2]: invalid_glz_override_source']
    finally:
        with app.app_context():
            WorkEntry.query.filter_by(date='2024-02-29').delete()
            db.session.commit()


def test_shared_json_import_cases(client):
    """Der API-Import erfüllt alle zentral definierten additiven Importfälle."""
    cases = json.loads(SHARED_IMPORT_CASES.read_text(encoding="utf-8"))["cases"]
    unique_dates = {entry["date"] for case in cases for entry in case["incoming_entries"]}
    try:
        for case in cases:
            with app.app_context():
                for existing in case["existing_entries"]:
                    db.session.add(WorkEntry(
                        date=existing["date"], type=existing["type"], start_time=existing["start"],
                        end_time=existing["end"], comment=existing["comment"],
                        glz_override=existing["glz_override"], glz_override_source=existing["glz_override_source"],
                    ))
                db.session.commit()

            payload = {
                "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00+00:00",
                "settings": {}, "custom_holidays": [], "entries": case["incoming_entries"],
            }
            response = client.post(
                "/api/import/json",
                data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "export.json")},
                content_type="multipart/form-data",
            )
            assert response.status_code == 200, case["id"]
            result = response.get_json()
            assert result["imported_entries"] == case["expected"]["imported_entries"], case["id"]
            assert result["skipped_entries"] == case["expected"]["skipped_entries"], case["id"]
            if "invalid_entries" in case["expected"]:
                assert result["invalid_entries"] == case["expected"]["invalid_entries"], case["id"]
                assert result["details"] == case["expected"]["details"], case["id"]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_(unique_dates)).delete(synchronize_session=False)
            db.session.commit()


def test_shared_pdf_merge_cases():
    """Docker erfüllt die gemeinsamen Regeln zum additiven PDF-Blockmerge."""
    cases = json.loads(SHARED_PDF_MERGE_CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        existing_entries = [SimpleNamespace(**entry) for entry in case["existing_entries"]]
        merged = merge_pdf_entries(existing_entries, case["pdf_entries"])
        expected = case["expected"]
        assert len(merged["entries_to_add"]) == expected["imported_entries"], case["id"]
        for field in ("skipped_duplicates", "comment_hints", "glz_override_conflicts"):
            assert merged[field] == expected[field], case["id"]
        assert merged["entries_to_add"] == expected["added_entries"], case["id"]
        if "existing_comments" in expected:
            assert [entry.comment for entry in existing_entries] == expected["existing_comments"], case["id"]



def test_glz_carryover_uses_last_anchor_stored_on_same_day(client):
    anchor_date = "2098-04-30"
    try:
        with app.app_context():
            settings = Settings.query.first()
            WorkEntry.query.filter_by(date=anchor_date).delete()
            db.session.add_all([
                WorkEntry(date=anchor_date, type="home", glz_override=1.5, glz_override_source="manual"),
                WorkEntry(date=anchor_date, type="office", glz_override=4.0, glz_override_source="pdf"),
            ])
            db.session.commit()
            assert get_glz_carryover(2098, 5, settings, {}) == 4.0
    finally:
        with app.app_context():
            WorkEntry.query.filter_by(date=anchor_date).delete()
            db.session.commit()



def test_json_import_preview_accepts_multiple_new_glz_anchors_on_same_day(client):
    """Vorschau und Import behandeln neue Anker desselben Tages identisch."""
    case = next(
        case for case in json.loads(SHARED_GLZ_CASES.read_text(encoding="utf-8"))["cases"]
        if case["id"] == "multiple-anchors-on-same-day-use-last-stored-entry"
    )
    payload = {
        "format": "ho-planer-export", "version": 1, "settings": {}, "custom_holidays": [],
        "entries": case["entries"],
    }

    preview = client.post(
        "/api/import/json/preview",
        data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "export.json")},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200
    assert preview.get_json()["glz_override_conflicts"] == 0
    assert preview.get_json()["valid_entries"] == 2

    imported = client.post(
        "/api/import/json",
        data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "export.json")},
        content_type="multipart/form-data",
    )
    assert imported.status_code == 200
    assert imported.get_json()["glz_override_conflicts"] == 0
    assert imported.get_json()["imported_entries"] == 2

    anchor = case["expected_anchor"]
    with app.app_context():
        entries = WorkEntry.query.filter_by(date=anchor["date"]).order_by(WorkEntry.id).all()
        assert [(entry.glz_override, entry.glz_override_source) for entry in entries] == [
            (1.5, "manual"), (4.0, "pdf"),
        ]
        assert get_glz_carryover(2025, 4, Settings.query.first(), {}) == anchor["value"]


def test_shared_glz_anchor_round_trip(client):
    """GLZ-Anker behalten beim JSON-Import und anschließendem Export Wert sowie Quelle."""
    cases = json.loads(SHARED_GLZ_CASES.read_text(encoding="utf-8"))["cases"]
    dates = {entry["date"] for case in cases for entry in case["entries"]}
    try:
        for case in cases:
            payload = {
                "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00+00:00",
                "settings": {}, "custom_holidays": [], "entries": case["entries"],
            }
            response = client.post(
                "/api/import/json",
                data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "export.json")},
                content_type="multipart/form-data",
            )
            assert response.status_code == 200, case["id"]

        exported = client.get("/api/export/json")
        assert exported.status_code == 200
        entries = exported.get_json()["entries"]
        for case in cases:
            anchor = case["expected_anchor"]
            exported_anchor = next(entry for entry in entries if entry["date"] == anchor["date"] and entry["glz_override"] == anchor["value"])
            assert exported_anchor["glz_override_source"] == anchor["source"], case["id"]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_(dates)).delete(synchronize_session=False)
            db.session.commit()


def test_edit_custom_holiday(client):
    """Prüft ob ein bestehender Feiertag überschrieben wird (auch bei Datumsänderung)."""
    # Basis-Zustand merken (da evt. Daten von test_gui.py existieren)
    initial_holidays = client.get('/api/custom-holidays').get_json()
    initial_count = len(initial_holidays)

    # 1. Feiertag anlegen (Datum weit in der Zukunft, um Konflikte zu vermeiden)
    payload_create = {"date": "2099-05-01", "name": "Tag der Arbeit", "hours": 0}
    client.post('/api/custom-holidays', json=payload_create)

    # Prüfen, ob er angelegt wurde
    holidays_after_create = client.get('/api/custom-holidays').get_json()
    assert len(holidays_after_create) == initial_count + 1

    # ID des neuen Feiertags herausfinden
    created_holiday = next(h for h in holidays_after_create if h["date"] == "2099-05-01")
    holiday_id = created_holiday["id"]

    # 2. Feiertag bearbeiten (Datum und Name ändern)
    payload_update = {
        "id": holiday_id, 
        "date": "2099-05-02", 
        "name": "Geänderter Feiertag", 
        "hours": 4.0
    }
    client.post('/api/custom-holidays', json=payload_update)

    # 3. Überprüfen, ob die Änderung korrekt übernommen wurde
    holidays_after_update = client.get('/api/custom-holidays').get_json()
    
    # Die Gesamtanzahl darf sich beim Bearbeiten nicht verändern
    assert len(holidays_after_update) == initial_count + 1
    
    # Den bearbeiteten Feiertag holen und Werte prüfen
    updated_holiday = next(h for h in holidays_after_update if h["id"] == holiday_id)
    assert updated_holiday["date"] == "2099-05-02"
    assert updated_holiday["name"] == "Geänderter Feiertag"
    assert updated_holiday["hours"] == 4.0