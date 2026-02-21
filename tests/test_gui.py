import pytest
import re
from datetime import datetime
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:5000"

def test_initial_elements_present(page: Page):
    page.goto(BASE_URL)
    # Titel ist jetzt im Navigation Drawer
    expect(page.locator(".v-navigation-drawer").get_by_text("HO Planer").first).to_be_visible()
    
    # Menüeinträge prüfen
    expect(page.locator(".v-list-item").filter(has_text="Kalender")).to_be_visible()
    expect(page.locator(".v-list-item").filter(has_text="PDF Importieren")).to_be_visible()

def test_switch_views(page: Page):
    page.goto(BASE_URL)
    # Listenansicht (Standard)
    expect(page.locator("table")).to_be_visible()
    
    # Jahresansicht (Klick im Seitenmenü)
    page.locator(".v-list-item").filter(has_text="Jahresübersicht").click()
    expect(page.locator("th").filter(has_text="Home Office")).to_be_visible()
    
    # Kalenderansicht (Klick im Seitenmenü)
    page.locator(".v-list-item").filter(has_text="Kalender").click()
    expect(page.locator(".calendar-wrapper")).to_be_visible()
    
    # Warten, bis die erste Zelle (.cal-cell) tatsächlich im DOM erscheint
    expect(page.locator(".cal-cell").first).to_be_visible()

    # Jetzt können wir sicher zählen
    count = page.locator(".cal-cell").count()
    assert count >= 28

def test_year_navigation(page: Page):
    page.goto(BASE_URL)
    page.locator(".v-list-item").filter(has_text="Jahresübersicht").click()
    current_year = datetime.now().year
    
    expect(page.get_by_text(str(current_year)).first).to_be_visible()
    page.locator(".mdi-chevron-right").first.click()
    expect(page.get_by_text(str(current_year + 1)).first).to_be_visible()

def test_month_navigation(page: Page):
    page.goto(BASE_URL)
    page.locator(".mdi-chevron-left").first.click()
    day_cell = page.locator("td").filter(has_text=re.compile(r"^\d+\.")).first
    expect(day_cell).to_be_visible()

def test_status_bar_content(page: Page):
    page.goto(BASE_URL)
    status_bar = page.locator(".status-bar").first
    expect(status_bar).to_be_visible()
    
    # Angepasst an die neuen Dashboard-Karten Texte (Regex wegen Zeilenumbrüchen im HTML)
    expect(status_bar.locator(".stat-label").filter(has_text=re.compile(r"Arbeitstage", re.IGNORECASE))).to_be_visible()
    expect(status_bar.locator(".stat-label").filter(has_text=re.compile(r"Bürostd", re.IGNORECASE))).to_be_visible()
    expect(status_bar.locator(".stat-label").filter(has_text=re.compile(r"Gleitzeit", re.IGNORECASE))).to_be_visible()
    expect(status_bar.locator(".stat-label").filter(has_text=re.compile(r"Budget", re.IGNORECASE))).to_be_visible()

def test_list_view_new_columns(page: Page):
    """Prüft ob die 'GLZ Saldo' Spalte in der Tabelle vorhanden ist."""
    page.goto(BASE_URL)
    expect(page.locator("th").filter(has_text="GLZ Saldo")).to_be_visible()

def test_edit_day_dialog_buttons(page: Page):
    page.goto(BASE_URL)
    
    # Da die Buttons jetzt Hover-Aktionen sind, weisen wir Playwright an, 
    # das Element sicherheitshalber vorher zu hovern.
    row = page.locator(".day-row").first
    row.hover()
    row.locator(".mdi-pencil").click()
    
    dialog = page.locator(".v-overlay__content").filter(has=page.locator(".v-card-title"))
    expect(dialog).to_be_visible()
    
    # Buttons der Schnellauswahl prüfen
    expect(dialog.locator("button").filter(has_text="Home Office")).to_be_visible()
    expect(dialog.locator("button").filter(has_text="Büro")).to_be_visible()

    # GLZ-Override Label im Dialog prüfen
    expect(dialog.get_by_text("GLZ Sync-Anker")).to_be_visible()

def test_pdf_import_element_exists(page: Page):
    page.goto(BASE_URL)
    # Der Listen-Eintrag im Sidebar-Menü
    pdf_item = page.locator(".v-list-item").filter(has_text="PDF Importieren")
    expect(pdf_item).to_be_visible()
    # Das versteckte File-Input Element
    pdf_input = page.locator("input[type='file']")
    expect(pdf_input).to_be_attached()

def test_series_planner_dialog(page: Page):
    page.goto(BASE_URL)
    page.locator(".v-list-item").filter(has_text="Serien-Planer").click()
    
    dialog_title = page.locator(".v-card-title").filter(has_text="Serien-Planer")
    expect(dialog_title).to_be_visible()
    
    expect(page.locator("label").filter(has_text="Mo").first).to_be_visible()
    
    # Schließen
    dialog_card = page.locator(".v-card").filter(has=dialog_title)
    cancel_btn = dialog_card.locator("button").filter(has_text="Abbrechen")
    cancel_btn.click()
    expect(dialog_title).not_to_be_visible()

def test_custom_holiday_edit(page: Page):
    """NEU: Prüft ob der Edit-Button für eigene Feiertage in den Einstellungen funktioniert."""
    page.goto(BASE_URL)
    
    # Einstellungen öffnen
    page.locator(".v-list-item").filter(has_text="Einstellungen").click()
    dialog = page.locator(".v-dialog .v-card").filter(has_text="Einstellungen")
    expect(dialog).to_be_visible()
    
    # Wäldchestag laden (als Testdaten)
    dialog.locator("button").filter(has_text="Wäldchestag").click()
    
    # Speichern (mit dem Plus/Save Button)
    save_icon_btn = dialog.locator(".mdi-content-save").locator("..")
    save_icon_btn.click()
    
    # Prüfen, ob Wäldchestag nun in der Liste steht
    expect(dialog.get_by_text("Wäldchestag").first).to_be_visible()
    
    # Auf den Stift (Edit-Icon) klicken
    # Sucht die Zeile mit dem Wäldchestag und klickt das .mdi-pencil Icon
    dialog.locator("div.d-flex.align-center").filter(has_text="Wäldchestag").locator(".mdi-pencil").click()
    
    # Feld ändern
    page.get_by_label("Bez.").fill("Test Feiertag")
    save_icon_btn.click()
    
    # Warten und prüfen, ob sich der Text aktualisiert hat und "Wäldchestag" verschwunden ist
    expect(dialog.get_by_text("Test Feiertag").first).to_be_visible()
    
    # Fenster wieder schließen
    dialog.locator("button").filter(has_text="Speichern & Schließen").click()
    expect(dialog).not_to_be_visible()