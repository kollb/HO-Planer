import pytest
import json
from pathlib import Path
from datetime import timedelta
import io

import pytest
from app import app, db, Settings, WorkEntry, CustomHoliday, get_local_now

SHARED_IMPORT_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "json-import.json"
SHARED_INCOMPLETE_ENTRY_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "incomplete-entries.json"
SHARED_GLZ_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "glz.json"

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Da die SQLAlchemy Engine in app.py bereits beim Import an die Datei gebunden wird,
    # nutzen wir diese, räumen aber am Ende der Tests immer brav auf.
    with app.test_client() as client:
        yield client

def test_index_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"HO Planer" in response.data

def test_get_settings(client):
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert "weekly_hours" in response.get_json()

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
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.date.in_(unique_dates)).delete(synchronize_session=False)
            db.session.commit()


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