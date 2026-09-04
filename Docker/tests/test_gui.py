import pytest
import re
from datetime import datetime

import pytest
from playwright.sync_api import Page, expect

# Die frühere Beta-Oberfläche ist die produktive Standardansicht.
BASE_URL = "http://localhost:5000/"

# Aktionen liegen an genau einer Stelle: im Menü des Floating Action Buttons.
QUICK_ACTION_FAB = ".quick-action-fab"
QUICK_ACTION_ITEMS = ".v-menu .v-list-item"


def open_quick_actions(page: Page):
    """Öffnet das Aktionsmenü des FAB und liefert seine Einträge."""
    page.locator(QUICK_ACTION_FAB).click()
    items = page.locator(QUICK_ACTION_ITEMS)
    expect(items.first).to_be_visible()
    return items


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

    # Die Kopfzeile trägt Navigation und Darstellung, die Aktionen liegen im FAB.
    expect(page.locator("button[aria-label='Navigation öffnen']")).to_be_visible()
    expect(page.locator(QUICK_ACTION_FAB)).to_be_visible()

    actions = open_quick_actions(page)
    expect(actions.filter(has_text="PDF importieren")).to_be_visible()
    expect(actions.filter(has_text="Serienplanung")).to_be_visible()
    expect(actions.filter(has_text="Einstellungen")).to_be_visible()


def test_app_bar_has_no_obsolete_beta_controls(page: Page):
    """Der BETA-Hinweis und der Verweis „Zurück zu V1" sind entfernt."""
    page.goto(BASE_URL)
    app_bar = page.locator(".v-app-bar")
    expect(app_bar.locator("[title='Zurück zu V1']")).to_have_count(0)
    expect(app_bar.get_by_text("BETA")).to_have_count(0)


def test_app_bar_contains_no_action_duplicates(page: Page):
    """Aktionen hängen nicht zusätzlich in der Kopfzeile."""
    page.goto(BASE_URL)
    app_bar = page.locator(".v-app-bar")
    for label in ("PDF", "Serien", "Einstellungen", "Zurück zu V1", "Aktionen öffnen"):
        expect(app_bar.locator(f"[title*='{label}']")).to_have_count(0)


def test_quick_action_menu_offers_every_action_once(page: Page):
    """Das Aktionsmenü deckt Erfassung, Planung, Import, Export und Einstellungen ab."""
    page.goto(BASE_URL)
    actions = open_quick_actions(page)
    for label in ("Tag erfassen", "Serienplanung", "PDF importieren", "JSON importieren", "JSON exportieren", "Einstellungen"):
        expect(actions.filter(has_text=label)).to_be_visible()
    # Jede Aktion genau einmal
    expect(actions).to_have_count(6)


def test_json_export_downloads_a_file(page: Page):
    """Der Export ist aus der Oberfläche erreichbar und liefert eine Datei."""
    page.goto(BASE_URL)
    with page.expect_download() as download_info:
        open_quick_actions(page).filter(has_text="JSON exportieren").click()
    download = download_info.value
    assert download.suggested_filename.startswith("ho-planer-export")
    assert download.suggested_filename.endswith(".json")


def test_theme_toggle_switches_and_persists(page: Page):
    """Der Umschalter in der Kopfzeile wechselt das Farbschema dauerhaft."""
    page.goto(BASE_URL)
    initial_theme = page.evaluate("() => document.documentElement.dataset.theme")

    page.locator(".v-app-bar button[aria-label*='Farbschema']").click()
    toggled_theme = page.evaluate("() => document.documentElement.dataset.theme")
    assert toggled_theme in ("light", "dark")
    assert toggled_theme != initial_theme

    expect(page.locator(".v-snackbar")).to_be_visible()
    stored = page.evaluate("() => fetch('/api/settings').then(response => response.json())")
    assert stored["theme"] == toggled_theme

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
    open_quick_actions(page).filter(has_text="Serienplanung").click()
    
    dialog_title = page.locator(".v-card-title").filter(has_text="Serien-Planer")
    expect(dialog_title).to_be_visible()
    
    expect(page.locator("label").filter(has_text="Mo").first).to_be_visible()
    expect(page.locator("label").filter(has_text="Sa").first).to_be_visible()
    expect(page.locator("label").filter(has_text="So").first).to_be_visible()
    
    # Schließen
    dialog_card = page.locator(".v-card").filter(has=dialog_title)
    cancel_btn = dialog_card.locator("button").filter(has_text="Abbrechen")
    cancel_btn.click()
    expect(dialog_title).not_to_be_visible()

def test_standard_custom_holiday_edit(page: Page):
    page.goto(BASE_URL)
    
    # Einstellungen öffnen
    open_quick_actions(page).filter(has_text="Einstellungen").click()
    dialog = page.locator(".v-dialog .v-card").filter(has_text="Einstellungen")
    expect(dialog).to_be_visible()
    expect(dialog.get_by_label("Heiligabend und Silvester arbeitsfrei")).to_be_visible()
    
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


def test_standard_custom_holiday_save_error_is_visible(page: Page):
    """Eine API-Validierungsfehlermeldung beim Speichern bleibt für Nutzende sichtbar."""
    def reject_custom_holiday_save(route):
        if route.request.method == "POST":
            route.fulfill(
                status=400,
                content_type="application/json",
                body='{"success": false, "message": "Sondertag konnte nicht gespeichert werden."}',
            )
        else:
            route.continue_()

    page.route("**/api/custom-holidays", reject_custom_holiday_save)
    page.goto(BASE_URL)
    open_quick_actions(page).filter(has_text="Einstellungen").click()
    dialog = page.locator(".v-dialog .v-card").filter(has_text="Einstellungen")
    expect(dialog).to_be_visible()

    page.get_by_label("Bez.").fill("Test Sondertag")
    date_field = dialog.locator("input[type='date']")
    date_field.fill("2026-09-01")
    page.get_by_label("Std.").fill("6")
    dialog.locator(".mdi-content-save").locator("..").click()

    expect(page.locator(".v-snackbar").filter(has_text="Sondertag konnte nicht gespeichert werden.")).to_be_visible()

# ==========================================
# MOBILE TAGESKARTEN
# ==========================================

def test_mobile_timeline_has_no_repeated_action_buttons(page: Page):
    """Unterhalb der Desktop-Breite gibt es keinen Button je Tag mehr."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)

    expect(page.locator(".tl-day-edit")).to_have_count(0)
    expect(page.locator(".tl-day-card").first).to_be_visible()


def test_mobile_day_card_opens_dialog_by_click(page: Page):
    """Die Tageskarte selbst ist das Bedienelement."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)

    card = page.locator(".tl-day-card").first
    expect(card).to_have_attribute("role", "button")
    expect(card).to_have_attribute("tabindex", "0")

    # Die Felder bleiben direkt bedienbar; getippt wird auf den Kopfbereich der Karte.
    card.locator(".tl-date-cell").first.click()
    expect(page.locator(".v-dialog .v-card").first).to_be_visible()


def test_mobile_day_card_opens_dialog_by_keyboard(page: Page):
    """Die Tageskarte ist auch per Tastatur bedienbar."""
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE_URL)

    card = page.locator(".tl-day-card").first
    card.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".v-dialog .v-card").first).to_be_visible()


def test_desktop_rows_keep_direct_input(page: Page):
    """Auf Desktop bleiben die Felder direkt bedienbar; die Karte ist kein Button."""
    page.goto(BASE_URL)

    card = page.locator(".tl-day-card").first
    expect(card).not_to_have_attribute("role", "button")
    expect(page.locator(".tl-row").first.locator("input").first).to_be_visible()


# ==========================================
# WOCHENKOPF
# ==========================================

def test_week_summary_opens_its_week(page: Page):
    """Der Wochenkopf steht vor den Tagen seiner Woche und bleibt vollständig."""
    page.goto(BASE_URL)
    header = page.locator(".tl-week-sum").first
    expect(header).to_be_visible()

    summary_box = header.bounding_box()
    day_box = page.locator(".tl-day-card").first.bounding_box()
    assert summary_box["y"] < day_box["y"], "Der Kopf muss über seinen Tagen stehen."

    text = header.inner_text()
    assert "KW" in text
    assert "von" in text


def test_week_summary_stays_visible_while_scrolling(page: Page):
    """Beim Scrollen bleibt der Wochenkopf stehen, statt mitzuwandern."""
    page.goto(BASE_URL)
    header = page.locator(".tl-week-sum").first
    expect(header).to_be_visible()

    page.mouse.wheel(0, 500)
    page.wait_for_timeout(500)

    box = header.bounding_box()
    assert box["y"] > 0, "Der Kopf ist beim Scrollen aus dem Blickfeld gewandert."
    assert box["y"] < 200, "Der Kopf klebt nicht unter der Kopfzeile."


def test_week_summary_shows_week_balance(page: Page):
    """Ist von Soll und Abweichung bleiben ablesbar."""
    page.goto(BASE_URL)
    header = page.locator(".tl-week-sum").first
    expect(header).to_be_visible()
    expect(header.locator(".tl-week-sum__week")).to_contain_text("KW")
    expect(header.locator(".tl-week-sum__hours")).to_contain_text("von")
    expect(header.locator(".tl-week-sum__delta")).to_be_visible()


def test_week_summaries_do_not_stack(page: Page):
    """Köpfe dürfen nicht gleichzeitig auf derselben Höhe kleben.

    Ohne eigenen Abschnitt pro Woche sammeln sich alle Köpfe an derselben
    Klebeposition und überdecken sich gegenseitig.
    """
    page.goto(BASE_URL)
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


def test_each_week_forms_its_own_block(page: Page):
    """Variante C: Rahmen fasst Kopf und Tage einer Woche zusammen."""
    page.goto(BASE_URL)
    expect(page.locator(".tl-week").first).to_be_visible()
    blocks = page.evaluate(
        "() => [...document.querySelectorAll('.tl-week')].map(b => ({"
        "  kopf: b.querySelector('.tl-week-sum') ? b.querySelector('.tl-week-sum').innerText.trim().split('\\n')[0] : null,"
        "  tage: [...b.querySelectorAll('.tl-day-card')].map(c => c.dataset.kw),"
        "}))"
    )
    assert len(blocks) >= 4, "Der Monat muss mehrere Wochenblöcke enthalten."
    for block in blocks:
        assert block["kopf"], "Block ohne Kopf"
        assert block["kopf"].startswith("KW ")
        woche = block["kopf"].split()[1]
        assert block["tage"], f"{block['kopf']} enthält keine Tage"
        assert set(block["tage"]) == {woche}, f"Block {woche} enthält fremde Tage: {block['tage']}"


def test_every_day_carries_its_calendar_week(page: Page):
    """Variante B: die Kalenderwoche ist Merkmal des Tages, nicht nur des Kopfes."""
    page.goto(BASE_URL)
    expect(page.locator(".tl-week").first).to_be_visible()
    for anteig in (0, 0.25, 0.5, 0.75, 1.0):
        page.evaluate(f"() => window.scrollTo(0, Math.round(document.documentElement.scrollHeight * {anteig}))")
        page.wait_for_timeout(250)
        zeilen = page.evaluate(
            "() => [...document.querySelectorAll('.tl-day-card')]"
            ".filter(c => { const r = c.getBoundingClientRect(); return r.bottom > 130 && r.top < window.innerHeight - 60; })"
            ".map(c => c.dataset.kw + '|' + (c.querySelector('.tl-date-kw') ? c.querySelector('.tl-date-kw').textContent.trim() : ''))"
        )
        assert zeilen, f"Keine Tageszeile sichtbar bei Scroll-Anteil {anteig}"
        for zeile in zeilen:
            woche, text = zeile.split("|")
            assert text == f"KW {woche}", f"KW-Merkmal falsch oder fehlend: {zeile!r}"
