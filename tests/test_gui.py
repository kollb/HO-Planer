import pytest
import re
from datetime import datetime
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:5000"

# --- Bestehende Tests (unverändert) ---
def test_initial_elements_present(page: Page):
    page.goto(BASE_URL)
    expect(page.locator(".v-toolbar-title")).to_contain_text("HO Planer")
    expect(page.locator(".mdi-calendar-multiple")).to_be_visible()
    expect(page.locator(".mdi-file-pdf-box")).to_be_visible()

def test_switch_views(page: Page):
    page.goto(BASE_URL)
    # Listenansicht (Standard)
    expect(page.locator("table")).to_be_visible()
    
    # Jahresansicht
    page.locator("button").filter(has=page.locator(".mdi-chart-bar")).click()
    expect(page.locator("th").filter(has_text="Home Office Tage")).to_be_visible()
    
    # Kalenderansicht
    page.locator("button").filter(has=page.locator(".mdi-calendar-month")).click()
    expect(page.locator(".calendar-wrapper")).to_be_visible()
    
    # FIX: count() wartet nicht auf das Rendering der Liste.
    # Wir müssen warten, bis die erste Zelle (.cal-cell) tatsächlich im DOM erscheint.
    # expect(...) wartet automatisch bis zu 5 Sekunden.
    expect(page.locator(".cal-cell").first).to_be_visible()

    # Jetzt können wir sicher zählen
    count = page.locator(".cal-cell").count()
    assert count >= 28

def test_year_navigation(page: Page):
    page.goto(BASE_URL)
    page.locator("button").filter(has=page.locator(".mdi-chart-bar")).click()
    current_year = datetime.now().year
    
    expect(page.get_by_text(f"Jahr {current_year}")).to_be_visible()
    page.locator(".mdi-chevron-right").first.click()
    expect(page.get_by_text(f"Jahr {current_year + 1}")).to_be_visible()

def test_month_navigation(page: Page):
    page.goto(BASE_URL)
    page.locator(".mdi-chevron-left").first.click()
    day_cell = page.locator("td").filter(has_text=re.compile(r"^\d+\. ")).first
    expect(day_cell).to_be_visible()

def test_status_bar_content(page: Page):
    page.goto(BASE_URL)
    status_bar = page.locator(".status-bar")
    expect(status_bar).to_be_visible()
    expect(status_bar.locator(".stat-label").filter(has_text="Arbeitstage")).to_be_visible()
    expect(status_bar.locator(".stat-label").filter(has_text="Bürostd.")).to_be_visible()

# --- GEFIXTE TESTS ---

def test_edit_day_dialog_buttons(page: Page):
    page.goto(BASE_URL)
    
    # Öffnen
    page.locator(".day-row").first.locator(".mdi-pencil").click()
    dialog = page.locator(".v-overlay__content").filter(has=page.locator(".v-card-title"))
    expect(dialog).to_be_visible()
    
    # Buttons prüfen
    expect(dialog.locator("button").filter(has_text="Home Office")).to_be_visible()
    expect(dialog.locator("button").filter(has_text="Büro")).to_be_visible()

    # FIX: Vuetify Double-Label Problem.
    # Wir filtern nach 'visible=True', um das versteckte Label zu ignorieren.
    # Alternativ nehmen wir das erste, das Playwright findet, falls visible nicht reicht.
    start_label = dialog.locator("label").filter(has_text="Start").first
    expect(start_label).to_be_visible()

def test_pdf_import_element_exists(page: Page):
    """
    Prüft, ob der PDF-Input vorhanden ist.
    (Der Dialog öffnet sich erst NACH Datei-Auswahl, das ist schwer zu testen ohne Datei).
    """
    page.goto(BASE_URL)
    
    # Der Button ist da
    pdf_btn = page.locator(".mdi-file-pdf-box")
    expect(pdf_btn).to_be_visible()
    
    # Das Input-Feld ist hidden (display: none), aber im DOM
    # Wir prüfen, ob es existiert und angehängt ist
    pdf_input = page.locator("input[type='file']")
    expect(pdf_input).to_be_attached()

def test_series_planner_dialog(page: Page):
    page.goto(BASE_URL)
    page.locator(".mdi-calendar-multiple").click()
    
    dialog_title = page.locator(".v-card-title").filter(has_text="Serien-Planer")
    expect(dialog_title).to_be_visible()
    
    # FIX: Auch hier Double-Label bei "Mo", "Di" etc. möglich
    expect(page.locator("label").filter(has_text="Mo").first).to_be_visible()
    
    # Schließen
    dialog_card = page.locator(".v-card").filter(has=dialog_title)
    cancel_btn = dialog_card.locator("button").filter(has_text="Abbrechen")
    cancel_btn.click()
    expect(dialog_title).not_to_be_visible()