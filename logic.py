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

def calculate_net_hours(start_str, end_str):
    """
    Berechnet die Netto-Arbeitszeit. 
    WICHTIG: Zieht Pausen gemäß Arbeitszeitgesetz ab inkl. dynamischer Kappungsgrenzen.
    """
    start_str = normalize_time_str(start_str)
    end_str = normalize_time_str(end_str)
    
    if not start_str or not end_str:
        return 0.0

    try:
        fmt = "%H:%M"
        t_start = datetime.strptime(start_str, fmt)
        t_end = datetime.strptime(end_str, fmt)
        
        if t_end < t_start:
            # Fall für Nachtschicht (falls relevant), sonst passiert hier nichts Schlimmes
            t_end += timedelta(days=1)
            
        diff = t_end - t_start
        # Wichtig: total_seconds gibt float zurück
        hours_worked = diff.total_seconds() / 3600.0
        
        # Pausenkappung nach ArbZG:
        if hours_worked <= 6.0:
            net_hours = hours_worked
        elif hours_worked <= 6.5:
            # Präsenz zwischen 6.0h und 6.5h -> Netto wird auf 6.0h gedeckelt (füllt die 30 Min. Pause)
            net_hours = 6.0
        elif hours_worked <= 9.5:
            # Präsenz bis 9.5h -> 30 Min Pause abziehen (ergibt max. 9.0h Netto)
            net_hours = hours_worked - 0.5
        elif hours_worked <= 9.75:
            # Präsenz zwischen 9.5h und 9.75h -> Netto wird auf 9.0h gedeckelt (füllt die restlichen 15 Min.)
            net_hours = 9.0
        else:
            # Präsenz über 9.75h -> Volle 45 Min Pause abziehen
            net_hours = hours_worked - 0.75
            
        return max(0.0, round(net_hours, 2))
    except Exception as e:
        print(f"Fehler bei Zeitberechnung: {e}") # Logging hilft im Docker Container
        return 0.0

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
    cust = custom_map.get(date_obj)
    if cust:
        return {
            "is_workday": cust.hours > 0,
            "target": cust.hours if cust.hours else 0.0,
            "holiday_name": cust.name,
            "is_short_day": (cust.hours > 0 and cust.hours < (settings.weekly_hours / 5)),
            "is_off_day": False
        }

    if date_obj in he_holidays:
        return {
            "is_workday": False,
            "target": 0.0,
            "holiday_name": he_holidays[date_obj],
            "is_short_day": False,
            "is_off_day": False
        }

    weekday = date_obj.weekday()
    active_days_list = [int(x) for x in settings.active_weekdays.split(',')] if settings.active_weekdays else []
    
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