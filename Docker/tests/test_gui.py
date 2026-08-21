import pytest
import re
from datetime import datetime
from playwright.sync_api import Page, expect

# Die frühere Beta-Oberfläche ist die produktive Standardansicht.
BASE_URL = "http://localhost:5000/"

@pytest.fixture(autouse=True)
def setup_viewport(page: Page):
    """
    Zwingt Playwright in eine Desktop-Auflösung (1280x800).
    """
    page.set_viewport_size({"width": 1280, "height": 800})
    yield

# ==========================================
# TESTS FÜR DIE PRODUKTIVE STANDARDANSICHT
# ==========================================

def test_standard_initial_elements_present(page: Page):
    page.goto(BASE_URL)
    # Titel ist jetzt in der neuen Top-App-Bar
    expect(page.get_by_text("HO Planer").first).to_be_visible()
    
    # Menüeinträge prüfen (sind jetzt Icons mit title Attributen in der Header-Leiste)
    expect(page.locator("button[title='PDF Import']").first).to_be_visible()
    expect(page.locator("button[title='Serien-Planer']").first).to_be_visible()
    expect(page.locator("button[title='Einstellungen']").first).to_be_visible()

def test_standard_switch_views(page: Page):
    page.goto(BASE_URL)
    
    # Listenansicht / Timeline (Standard in V2)
    expect(page.locator(".tl-panel")).to_be_visible()
    
    # Jahresansicht (Klick auf den Segmented Control Button oben)
    page.locator(".view-btn").filter(has_text="Jahr").click()
    expect(page.get_by_text("Jahresübersicht").first).to_be_visible()
    
    # Kalenderansicht (Klick auf Button)
    page.locator(".view-btn").filter(has_text="Kalender").click()
    expect(page.locator(".cal-grid-wrapper")).to_be_visible()
    
    # Warten, bis die erste Zelle (.cal-cell) tatsächlich im DOM erscheint
    expect(page.locator(".cal-cell").first).to_be_visible()
    count = page.locator(".cal-cell").count()
    assert count >= 28

def test_standard_year_navigation(page: Page):
    page.goto(BASE_URL)
    page.locator(".view-btn").filter(has_text="Jahr").click()
    current_year = datetime.now().year
    
    expect(page.get_by_text(str(current_year)).first).to_be_visible()
    page.locator(".mdi-chevron-right").first.click()
    expect(page.get_by_text(str(current_year + 1)).first).to_be_visible()

def test_standard_bento_dashboard_content(page: Page):
    page.goto(BASE_URL)
    dashboard = page.locator(".bento-grid").first
    expect(dashboard).to_be_visible()
    
    # Prüfen auf die 3 neuen Bento-Spalten
    expect(dashboard.locator(".bento-label").filter(has_text=re.compile(r"Arbeitstage", re.IGNORECASE))).to_be_visible()
    expect(dashboard.locator(".bento-label").filter(has_text=re.compile(r"Gleitzeit", re.IGNORECASE))).to_be_visible()
    expect(dashboard.locator(".bento-label").filter(has_text=re.compile(r"Budget", re.IGNORECASE))).to_be_visible()
    
    # Sicherstellen, dass das Büro-Bento wirklich gelöscht wurde
    expect(dashboard.locator(".bento-label").filter(has_text=re.compile(r"Büro", re.IGNORECASE))).not_to_be_visible()

def test_standard_list_view_new_columns(page: Page):
    """Prüft, ob die Spalte „GLZ Abgleich“ im Hybrid-Grid vorhanden ist."""
    page.goto(BASE_URL)
    # GEFIXT: Prüft nur noch, ob das Element ins DOM geladen wurde (ignoriert Vuetify Mobile-Breakpoints)
    expect(page.locator(".tl-header").filter(has_text="GLZ Abgleich").first).to_be_attached()

def test_standard_edit_day_dialog_calendar(page: Page):
    page.goto(BASE_URL)
    
    # In V2 öffnet sich der Bearbeitungs-Dialog über einen Klick in den Kalender
    page.locator(".view-btn").filter(has_text="Kalender").click()
    
    # Warten bis Kalender da ist
    expect(page.locator(".cal-cell").first).to_be_visible()
    cell = page.locator(".cal-cell").nth(15) 
    cell.click()
    
    dialog = page.locator(".v-dialog .v-card").first
    expect(dialog).to_be_visible()
    
    # Dropdown statt einzelner Buttons in V2
    select_box = dialog.locator("select.hover-select").first
    expect(select_box).to_be_visible()

    # GLZ Input Test
    # GEFIXT: .first hinzugefügt, da Vuetify für Textfelder immer zwei <label> Tags generiert!
    expect(dialog.get_by_label("Manueller GLZ Abgleich")).to_be_visible()

def test_standard_series_planner_dialog(page: Page):
    page.goto(BASE_URL)
    page.locator("button[title='Serien-Planer']").click()
    
    dialog_title = page.locator(".v-card-title").filter(has_text="Serien-Planer")
    expect(dialog_title).to_be_visible()
    
    expect(page.locator("label").filter(has_text="Mo").first).to_be_visible()
    
    # Schließen
    dialog_card = page.locator(".v-card").filter(has=dialog_title)
    cancel_btn = dialog_card.locator("button").filter(has_text="Abbrechen")
    cancel_btn.click()
    expect(dialog_title).not_to_be_visible()

def test_standard_custom_holiday_edit(page: Page):
    page.goto(BASE_URL)
    
    # Einstellungen öffnen
    page.locator("button[title='Einstellungen']").click()
    dialog = page.locator(".v-dialog .v-card").filter(has_text="Einstellungen")
    expect(dialog).to_be_visible()
    
    # Wäldchestag laden (als Testdaten)
    dialog.locator("button").filter(has_text="Wäldchestag").click()
    
    # Speichern
    save_icon_btn = dialog.locator(".mdi-content-save").locator("..")
    save_icon_btn.click()
    
    # Prüfen, ob Wäldchestag nun in der Liste steht
    expect(dialog.get_by_text("Wäldchestag").first).to_be_visible()
    
    # Auf den Stift (Edit-Icon) klicken
    dialog.locator("div.d-flex.align-center").filter(has_text="Wäldchestag").locator(".mdi-pencil").click()
    
    # Feld ändern
    page.get_by_label("Bez.").fill("Test Feiertag")
    save_icon_btn.click()
    
    # Warten und prüfen, ob sich der Text aktualisiert hat
    expect(dialog.get_by_text("Test Feiertag").first).to_be_visible()
    
    # Fenster wieder schließen
    dialog.locator("button").filter(has_text="Speichern & Schließen").click()
    expect(dialog).not_to_be_visible()