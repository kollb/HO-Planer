from datetime import datetime, timedelta

def normalize_time_str(t_str):
    """
    Bereinigt Benutzereingaben und macht daraus ein sauberes 'HH:MM' Format.
    """
    if not t_str: return None
    t_str = str(t_str).strip().replace('.', ':')
    
    try:
        h, m = 0, 0
        if ':' in t_str:
            parts = t_str.split(':')
            h, m = int(parts[0]), int(parts[1])
        elif len(t_str) == 4:
            h, m = int(t_str[:2]), int(t_str[2:])
        elif len(t_str) == 3:
            h, m = int(t_str[:1]), int(t_str[1:])
        elif len(t_str) <= 2:
            h, m = int(t_str), 0
        else:
            return None
        
        if h > 23 or m > 59: return None
        return f"{h:02d}:{m:02d}"
    except ValueError:
        return None

def calculate_gross_hours(start_str, end_str):
    """Berechnet die Bruttozeit eines einzelnen Arbeitsblocks."""
    start_str = normalize_time_str(start_str)
    end_str = normalize_time_str(end_str)
    if not start_str or not end_str:
        return 0.0
    try:
        fmt = "%H:%M"
        t_start = datetime.strptime(start_str, fmt)
        t_end = datetime.strptime(end_str, fmt)
        if t_end < t_start:
            t_end += timedelta(days=1)
        return max(0.0, (t_end - t_start).total_seconds() / 3600.0)
    except Exception as error:
        print(f"Fehler bei Zeitberechnung: {error}")
        return 0.0


def calculate_net_hours_from_gross(hours_worked):
    """Wendet die bestehende ArbZG-Pausenkappung auf eine Brutto-Stundensumme an."""
    if hours_worked <= 6.0:
        net_hours = hours_worked
    elif hours_worked <= 6.5:
        net_hours = 6.0
    elif hours_worked <= 9.5:
        net_hours = hours_worked - 0.5
    elif hours_worked <= 9.75:
        net_hours = 9.0
    else:
        net_hours = hours_worked - 0.75
    return max(0.0, round(net_hours, 2))


def calculate_net_hours(start_str, end_str):
    """Berechnet die Nettozeit eines einzelnen Blocks für die Einzelanzeige."""
    return calculate_net_hours_from_gross(calculate_gross_hours(start_str, end_str))


def calculate_daily_net_hours(time_ranges):
    """Berechnet die Nettozeit aus der Summe aller zeitlich erfassten Arbeitsblöcke eines Tages."""
    gross_hours = sum(calculate_gross_hours(start, end) for start, end in time_ranges)
    return calculate_net_hours_from_gross(gross_hours)

def calculate_gross_time_needed(target_net_hours):
    """
    Berechnet nötige Brutto-Anwesenheit für ein Netto-Ziel.
    """
    if target_net_hours <= 6.0:
        return target_net_hours
    elif target_net_hours <= 9.0: 
        # Bis zu einem Ziel von 9,0h Netto reicht eine Pause von 0,5h aus
        return target_net_hours + 0.5
    else:
        # Alles über 9,0h Netto durchbricht zwingend die 9,5h Brutto-Marke -> 0,75h Pause nötig
        return target_net_hours + 0.75

def get_day_info(date_obj, settings, he_holidays, custom_map):
    """
    Liefert Feiertags- und Soll-Stunden-Infos.
    """
    iso_date_str = str(date_obj)
    if date_obj in he_holidays:
        return {
            "is_workday": False,
            "target": 0.0,
            "holiday_name": he_holidays[date_obj],
            "is_short_day": False,
            "is_off_day": False
        }

    active_days_list = [int(x) for x in settings.active_weekdays.split(',') if x.strip().isdigit()] if settings.active_weekdays else []
    regular_daily_target = settings.weekly_hours / len(active_days_list) if active_days_list else 0.0

    cust = custom_map.get(date_obj)
    if cust:
        return {
            "is_workday": cust.hours > 0,
            "target": cust.hours if cust.hours else 0.0,
            "holiday_name": cust.name,
            "is_short_day": cust.hours > 0 and cust.hours < regular_daily_target,
            "is_off_day": False
        }

    weekday = date_obj.weekday()
    
    if weekday not in active_days_list:
        return {
            "is_workday": False,
            "target": 0.0,
            "holiday_name": "",
            "is_short_day": False,
            "is_off_day": True
        }

    daily_target = 0.0
    if len(active_days_list) > 0:
        daily_target = settings.weekly_hours / len(active_days_list)
        
    return {
        "is_workday": True,
        "target": daily_target,
        "holiday_name": "",
        "is_short_day": False,
        "is_off_day": False
    }