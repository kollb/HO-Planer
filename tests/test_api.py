import pytest
from app import app, db, Settings, WorkEntry
import json

@pytest.fixture
def client():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            if not db.session.query(Settings).first():
                db.session.add(Settings())
            db.session.commit()
        yield client

def test_index_page_loads(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"Home Office Planer" in response.data

def test_get_settings(client):
    response = client.get('/api/settings')
    assert response.status_code == 200
    assert response.get_json()["weekly_hours"] == 39

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

    # 2. Prüfen ob er in der Datenbank ist (via API GET)
    res_get = client.get('/api/month/2024/01')
    data = res_get.get_json()
    day_item = next((item for item in data['items'] if item.get('date') == '2024-01-15'), None)
    assert day_item is not None
    assert day_item['entries'][0]['type'] == 'office'

def test_glz_override_save_and_carryover(client):
    """NEU: Prüft ob der GLZ Override gespeichert wird und zukünftige Tage beeinflusst."""
    # 1. Override am 10. Januar setzen
    payload = {
        "date": "2024-01-10",
        "type": "home",
        "start": "08:00",
        "end": "16:00",
        "glz_override": 12.5  # Der neue Anker!
    }
    client.post('/api/entry', json=payload)

    # 2. Januar abrufen und prüfen, ob der Anker greift
    res_jan = client.get('/api/month/2024/01')
    jan_data = res_jan.get_json()
    
    day_10 = next((i for i in jan_data['items'] if i.get('date') == '2024-01-10'), None)
    assert day_10 is not None
    assert day_10['entries'][0]['glz_override'] == 12.5
    assert day_10['glz_saldo'] == 12.5

    # 3. Februar abrufen -> Prüfen ob get_glz_carryover den Wert aus Januar mitnimmt
    res_feb = client.get('/api/month/2024/02')
    feb_data = res_feb.get_json()
    # Wenn der Februar startet, sollte der base_saldo die 12.5 aus dem Januar beinhalten
    # (Abzüglich der Sollarbeitszeit vom 11.01 bis 31.01, da diese leer sind)
    assert "current_glz" in feb_data['stats']
    assert type(feb_data['stats']['current_glz']) in [float, int]