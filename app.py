from flask import Flask, jsonify, request
from flask_cors import CORS
from models import db, Settings, CustomHoliday, WorkEntry
from logic import calculate_net_hours, get_day_info, normalize_time_str, calculate_gross_time_needed
import os
import shutil
import time
from datetime import datetime, date, timedelta
import holidays
import calendar
from sqlalchemy import text, inspect
import pdfplumber
import re
import logging
from logging.handlers import TimedRotatingFileHandler

app = Flask(__name__)
CORS(app)

# --- PFADE & ORDNER (DOCKER OPTIMIERT) ---
basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, 'data')
db_path = os.path.join(data_dir, 'database.db')
log_dir = os.path.join(data_dir, 'logs')
backup_dir = os.path.join(data_dir, 'backups')

# Stelle sicher, dass alle Ordner existieren
for directory in [data_dir, log_dir, backup_dir]:
    os.makedirs(directory, exist_ok=True)

# --- 1. LOGGING KONFIGURATION (Log-Rotation) ---
# Rotiert alle 30 Tage, behält max. 6 alte Dateien (180 Tage)
log_file = os.path.join(log_dir, 'tracker.log')
log_handler = TimedRotatingFileHandler(log_file, when='D', interval=30, backupCount=6)
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# --- DB KONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)


# --- 2. DATENBANK BACKUPS (Backup-Rotation) ---
def perform_daily_backup():
    """Erstellt einmal am Tag ein Backup der SQLite Datenbank und löscht alte Backups (>180 Tage)"""
    today_str = datetime.now().strftime('%Y-%m-%d')
    backup_file = os.path.join(backup_dir, f'db_backup_{today_str}.db')
    
    # Prüfe ob heute schon ein Backup gemacht wurde und ob die DB existiert
    if not os.path.exists(backup_file) and os.path.exists(db_path):
        try:
            shutil.copy2(db_path, backup_file)
            app.logger.info(f"Tägliches Datenbank-Backup erstellt: {backup_file}")
            
            # Aufräumen: Backups älter als 180 Tage löschen
            now = time.time()
            for f in os.listdir(backup_dir):
                f_path = os.path.join(backup_dir, f)
                if os.path.isfile(f_path):
                    # st_mtime = Letztes Änderungsdatum (in Sekunden)
                    if os.stat(f_path).st_mtime < now - (180 * 86400):
                        os.remove(f_path)
                        app.logger.info(f"Altes Backup gelöscht (>180 Tage): {f}")
        except Exception as e:
            app.logger.error(f"Fehler beim DB-Backup: {e}", exc_info=True)

@app.before_request
def before_request_hook():
    # Dieser Check ist extrem schnell und bremst Anfragen nicht aus
    perform_daily_backup()


# --- MIGRATION & HELPER ---
def migrate_x_to_planned():
    try:
        with app.app_context():
            old_entries = WorkEntry.query.filter_by(type='x').all()
            if old_entries:
                app.logger.info(f"Migriere {len(old_entries)} alte 'X'-Einträge zu 'planned'...")
                for entry in old_entries:
                    entry.type = 'planned'
                db.session.commit()
    except Exception as e:
        app.logger.error(f"Migrations-Fehler (X->Planned): {e}")

def auto_convert_expired_planned_days():
    try:
        settings = db.session.query(Settings).first()
        if not settings or not settings.auto_convert_planned:
            return

        today_str = str(datetime.now().date())
        expired_entries = WorkEntry.query.filter(WorkEntry.type == 'planned', WorkEntry.date < today_str).all()
        
        if not expired_entries:
            return 

        year = datetime.now().year
        he_holidays = holidays.DE(subdiv='HE', years=year)
        he_holidays[datetime(year, 12, 24).date()] = "Heiligabend"
        he_holidays[datetime(year, 12, 31).date()] = "Silvester"

        custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
        def_start = settings.default_start_time if settings.default_start_time else "08:00"

        for entry in expired_entries:
            entry.type = 'home'
            if not entry.start_time:
                try:
                    d_obj = datetime.strptime(entry.date, "%Y-%m-%d").date()
                    info = get_day_info(d_obj, settings, he_holidays, custom_map)
                    target = info["target"]
                    
                    if target > 0:
                        entry.start_time = normalize_time_str(def_start)
                        gross_hours = calculate_gross_time_needed(target)
                        
                        sh, sm = map(int, entry.start_time.split(':'))
                        start_minutes = sh * 60 + sm
                        end_minutes = start_minutes + (gross_hours * 60)
                        entry.end_time = f"{int(end_minutes // 60):02d}:{int(end_minutes % 60):02d}"
                except Exception as e:
                    pass
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Auto-Convert Fehler: {e}", exc_info=True)


# --- VALIDIERUNGS-HELPER (3. API Sicherheit) ---
def is_valid_date(date_str):
    return bool(re.match(r'^\d{4}-\d{2}-\d{2}$', str(date_str)))

def is_valid_time(time_str):
    if not time_str: return True
    return bool(re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', str(time_str)))

VALID_TYPES = ['home', 'office', 'dr', 'planned', 'sick', 'vacation', 'glz', '']


# --- APP STARTUP ---
with app.app_context():
    db.create_all()
    if not db.session.query(Settings).first():
        db.session.add(Settings())
        db.session.commit()
    migrate_x_to_planned()
    app.logger.info("Anwendung erfolgreich gestartet.")


# --- REFACTORED LOGIC ---
def parse_pdf_content(file_obj):
    TYPE_MAP = {
        "Mobil": "home", "Telearb": "home", "anwesend": "office", 
        "Krank": "sick", "Urlaub": "vacation", "Erholungs": "vacation", "Gleitzeit": "glz", 
        "Dienstreise": "dr", "Fortbildung": "dr", "Reisezeit": "dr",
        "BUCHUNG FEHLT": "missing"
    }
    extracted_entries = []
    
    with pdfplumber.open(file_obj) as pdf:
        first_page_text = pdf.pages[0].extract_text()
        match_my = re.search(r'Monat:?\s*([a-zA-ZäöüÄÖÜ]+)\s*[-_]?\s*(\d{4})', first_page_text)
        if not match_my:
            raise ValueError("Monat/Jahr im PDF nicht erkannt")
            
        m_dict = {'Januar':1,'Februar':2,'März':3,'April':4,'Mai':5,'Juni':6,'Juli':7,'August':8,'September':9,'Oktober':10,'November':11,'Dezember':12}
        month = m_dict.get(match_my.group(1))
        year = int(match_my.group(2))
        
        daily_data = {}
        curr_day = None

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 2: continue
                    col0 = str(row[0] or "")
                    
                    dm = re.search(r'(\d{2})\s+(MO|DI|MI|DO|FR|SA|SO)', col0)
                    if dm:
                        curr_day = int(dm.group(1))
                    elif curr_day is None:
                        continue

                    if curr_day not in daily_data: daily_data[curr_day] = []
                    
                    full_row_text = " ".join([str(c) for c in row if c])
                    
                    found_type = None
                    for k, v in TYPE_MAP.items():
                        if k in full_row_text: found_type = v
                    
                    times = re.findall(r'(\d{2}:\d{2})', full_row_text)
                    if times and all(t == "00:00" for t in times): times = []

                    entry = {'type': None, 'times': []}
                    if found_type == "missing":
                        entry['type'] = ''
                        entry['comment'] = "Buchung fehlt (PDF)"
                    elif times and len(times) >= 2:
                        entry['type'] = found_type if found_type else "office"
                        entry['times'] = times
                    elif found_type in ["vacation", "sick", "glz"]:
                        entry['type'] = found_type
                    
                    if entry['type'] is not None or entry.get('comment'):
                        daily_data[curr_day].append(entry)

        for d, blocks in daily_data.items():
            try:
                date_obj = date(year, month, d)
                for b in blocks:
                    final_entry = {
                        'date': date_obj,
                        'type': b['type'] or '',
                        'start': b['times'][0] if b['times'] else '',
                        'end': b['times'][1] if b['times'] and len(b['times']) > 1 else '',
                        'comment': b.get('comment', '')
                    }
                    extracted_entries.append(final_entry)
            except ValueError:
                continue
                
    return extracted_entries


# --- API ROUTEN ---

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    settings = db.session.query(Settings).first()
    if request.method == 'POST':
        data = request.json
        if not data: return jsonify({"success": False, "message": "Keine Daten"}), 400
        
        try:
            settings.weekly_hours = float(data.get('weekly_hours', 39))
            active_list = data.get('active_weekdays', [0,1,2,3,4])
            clean_list = [str(i) for i in active_list if isinstance(i, int) and 0 <= i <= 6]
            settings.active_weekdays = ",".join(clean_list)
            settings.ho_quota_percent = int(data.get('ho_quota_percent', 60))
            settings.hide_weekends = bool(data.get('hide_weekends', True))
            
            def_start = data.get('default_start_time', '08:00')
            settings.default_start_time = normalize_time_str(def_start) if def_start else '08:00'
            
            settings.auto_convert_planned = bool(data.get('auto_convert_planned', True))
            db.session.commit()
            return jsonify({"success": True})
        except ValueError:
            return jsonify({"success": False, "message": "Ungültiges Datenformat"}), 400
    
    active_list = [int(x) for x in settings.active_weekdays.split(',')] if settings.active_weekdays else [0,1,2,3,4]
    return jsonify({ 
        "weekly_hours": settings.weekly_hours, 
        "active_weekdays": active_list, 
        "ho_quota_percent": settings.ho_quota_percent,
        "hide_weekends": settings.hide_weekends,
        "default_start_time": settings.default_start_time,
        "auto_convert_planned": settings.auto_convert_planned
    })

@app.route('/api/month/<int:year>/<int:month>', methods=['GET'])
def get_month_data(year, month):
    auto_convert_expired_planned_days()
    settings = db.session.query(Settings).first()
    
    he_holidays = holidays.DE(subdiv='HE', years=year)
    he_holidays[datetime(year, 12, 24).date()] = "Heiligabend"
    he_holidays[datetime(year, 12, 31).date()] = "Silvester"
    custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
    
    month_str = f"{year}-{month:02d}"
    all_entries = WorkEntry.query.filter(WorkEntry.date.startswith(month_str)).all()
    entries_by_date = {}
    for e in all_entries:
        if e.date not in entries_by_date: entries_by_date[e.date] = []
        entries_by_date[e.date].append(e)

    total_ho, total_office, workdays, current_week_sum = 0.0, 0.0, 0, 0.0
    total_target_month = 0.0
    response_items = []
    
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        date_obj = datetime(year, month, day).date()
        date_str = str(date_obj)
        iso_week = date_obj.isocalendar()[1]
        info = get_day_info(date_obj, settings, he_holidays, custom_map)
        
        if info["is_workday"]: 
            workdays += 1
            total_target_month += info["target"]

        day_entries = entries_by_date.get(date_str, [])
        day_net = 0.0
        day_ho_sum = 0.0
        day_office_sum = 0.0
        
        frontend_entries = []
        for e in day_entries:
            hours = 0.0
            if e.type == 'planned': 
                hours = info["target"]
            elif e.type in ["home", "office", "dr"]: 
                hours = calculate_net_hours(e.start_time, e.end_time)
            
            frontend_entries.append({
                "id": e.id, "type": e.type, "start": e.start_time or "", "end": e.end_time or "",
                "net": round(hours, 2), "comment": e.comment or ""
            })
            
            day_net += hours
            if e.type in ["home", "planned"]: day_ho_sum += hours
            elif e.type in ["office", "dr"]: day_office_sum += hours

        total_ho += day_ho_sum
        total_office += day_office_sum
        current_week_sum += day_net
        
        main_type = ""
        if day_entries:
            if day_office_sum > day_ho_sum: main_type = "office"
            elif day_ho_sum > 0: main_type = "home"
            elif any(e.type == 'planned' for e in day_entries): main_type = "planned"
            elif any(e.type == 'sick' for e in day_entries): main_type = "sick"
            elif any(e.type == 'vacation' for e in day_entries): main_type = "vacation"
            else: main_type = day_entries[0].type
        
        response_items.append({
            "row_type": "day", "date": date_str, "day_num": day, "weekday_index": date_obj.weekday(),
            "iso_week": iso_week, "is_holiday": (info["holiday_name"] != "" and not info["is_workday"]),
            "holiday_name": info["holiday_name"], "is_short_day": info["is_short_day"], 
            "is_off_day": info["is_off_day"], "daily_target": info["target"],
            "entries": frontend_entries, "total_net": round(day_net, 2), "main_type": main_type
        })
        
        if date_obj.weekday() == 6 or day == num_days:
            response_items.append({
                "row_type": "summary", "iso_week": iso_week, 
                "sum": round(current_week_sum, 2), "target": settings.weekly_hours
            })
            current_week_sum = 0.0

    max_ho = total_target_month * (settings.ho_quota_percent / 100)
    weeks_count = len([x for x in response_items if x['row_type'] == 'summary'])
    avg_per_week = round((total_ho + total_office) / weeks_count, 2) if weeks_count else 0
    
    return jsonify({
        "items": response_items,
        "stats": {
            "total_ho_made": round(total_ho, 2), "total_office_made": round(total_office, 2),
            "total_work_made": round(total_ho + total_office, 2), "total_ho_allowed": round(max_ho, 2),
            "avg_per_week": avg_per_week, "workdays_month": workdays
        }
    })

@app.route('/api/year/<int:year>', methods=['GET'])
def get_year_data(year):
    settings = db.session.query(Settings).first()
    he_holidays = holidays.DE(state='HE', years=year)
    custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
    
    all_entries = WorkEntry.query.filter(WorkEntry.date.startswith(f"{year}-")).all()
    
    data = []
    for m in range(1, 13):
        m_str = f"{year}-{m:02d}"
        m_entries = [e for e in all_entries if e.date.startswith(m_str)]
        
        ho_h, off_h, wd_count, target_month = 0.0, 0.0, 0, 0.0
        d_ho, d_off, d_vac = set(), set(), set()
        
        num_days = calendar.monthrange(year, m)[1]
        for day in range(1, num_days+1):
            dt = datetime(year, m, day).date()
            inf = get_day_info(dt, settings, he_holidays, custom_map)
            if inf["is_workday"]: 
                wd_count += 1
                target_month += inf["target"]
        
        for e in m_entries:
            h = 0.0
            if e.type == 'planned':
                d_obj = datetime.strptime(e.date, "%Y-%m-%d").date()
                inf = get_day_info(d_obj, settings, he_holidays, custom_map)
                h = inf["target"]
            elif e.type in ['home', 'office', 'dr']:
                h = calculate_net_hours(e.start_time, e.end_time)
            
            if e.type in ['home', 'planned']: 
                ho_h += h
                d_ho.add(e.date)
            elif e.type in ['office', 'dr']: 
                off_h += h
                d_off.add(e.date)
            elif e.type == 'vacation':
                d_obj = datetime.strptime(e.date, "%Y-%m-%d").date()
                if get_day_info(d_obj, settings, he_holidays, custom_map)["is_workday"]:
                    d_vac.add(e.date)
        
        data.append({ 
            "month": m, "workdays": wd_count, "days_ho": len(d_ho), "days_office": len(d_off), 
            "days_vacation": len(d_vac), "ho_hours_made": round(ho_h, 2), 
            "ho_hours_allowed": round(target_month * (settings.ho_quota_percent/100), 2), 
            "office_hours_made": round(off_h, 2) 
        })
    return jsonify(data)

@app.route('/api/entry', methods=['POST'])
def save_entry():
    d = request.json
    if not d: return jsonify({"success": False, "message": "Keine Daten empfangen"}), 400
    
    # Validierung
    if not is_valid_date(d.get('date')):
        return jsonify({"success": False, "message": "Ungültiges Datum"}), 400
    if d.get('type') not in VALID_TYPES:
        return jsonify({"success": False, "message": "Ungültiger Typ"}), 400
    
    if d.get('id'):
        entry = db.session.get(WorkEntry, d.get('id'))
        if not entry: return jsonify({"success": False, "message": "Nicht gefunden"}), 404
    else:
        entry = WorkEntry(date=d.get('date'))
        db.session.add(entry)

    entry.type = d.get('type')
    entry.start_time = normalize_time_str(d.get('start'))
    entry.end_time = normalize_time_str(d.get('end'))
    entry.comment = d.get('comment')
    
    if not entry.type and not entry.start_time and not entry.comment:
         db.session.delete(entry)
         db.session.commit()
         return jsonify({"success": True, "id": None})
    
    db.session.commit()
    return jsonify({"success": True, "id": entry.id})

@app.route('/api/entry/<int:id>', methods=['DELETE'])
def delete_entry(id):
    entry = db.session.get(WorkEntry, id)
    if entry:
        db.session.delete(entry)
        db.session.commit()
    return jsonify({"success": True})

@app.route('/api/plan/series', methods=['POST'])
def plan_series():
    d = request.json
    try:
        if not is_valid_date(d.get('start')) or not is_valid_date(d.get('end')):
            return jsonify({"success": False, "message": "Ungültiger Zeitraum"}), 400
            
        start_date = datetime.strptime(d['start'], '%Y-%m-%d').date()
        end_date = datetime.strptime(d['end'], '%Y-%m-%d').date()
        weekdays = [int(x) for x in d['weekdays']]
        target_type = d.get('type')
        overwrite = d.get('overwrite', False)
        
        if target_type not in VALID_TYPES:
            return jsonify({"success": False, "message": "Ungültiger Typ"}), 400
        
        # --- 4. PERFORMANCE OPTIMIERUNG (N+1 Query fix) ---
        # Hole alle existierenden Einträge in diesem Zeitraum mit EINER Datenbank-Anfrage
        all_existing = WorkEntry.query.filter(WorkEntry.date >= str(start_date), WorkEntry.date <= str(end_date)).all()
        existing_by_date = {}
        for entry in all_existing:
            if entry.date not in existing_by_date:
                existing_by_date[entry.date] = []
            existing_by_date[entry.date].append(entry)
        
        curr = start_date
        while curr <= end_date:
            if curr.weekday() in weekdays:
                s_date = str(curr)
                he_hols = holidays.DE(state='HE', years=curr.year)
                
                if curr in he_hols and not (curr.month==12 and curr.day in [24,31]):
                    curr += timedelta(days=1)
                    continue

                # Suche im RAM statt in der Datenbank
                existing_entries_for_day = existing_by_date.get(s_date, [])
                
                if overwrite and existing_entries_for_day:
                    for e in existing_entries_for_day: 
                        db.session.delete(e)
                    existing_entries_for_day = []
                
                if not existing_entries_for_day:
                    db.session.add(WorkEntry(date=s_date, type=target_type))
            
            curr += timedelta(days=1)
            
        db.session.commit()
        app.logger.info(f"Serienplaner ausgeführt: {start_date} bis {end_date}")
        return jsonify({"success": True})
        
    except Exception as e:
        app.logger.error(f"Fehler im Serienplaner: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Ein Fehler ist beim Speichern aufgetreten."}), 400

@app.route('/api/custom-holidays', methods=['GET', 'POST'])
def handle_custom_holidays():
    if request.method == 'GET':
        hols = CustomHoliday.query.all()
        return jsonify(sorted([{'id': h.id, 'date': h.date, 'name': h.name, 'hours': h.hours or 0} for h in hols], key=lambda x: x['date']))
    
    data = request.json
    if not is_valid_date(data.get('date')):
        return jsonify({"success": False, "message": "Ungültiges Datum"}), 400
        
    if not CustomHoliday.query.filter_by(date=data['date']).first():
        db.session.add(CustomHoliday(date=data['date'], name=data['name'], hours=float(data.get('hours', 0))))
        db.session.commit()
    return jsonify({"success": True})

@app.route('/api/custom-holidays/<int:id>', methods=['DELETE'])
def delete_custom_holiday(id):
    h = db.session.get(CustomHoliday, id)
    if h: 
        db.session.delete(h)
        db.session.commit()
    return jsonify({"success": True})

@app.route('/api/import/pdf', methods=['POST'])
def import_pdf():
    if 'file' not in request.files: 
        return jsonify({"success": False, "message": "Keine Datei"}), 400
        
    file = request.files['file']
    overwrite = request.form.get('overwrite') == 'true'
    
    app.logger.info(f"--- START IMPORT (Overwrite: {overwrite}) ---")

    try:
        settings = Settings.query.first()
        extracted_entries = parse_pdf_content(file)
        
        if not extracted_entries:
             app.logger.info("PDF Import: Keine Einträge gefunden.")
             return jsonify({"success": True, "message": "Keine Einträge gefunden."})
             
        y = extracted_entries[0]['date'].year
        he_holidays = holidays.DE(state='HE', years=y)
        he_holidays[datetime(y, 12, 24).date()] = "Heiligabend"
        he_holidays[datetime(y, 12, 31).date()] = "Silvester"
        custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}

        cnt = 0
        entries_by_date = {}
        for e in extracted_entries:
            d = e['date']
            if d not in entries_by_date: entries_by_date[d] = []
            entries_by_date[d].append(e)
            
        for date_obj, entries in entries_by_date.items():
            date_iso = str(date_obj)
            day_info = get_day_info(date_obj, settings, he_holidays, custom_map)
            is_free_day = not day_info["is_workday"]
            
            valid_entries = []
            for e in entries:
                has_times = bool(e['start'] and e['end'])
                has_comment = bool(e['comment'])
                if has_times or not is_free_day or has_comment:
                    valid_entries.append(e)
            
            if not valid_entries: continue
            
            if overwrite:
                WorkEntry.query.filter_by(date=date_iso).delete()
            
            for e in valid_entries:
                if not overwrite:
                    if e['type'] and WorkEntry.query.filter_by(date=date_iso, type=e['type']).first():
                        continue
                
                en = WorkEntry(date=date_iso, type=e['type'])
                en.start_time = e['start']
                en.end_time = e['end']
                en.comment = e['comment']
                db.session.add(en)
                cnt += 1

        db.session.commit()
        app.logger.info(f"--- IMPORT FERTIG: {cnt} Einträge ---")
        return jsonify({"success": True, "message": f"{cnt} Einträge importiert."})
            
    except Exception as e: 
        app.logger.error(f"IMPORT ERROR: {e}", exc_info=True)
        return jsonify({"success": False, "message": "Ein interner Fehler ist beim Import aufgetreten. Bitte prüfen Sie die Logs."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)