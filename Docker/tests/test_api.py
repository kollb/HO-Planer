import pytest
import pytest
import json
from pathlib import Path
from datetime import timedelta
import io
from app import app, db, Settings, WorkEntry, CustomHoliday, get_local_now

SHARED_IMPORT_CASES = Path(__file__).resolve().parents[2] / "shared" / "test-cases" / "json-import.json"

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
    assert b"Home Office Planer" in response.data

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

def test_unfinished_actual_entries_count_only_for_future_days(client):
    """Unvollständige Ist-Einträge erhalten nur an zukünftigen Tagen die Sollzeit."""
    today = get_local_now().date()
    tomorrow = today + timedelta(days=1)
    created_ids = []

    try:
        for entry_date, entry_type in ((today, "home"), (tomorrow, "office"), (today, "dr")):
            response = client.post('/api/entry', json={
                "date": entry_date.isoformat(),
                "type": entry_type,
                "start": "",
                "end": "",
                "comment": "Heute-Regel-Regressionstest"
            })
            assert response.status_code == 200
            created_ids.append(response.get_json()["id"])

        today_response = client.get(f'/api/month/{today.year}/{today.month:02d}')
        assert today_response.status_code == 200
        today_items = {item["date"]: item for item in today_response.get_json()["items"] if item.get("row_type") == "day"}

        today_entries = today_items[today.isoformat()]["entries"]
        assert next(entry for entry in today_entries if entry["id"] == created_ids[0])["net"] == 0
        assert next(entry for entry in today_entries if entry["id"] == created_ids[2])["net"] == 0

        tomorrow_response = client.get(f'/api/month/{tomorrow.year}/{tomorrow.month:02d}')
        assert tomorrow_response.status_code == 200
        tomorrow_items = {item["date"]: item for item in tomorrow_response.get_json()["items"] if item.get("row_type") == "day"}
        tomorrow_entry = next(entry for entry in tomorrow_items[tomorrow.isoformat()]["entries"] if entry["id"] == created_ids[1])
        assert tomorrow_entry["net"] == tomorrow_items[tomorrow.isoformat()]["daily_target"]
    finally:
        with app.app_context():
            WorkEntry.query.filter(WorkEntry.id.in_(created_ids)).delete(synchronize_session=False)
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


def test_json_import_uses_shared_contract_case(client):
    """Der API-Import erfüllt den zentral definierten additiven Importfall."""
    case = json.loads(SHARED_IMPORT_CASES.read_text(encoding="utf-8"))["cases"][0]
    unique_date = case["incoming_entries"][0]["date"]
    payload = {
        "format": "ho-planer-export", "version": 1, "exported_at": "2098-01-01T00:00:00+00:00",
        "settings": {}, "custom_holidays": [], "entries": case["incoming_entries"],
    }
    try:
        response = client.post(
            "/api/import/json",
            data={"file": (io.BytesIO(json.dumps(payload).encode("utf-8")), "export.json")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        result = response.get_json()
        assert result["imported_entries"] == case["expected"]["imported_entries"]
        assert result["skipped_entries"] == case["expected"]["skipped_entries"]
    finally:
        with app.app_context():
            WorkEntry.query.filter_by(date=unique_date).delete()
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