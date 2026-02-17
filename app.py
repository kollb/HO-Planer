from flask import Flask, jsonify, request
from flask_cors import CORS
from models import db, Settings, CustomHoliday, WorkEntry
from logic import calculate_net_hours, get_day_info, normalize_time_str, calculate_gross_time_needed
import os
from datetime import datetime, timedelta
import holidays
import calendar
from sqlalchemy import text, inspect
import pdfplumber
import re

app = Flask(__name__)
CORS(app)

# --- DB KONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'data', 'database.db')
os.makedirs(os.path.dirname(db_path), exist_ok=True)

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# --- MIGRATION & HELPER ---
def migrate_x_to_planned():
    try:
        with app.app_context():
            old_entries = WorkEntry.query.filter_by(type='x').all()
            if old_entries:
                print(f"INFO: Migriere {len(old_entries)} alte 'X'-Einträge zu 'planned'...")
                for entry in old_entries:
                    entry.type = 'planned'
                db.session.commit()
    except Exception as e:
        print(f"WARNUNG: Migrations-Fehler (X->Planned): {e}")

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
        he_holidays = holidays.DE(state='HE', years=year)
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
        print(f"Auto-Convert Fehler: {e}")

# --- APP STARTUP ---
with app.app_context():
    db.create_all()
    if not db.session.query(Settings).first():
        db.session.add(Settings())
        db.session.commit()
    migrate_x_to_planned()

# --- API ROUTEN ---

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    settings = db.session.query(Settings).first()
    if request.method == 'POST':
        data = request.json
        settings.weekly_hours = float(data.get('weekly_hours', 39))
        active_list = data.get('active_weekdays', [0,1,2,3,4])
        clean_list = [str(i) for i in active_list if isinstance(i, int) and 0 <= i <= 6]
        settings.active_weekdays = ",".join(clean_list)
        settings.ho_quota_percent = int(data.get('ho_quota_percent', 60))
        settings.hide_weekends = bool(data.get('hide_weekends', True))
        settings.default_start_time = normalize_time_str(data.get('default_start_time', '08:00'))
        settings.auto_convert_planned = bool(data.get('auto_convert_planned', True))
        db.session.commit()
        return jsonify({"success": True})
    
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
    
    he_holidays = holidays.DE(state='HE', years=year)
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
                # Zählen wenn Arbeitstag
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
    
    if not entry.type and not entry.start_time:
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
        start_date = datetime.strptime(d['start'], '%Y-%m-%d').date()
        end_date = datetime.strptime(d['end'], '%Y-%m-%d').date()
        weekdays = [int(x) for x in d['weekdays']]
        target_type = d['type']
        overwrite = d.get('overwrite', False)
        
        curr = start_date
        while curr <= end_date:
            if curr.weekday() in weekdays:
                s_date = str(curr)
                he_hols = holidays.DE(state='HE', years=curr.year)
                if curr in he_hols and not (curr.month==12 and curr.day in [24,31]):
                    curr += timedelta(days=1)
                    continue

                existing = WorkEntry.query.filter_by(date=s_date).all()
                if overwrite and existing:
                    for e in existing: db.session.delete(e)
                    existing = []
                
                if not existing:
                    db.session.add(WorkEntry(date=s_date, type=target_type))
            curr += timedelta(days=1)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"ERROR [custom-holidays]: {e}")
        return jsonify({"success": False, "message": "Ein Fehler ist beim Speichern aufgetreten."}), 400

@app.route('/api/custom-holidays', methods=['GET', 'POST'])
def handle_custom_holidays():
    if request.method == 'GET':
        hols = CustomHoliday.query.all()
        return jsonify(sorted([{'id': h.id, 'date': h.date, 'name': h.name, 'hours': h.hours or 0} for h in hols], key=lambda x: x['date']))
    
    data = request.json
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
    if 'file' not in request.files: return jsonify({"success": False, "message": "Keine Datei"}), 400
    file = request.files['file']
    overwrite = request.form.get('overwrite') == 'true'
    
    print(f"--- START IMPORT (Overwrite: {overwrite}) ---")

    TYPE_MAP = {
        "Mobil": "home", "Telearb": "home", "anwesend": "office", 
        "Krank": "sick", "Urlaub": "vacation", "Erholungs": "vacation", "Gleitzeit": "glz", 
        "Dienstreise": "dr", "Fortbildung": "dr", "Reisezeit": "dr"
    }

    try:
        settings = Settings.query.first()
        
        with pdfplumber.open(file) as pdf:
            txt = pdf.pages[0].extract_text()
            match_my = re.search(r'Monat:?\s*([a-zA-ZäöüÄÖÜ]+)\s*[-_]?\s*(\d{4})', txt)
            if not match_my: return jsonify({"success": False, "message": "Monat/Jahr nicht erkannt"}), 400
            m_dict = {'Januar':1,'Februar':2,'März':3,'April':4,'Mai':5,'Juni':6,'Juli':7,'August':8,'September':9,'Oktober':10,'November':11,'Dezember':12}
            m, y = m_dict.get(match_my.group(1)), int(match_my.group(2))
            
            he_holidays = holidays.DE(state='HE', years=y)
            he_holidays[datetime(y, 12, 24).date()] = "Heiligabend"
            he_holidays[datetime(y, 12, 31).date()] = "Silvester"
            custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
            
            daily_data = {}
            
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        if not row or len(row) < 2: continue
                        col0 = str(row[0] or "")
                        dm = re.search(r'(\d{2})\s+(MO|DI|MI|DO|FR|SA|SO)', col0)
                        if not dm: continue     
                        curr_day = int(dm.group(1))
                        if curr_day not in daily_data: daily_data[curr_day] = []
                        full_row_text = " ".join([str(c) for c in row if c])
                        
                        found_type = None
                        for k, v in TYPE_MAP.items():
                            if k in full_row_text: found_type = v
                        
                        times = re.findall(r'(\d{2}:\d{2})', full_row_text)
                        
                        if times and all(t == "00:00" for t in times):
                            times = []

                        if times and len(times) >= 2:
                            t = found_type if found_type else "office"
                            daily_data[curr_day].append({"type": t, "times": times})
                        elif found_type in ["vacation", "sick", "glz"]:
                            daily_data[curr_day].append({"type": found_type, "times": []})

            cnt = 0
            for d, blocks in daily_data.items():
                date_iso = f"{y}-{m:02d}-{d:02d}"
                dt_obj = datetime(y, m, d).date()
                
                day_info = get_day_info(dt_obj, settings, he_holidays, custom_map)
                is_free_day = not day_info["is_workday"]
                
                if d == 1:
                    print(f"DEBUG {date_iso}: is_workday={day_info['is_workday']}, times={[b['times'] for b in blocks]}")

                filtered_blocks = []
                for b in blocks:
                    if len(b['times']) >= 2:
                        filtered_blocks.append(b)
                    elif not is_free_day:
                        filtered_blocks.append(b)
                    else:
                        if d == 1: print(f"DEBUG {date_iso}: Ignoriere '{b['type']}' weil freier Tag.")
                
                blocks = filtered_blocks
                
                if overwrite:
                    WorkEntry.query.filter_by(date=date_iso).delete()
                
                if not blocks:
                    continue

                has_prio = any(b['type'] in ['vacation', 'sick', 'glz'] for b in blocks)
                if has_prio:
                    blocks = [b for b in blocks if b['type'] in ['vacation', 'sick', 'glz']]
                
                for b in blocks:
                    if b['type'] in ['vacation', 'sick', 'glz']:
                        if not overwrite and WorkEntry.query.filter_by(date=date_iso, type=b['type']).first(): continue
                        db.session.add(WorkEntry(date=date_iso, type=b['type']))
                        cnt += 1
                    else:
                        if len(b['times']) >= 2:
                            en = WorkEntry(date=date_iso, type=b['type'])
                            en.start_time = b['times'][0]
                            en.end_time = b['times'][1]
                            db.session.add(en)
                            cnt += 1

            db.session.commit()
            print(f"--- IMPORT FERTIG: {cnt} Einträge ---")
            return jsonify({"success": True, "message": f"{cnt} Einträge importiert."})
            
    except Exception as e: 
        print(f"IMPORT ERROR: {e}")
        return jsonify({"success": False, "message": "Fehler beim Verarbeiten der PDF-Datei."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)