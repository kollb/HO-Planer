import pytest
from app import app, db, Settings, WorkEntry
import json

@pytest.fixture
def client():
    # Wir nutzen eine In-Memory Datenbank für Tests, damit die echte DB nicht überschrieben wird
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['TESTING'] = True

    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            # Standard-Settings anlegen
            if not db.session.query(Settings).first():
                db.session.add(Settings())
            db.session.commit()
        yield client

def test_index_page_loads(client):
    """Prüft, ob die HTML-Seite überhaupt ausgeliefert wird."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"Home Office Planer" in response.data
    assert b'<div id="app"' in response.data

def test_get_settings(client):
    """Prüft, ob die API Settings zurückgibt."""
    response = client.get('/api/settings')
    assert response.status_code == 200
    data = response.get_json()
    assert "weekly_hours" in data
    assert data["weekly_hours"] == 39  # Standardwert aus models.py

def test_create_and_read_entry(client):
    """Prüft den kompletten Zyklus: Eintrag erstellen -> Monat abrufen."""
    
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
    assert res_get.status_code == 200
    data = res_get.get_json()
    
    # Suche den Tag 15 im Response
    day_item = next((item for item in data['items'] if item.get('date') == '2024-01-15'), None)
    assert day_item is not None
    assert day_item['entries'][0]['type'] == 'office'
    assert day_item['entries'][0]['comment'] == "Test Büro"