import pytest
from datetime import date
from logic import normalize_time_str, calculate_net_hours, calculate_gross_time_needed, get_day_info

# --- Mocks & Helper Classes ---
# Wir simulieren die Datenbank-Klassen, damit wir keine echte DB brauchen

class MockSettings:
    def __init__(self, weekly_hours=39.0, active_weekdays="0,1,2,3,4"):
        self.weekly_hours = weekly_hours
        self.active_weekdays = active_weekdays

class MockCustomHoliday:
    def __init__(self, name, hours=0.0):
        self.name = name
        self.hours = hours

# --- 1. Tests für normalize_time_str ---

@pytest.mark.parametrize("input_str, expected", [
    # Standard Formate
    ("08:00", "08:00"),
    ("8:00", "08:00"),
    ("17:30", "17:30"),
    # Formate ohne Doppelpunkt
    ("0800", "08:00"),
    ("800", "08:00"),
    ("1430", "14:30"),
    # Nur Stunden
    ("8", "08:00"),
    ("14", "14:00"),
    # Mit Punkt statt Doppelpunkt
    ("08.00", "08:00"),
    ("8.30", "08:30"),
    # Leerzeichen Trimmen
    (" 08:00 ", "08:00"),
])
def test_normalize_time_valid(input_str, expected):
    assert normalize_time_str(input_str) == expected

@pytest.mark.parametrize("input_str", [
    "", 
    None, 
    "25:00",   # Stunde zu hoch
    "08:60",   # Minute zu hoch
    "abc",     # Kein Zahl
    ("12:3", "12:03"),
    "12345"    # Zu lang
])
def test_normalize_time_invalid(input_str):
    assert normalize_time_str(input_str) is None

# --- 2. Tests für calculate_net_hours ---

@pytest.mark.parametrize("start, end, expected_net", [
    # Fall 1: Unter 6 Stunden (Kein Abzug)
    ("08:00", "12:00", 4.0),
    ("08:00", "14:00", 6.0),      # Exakt 6h -> Kein Abzug
    
    # Fall 2: Über 6 Stunden (0.5h Abzug)
    ("08:00", "14:30", 6.0),      # 6.5h Brutto - 0.5h Pause = 6.0h Netto
    ("08:00", "16:00", 7.5),      # 8.0h Brutto - 0.5h Pause = 7.5h Netto
    ("08:00", "17:00", 8.5),      # 9.0h Brutto - 0.5h Pause = 8.5h Netto (Grenzfall)

    # Fall 3: Über 9 Stunden (0.75h Abzug)
    ("08:00", "17:15", 8.5),      # 9.25h Brutto - 0.75h Pause = 8.5h Netto
    ("08:00", "18:00", 9.25),     # 10.0h Brutto - 0.75h Pause = 9.25h Netto

    # Fall 4: Nachtschicht (Ende < Start)
    ("22:00", "02:00", 4.0),      # 4h Arbeit
    ("20:00", "05:00", 8.5),      # 9h Brutto - 0.5h Pause = 8.5h

    # Fall 5: Ungültige Eingaben
    (None, "12:00", 0.0),
    ("08:00", None, 0.0),
])
def test_calculate_net_hours(start, end, expected_net):
    assert calculate_net_hours(start, end) == expected_net

# --- 3. Tests für calculate_gross_time_needed ---

@pytest.mark.parametrize("target_net, expected_gross", [
    # Bis 6h: Netto = Brutto
    (4.0, 4.0),
    (6.0, 6.0),
    
    # Bis 8.25h Netto (entspricht <= 8.75h Brutto, hier greift deine +0.5 Logik)
    (8.0, 8.5),   # 8.0 Netto braucht 8.5 Brutto (wegen 0.5 Pause)
    (8.25, 8.75), # Grenzfall in deiner Logik
    
    # Über 8.25h Netto -> +0.75 Pause
    (8.5, 9.25), 
])
def test_calculate_gross_time_needed(target_net, expected_gross):
    assert calculate_gross_time_needed(target_net) == expected_gross

# --- 4. Tests für get_day_info (Komplexere Logik) ---

def test_day_info_normal_workday():
    # Ein Dienstag (Weekday 1), keine Ferien, kein Custom Holiday
    d = date(2023, 10, 10) # Ein Dienstag
    settings = MockSettings(weekly_hours=40.0, active_weekdays="0,1,2,3,4")
    he_holidays = {}
    custom_map = {}

    info = get_day_info(d, settings, he_holidays, custom_map)
    
    assert info["is_workday"] is True
    assert info["target"] == 8.0  # 40h / 5 Tage
    assert info["is_off_day"] is False
    assert info["holiday_name"] == ""

def test_day_info_weekend():
    # Ein Sonntag (Weekday 6)
    d = date(2023, 10, 8) 
    settings = MockSettings(weekly_hours=40.0, active_weekdays="0,1,2,3,4")
    he_holidays = {}
    custom_map = {}

    info = get_day_info(d, settings, he_holidays, custom_map)
    
    assert info["is_workday"] is False
    assert info["target"] == 0.0
    assert info["is_off_day"] is True

def test_day_info_public_holiday():
    # Ein Feiertag (z.B. Weihnachten an einem Montag)
    d = date(2023, 12, 25) 
    settings = MockSettings()
    he_holidays = {d: "Weihnachten"} # Simuliertes holidays Objekt
    custom_map = {}

    info = get_day_info(d, settings, he_holidays, custom_map)
    
    assert info["is_workday"] is False
    assert info["target"] == 0.0
    assert info["holiday_name"] == "Weihnachten"

def test_day_info_custom_holiday_full():
    # Ein eigener freier Tag (z.B. Betriebsausflug)
    d = date(2023, 6, 15)
    settings = MockSettings()
    he_holidays = {}
    # Custom Map erwartet date-Objekt als Key und Objekt mit .hours/.name als Value
    custom_map = {d: MockCustomHoliday("Betriebsausflug", 0.0)}

    info = get_day_info(d, settings, he_holidays, custom_map)
    
    assert info["is_workday"] is False
    assert info["target"] == 0.0
    assert info["holiday_name"] == "Betriebsausflug"

def test_day_info_custom_half_day():
    # Ein halber Tag (z.B. Wäldchestag, 6h Soll)
    d = date(2023, 5, 30)
    settings = MockSettings(weekly_hours=40.0) # Normalziel 8h
    he_holidays = {}
    custom_map = {d: MockCustomHoliday("Wäldchestag", 6.0)}

    info = get_day_info(d, settings, he_holidays, custom_map)
    
    assert info["is_workday"] is True
    assert info["target"] == 6.0
    assert info["holiday_name"] == "Wäldchestag"
    # is_short_day ist True, wenn target < (Wochenstunden/5)
    # Hier: 6.0 < (40/5 = 8.0) -> True
    assert info["is_short_day"] is True

def test_day_info_part_time_model():
    # Benutzer arbeitet nur Mo, Di, Mi (0,1,2)
    d_off = date(2023, 10, 12) # Donnerstag (3)
    d_work = date(2023, 10, 11) # Mittwoch (2)
    
    settings = MockSettings(weekly_hours=24.0, active_weekdays="0,1,2")
    he_holidays = {}
    custom_map = {}

    # Test freier Donnerstag
    info_off = get_day_info(d_off, settings, he_holidays, custom_map)
    assert info_off["is_workday"] is False
    assert info_off["is_off_day"] is True
    assert info_off["target"] == 0.0

    # Test Arbeitstag Mittwoch
    info_work = get_day_info(d_work, settings, he_holidays, custom_map)
    assert info_work["is_workday"] is True
    assert info_work["target"] == 8.0 # 24h / 3 Tage