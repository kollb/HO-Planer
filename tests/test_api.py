import pytest
from app import app, db, Settings, WorkEntry, CustomHoliday
import json

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