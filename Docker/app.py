#1805206

from flask import Flask, Response, jsonify, redirect, request, send_file, url_for
from werkzeug.exceptions import RequestEntityTooLarge
from models import db, Settings, CustomHoliday, WorkEntry
from logic import calculate_daily_net_hours, calculate_gross_hours, get_day_info, normalize_time_str, calculate_gross_time_needed
import json
import math
import os
import sqlite3
import time
from datetime import datetime, date, timedelta
import holidays
import calendar
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError
import pdfplumber
import re
import logging
from logging.handlers import TimedRotatingFileHandler
from zoneinfo import ZoneInfo

app = Flask(__name__)

# --- PFADE & ORDNER (DOCKER OPTIMIERT) ---
basedir = os.path.abspath(os.path.dirname(__file__))
# Die Standardpfade bleiben für bestehende Docker-Volumes unverändert. Test- und
# Wartungsprozesse können ein vollständig separates Datenverzeichnis übergeben.
data_dir = os.path.abspath(os.environ.get('HO_PLANER_DATA_DIR', os.path.join(basedir, 'data')))
db_path = os.path.abspath(os.environ.get('HO_PLANER_DB_PATH', os.path.join(data_dir, 'database.db')))
log_dir = os.path.abspath(os.environ.get('HO_PLANER_LOG_DIR', os.path.join(data_dir, 'logs')))
backup_dir = os.path.abspath(os.environ.get('HO_PLANER_BACKUP_DIR', os.path.join(data_dir, 'backups')))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 31

for directory in [data_dir, os.path.dirname(db_path), log_dir, backup_dir]:
    os.makedirs(directory, exist_ok=True)

# --- LOGGING ---
log_file = os.path.join(log_dir, 'tracker.log')
log_handler = TimedRotatingFileHandler(log_file, when='D', interval=30, backupCount=6)
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
app.logger.addHandler(log_handler)
app.logger.setLevel(logging.INFO)

# --- DB KONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}?timeout=15'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_BYTES
db.init_app(app)

def get_local_now():
    return datetime.now(ZoneInfo("Europe/Berlin"))

# --- DATENBANK BACKUPS (PERFORMANCE OPTIMIERT) ---
# Globaler RAM-Cache, um Festplatten-I/O bei jedem Request zu vermeiden
LAST_BACKUP_DATE_STR = None

def create_sqlite_backup(backup_file):
    """Erstellt eine konsistente SQLite-Sicherung, auch wenn die Datenbank gerade genutzt wird."""
    if not os.path.exists(db_path):
        return False

    source = destination = None
    try:
        source = sqlite3.connect(db_path)
        destination = sqlite3.connect(backup_file)
        source.backup(destination)
        return True
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()


def perform_daily_backup():
    global LAST_BACKUP_DATE_STR
    today_str = str(get_local_now().date())

    if LAST_BACKUP_DATE_STR == today_str:
        return

    backup_file = os.path.join(backup_dir, f'db_backup_{today_str}.db')
    if not os.path.exists(backup_file) and os.path.exists(db_path):
        try:
            if create_sqlite_backup(backup_file):
                app.logger.info(f"Tägliches Datenbank-Backup erstellt: {backup_file}")
                now = time.time()
                for f in os.listdir(backup_dir):
                    f_path = os.path.join(backup_dir, f)
                    if os.path.isfile(f_path) and os.stat(f_path).st_mtime < now - (180 * 86400):
                        os.remove(f_path)
                        app.logger.info(f"Altes Backup gelöscht (>180 Tage): {f}")
                LAST_BACKUP_DATE_STR = today_str
        except Exception as e:
            app.logger.error(f"Fehler beim DB-Backup: {e}", exc_info=True)
    else:
        LAST_BACKUP_DATE_STR = today_str

@app.before_request
def before_request_hook():
    perform_daily_backup()

# --- MIGRATION & HELPER ---
def migrate_x_to_planned():
    try:
        with app.app_context():
            old_entries = WorkEntry.query.filter_by(type='x').all()
            if old_entries:
                for entry in old_entries: entry.type = 'planned'
                db.session.commit()
    except Exception as e:
        app.logger.error(f"Migrations-Fehler (X->Planned): {e}")

def auto_convert_expired_planned_days():
    try:
        settings = db.session.query(Settings).first()
        if not settings or not settings.auto_convert_planned: return

        today_str = str(get_local_now().date())
        expired_entries = WorkEntry.query.filter(WorkEntry.type == 'planned', WorkEntry.date < today_str).all()
        if not expired_entries: return 

        year = get_local_now().year
        he_holidays = hessen_holidays(settings, year)
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
                except Exception:
                    pass
        db.session.commit()
    except Exception as e:
        app.logger.error(f"Auto-Convert Fehler: {e}", exc_info=True)

def is_valid_date(date_str):
    if not isinstance(date_str, str) or not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return False
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def is_valid_time(time_str):
    return time_str == '' or (isinstance(time_str, str) and bool(re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', time_str)))


def finite_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalized_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', '1', 'yes', 'on'):
            return True
        if normalized in ('false', '0', 'no', 'off'):
            return False
    return None


def normalized_weekdays(value):
    if not isinstance(value, list):
        return None
    if any(isinstance(day, bool) or not isinstance(day, int) or day < 0 or day > 6 for day in value):
        return None
    if not value or len(set(value)) != len(value):
        return None
    return value


VALID_TYPES = ['home', 'office', 'dr', 'planned', 'sick', 'vacation', 'glz', '']
VALID_GLZ_OVERRIDE_SOURCES = {'manual', 'pdf', None}


# Die Feiertagsbibliothek benennt drei Tage anders als die Standalone-Variante.
# Beide Oberflächen müssen denselben Namen anzeigen, deshalb werden sie auf die
# im Sprachgebrauch übliche Schreibweise normalisiert. Verbindlich ist der
# gemeinsame Kalender in shared/test-cases/holidays-calendar.json.
CANONICAL_HOLIDAY_NAMES = {
    'Erster Mai': 'Tag der Arbeit',
    'Erster Weihnachtstag': '1. Weihnachtstag',
    'Zweiter Weihnachtstag': '2. Weihnachtstag',
}


def hessen_holidays(settings, years):
    """Liefert die hessischen Feiertage inklusive optionaler Jahresendregel."""
    # Ein einfaches dict statt der HolidayBase: Letztere hängt bei einer
    # Zuweisung auf ein belegtes Datum den neuen Namen an den bestehenden an
    # ("Erster Mai; Tag der Arbeit"), statt ihn zu ersetzen.
    holiday_map = {
        day: CANONICAL_HOLIDAY_NAMES.get(name, name)
        for day, name in holidays.DE(subdiv='HE', years=years).items()
    }
    if getattr(settings, 'christmas_eve_and_new_years_eve_off', True):
        for year in (years if isinstance(years, (list, tuple, range, set)) else [years]):
            holiday_map[date(year, 12, 24)] = 'Heiligabend'
            holiday_map[date(year, 12, 31)] = 'Silvester'
    return holiday_map

# --- SCHEMA-SELBSTHEILUNG BEIM START ---
# db.create_all() legt nur fehlende Tabellen an, ergänzt aber keine Spalten in
# bestehenden Tabellen. Ohne die folgende Absicherung bricht jede ORM-Abfrage auf
# einer älteren Datenbank mit „no such column“ ab – noch bevor migrate.py laufen
# kann, denn migrate.py importiert dieses Modul (Henne-Ei-Problem beim Import).
# Deshalb werden hier vor dem ersten ORM-Zugriff alle rein additiven,
# datenverlustfreien Spalten idempotent ergänzt. migrate.py bleibt für
# versionierte, strukturelle Eingriffe (Tabellenumbau, Dublettenbereinigung,
# Indexe) mit vorherigem Backup zuständig und nutzt dieselben Spaltendefinitionen.
# Alle Namen sind fest verdrahtete Konstanten, keine Nutzereingaben.
ADDITIVE_SCHEMA_COLUMNS = {
    "settings": (
        ("christmas_eve_and_new_years_eve_off", "BOOLEAN NOT NULL DEFAULT 1"),
        ("theme", "VARCHAR(10) NOT NULL DEFAULT 'dark'"),
    ),
    "work_entry": (
        ("glz_override", "FLOAT"),
        ("glz_override_source", "VARCHAR(20)"),
    ),
}


def ensure_additive_schema_columns(engine=None):
    """Ergänzt fehlende Spalten bestehender Tabellen, ohne Daten zu verändern."""
    engine = engine if engine is not None else db.engine
    with engine.begin() as conn:
        for table, columns in ADDITIVE_SCHEMA_COLUMNS.items():
            if not inspect(conn).has_table(table):
                continue
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
            for column, ddl in columns:
                if column in existing:
                    continue
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                except OperationalError as error:
                    # Mehrere Gunicorn-Worker starten gleichzeitig: Hat ein anderer
                    # Worker die Spalte soeben ergänzt, ist das kein Fehler.
                    if "duplicate column" not in str(error).lower():
                        raise
                    continue
                app.logger.info("[Init] Spalte ergänzt: %s.%s", table, column)


def init_db():
    """Legt Schema und Standarddatensatz an; verträgt auch alte Datenbanken."""
    db.create_all()
    ensure_additive_schema_columns()
    if not db.session.query(Settings).first():
        db.session.add(Settings())
        db.session.commit()
    migrate_x_to_planned()


with app.app_context():
    init_db()

# --- GLZ CARRYOVER LOGIK ---
def get_glz_carryover(year, month, settings, custom_map):
    target_date = date(year, month, 1) - timedelta(days=1)
    
    # Bei mehreren Ankern am selben Datum ist der zuletzt gespeicherte Eintrag
    # maßgeblich. Die ID macht diese Regel unabhängig von der DB-Standardreihenfolge.
    last_override = WorkEntry.query.filter(
        WorkEntry.date <= str(target_date),
        WorkEntry.glz_override.isnot(None)
    ).order_by(WorkEntry.date.desc(), WorkEntry.id.desc()).first()
    
    if last_override:
        running_glz = last_override.glz_override
        start_date = datetime.strptime(last_override.date, "%Y-%m-%d").date() + timedelta(days=1)
    else:
        running_glz = 0.0
        first_entry = WorkEntry.query.filter(
            WorkEntry.date >= f"{year}-01-01",
            WorkEntry.date <= str(target_date)
        ).order_by(WorkEntry.date.asc()).first()
        if not first_entry: return 0.0
        start_date = datetime.strptime(first_entry.date, "%Y-%m-%d").date()
        
    if start_date > target_date:
        return running_glz

    entries_in_range = WorkEntry.query.filter(
        WorkEntry.date >= str(start_date),
        WorkEntry.date <= str(target_date)
    ).all()
    
    entries_by_date = {}
    for e in entries_in_range:
        if e.date not in entries_by_date: entries_by_date[e.date] = []
        entries_by_date[e.date].append(e)
        
    years = list(range(start_date.year, target_date.year + 1))
    he_hols = hessen_holidays(settings, years)
        
    today_str = str(get_local_now().date())
        
    curr = start_date
    while curr <= target_date:
        info = get_day_info(curr, settings, he_hols, custom_map)
        day_entries = entries_by_date.get(str(curr), [])
        
        is_future = str(curr) > today_str
        
        timed_entries = [
            e for e in day_entries
            if e.type in ["planned", "home", "office", "dr"] and e.start_time and e.end_time
        ]
        day_net = calculate_daily_net_hours([(e.start_time, e.end_time) for e in timed_entries])
        for e in day_entries:
            if e.type == 'planned' and not (e.start_time and e.end_time):
                day_net += info["target"]
            elif e.type in ["home", "office", "dr"] and not (e.start_time and e.end_time) and is_future:
                day_net += info["target"]
        
        is_paid_leave = any(e.type in ['sick', 'vacation'] for e in day_entries)
        is_glz_day = any(e.type == 'glz' for e in day_entries)
        is_empty = len(day_entries) == 0 or all(not e.type for e in day_entries)
        
        day_delta = 0.0
        if info["is_workday"]:
            if is_paid_leave: day_delta = day_net
            elif is_glz_day: day_delta = day_net - info["target"]
            elif is_empty and is_future: day_delta = 0.0 
            else: day_delta = day_net - info["target"]
        else:
            day_delta = day_net
            
        running_glz += day_delta
        curr += timedelta(days=1)
        
    return running_glz

# --- PDF PARSER (V3 - konservative, nachvollziehbare Interpretation) ---
PDF_TYPE_RULES = (
    (r'\bbuchung\s+fehlt\b', 'missing'), (r'\bbetriebsausflug\b', 'office'),
    (r'\bdienstreise\b|\bfortbildung\b|\breise\b', 'dr'),
    (r'\bkrank(?:\s+im\s+dienst)?\b', 'sick'),
    (r'\berholungs\w*|\burlaub\b|\bzusatz\w*|\bsonder\w*', 'vacation'),
    (r'\bgleitzeit\b|\bglz\b', 'glz'), (r'\bmobil\b|\btelearb\w*', 'home'),
    (r'\banwesend\b', 'office'),
)
PDF_DATE_PATTERN = re.compile(r'\b(\d{2})\s+(MO|DI|MI|DO|FR|SA|SO)\b', re.IGNORECASE)
PDF_TIME_PATTERN = re.compile(r'\b([01]\d|2[0-3]):([0-5]\d)\b')
PDF_GLZ_PATTERN = re.compile(r'-?\d{1,3}[.,]\d{2}\b')
PDF_GLZ_CONTEXT_PATTERN = re.compile(r'\b(zeitkonto|gleitzeit|glz|saldo)\b', re.IGNORECASE)


def pdf_times_from_row(row_text):
    """Liest die Uhrzeiten einer PDF-Zeile und erhält dabei Nachtschichten.

    In den Zeitnachweisen steht ``00:00`` in zwei Bedeutungen: als leerer
    Platzhalter einer unbebuchten Spalte und als echte Mitternachtsgrenze einer
    Nachtschicht. Ein pauschaler Filter verwarf bisher beides und ließ damit von
    ``22:00 00:00`` nur einen einzelnen Wert übrig, der anschließend als ungerade
    Zeitfolge komplett entfiel. Verworfen werden deshalb nur Zeilen, die
    ausschließlich aus Platzhaltern bestehen.
    """
    times = [f"{hour}:{minute}" for hour, minute in PDF_TIME_PATTERN.findall(row_text)]
    if all(value == '00:00' for value in times):
        return []
    return times


def _pdf_type_for_text(text):
    return next((entry_type for pattern, entry_type in PDF_TYPE_RULES if re.search(pattern, text, re.IGNORECASE)), None)


def _pdf_glz_for_row(text, known_glz_column, report, day):
    candidates = PDF_GLZ_PATTERN.findall(text)
    if not candidates:
        return None
    if not (known_glz_column or PDF_GLZ_CONTEXT_PATTERN.search(text)):
        report['warnings'].append(f"Tag {day:02d}: Dezimalwert ohne GLZ-Kontext nicht übernommen.")
        return None
    if len(candidates) > 1:
        report['warnings'].append(f"Tag {day:02d}: mehrere GLZ-Kandidaten; letzter Wert wird verwendet.")
    return float(candidates[-1].replace(',', '.'))


def parse_pdf_content(file_obj, include_report=False):
    """Extrahiert PDF-Buchungen, ohne Arbeitszeit-, Pausen- oder GLZ-Regeln zu verändern."""
    extracted_entries = []
    report = {'pages': 0, 'recognized_month': None, 'recognized_rows': 0, 'importable_entries': 0, 'warnings': []}
    with pdfplumber.open(file_obj) as pdf:
        if not pdf.pages:
            raise ValueError("PDF enthält keine Seiten.")
        if len(pdf.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF enthält mehr als {MAX_PDF_PAGES} Seiten.")
        report['pages'] = len(pdf.pages)
        first_page_text = pdf.pages[0].extract_text() or ""
        match_my = re.search(r'Monat:?\s*([a-zA-ZäöüÄÖÜ]+)\s*[-_]?\s*(\d{4})', first_page_text, re.IGNORECASE)
        if not match_my:
            raise ValueError("Monat/Jahr im PDF nicht erkannt.")
        months = {'januar': 1, 'februar': 2, 'maerz': 3, 'april': 4, 'mai': 5, 'juni': 6, 'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12}
        month = months.get(match_my.group(1).lower().replace('ä', 'ae'))
        year = int(match_my.group(2))
        if not month:
            raise ValueError(f"Unbekannter Monat: {match_my.group(1)}")
        report['recognized_month'] = f"{year:04d}-{month:02d}"
        daily_data = {}
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            rows = [row for table in (page.extract_tables() or []) for row in table if row]
            if not rows:
                rows = [[line] for line in page_text.splitlines()]
                if page_text.strip():
                    report['warnings'].append('Text-Fallback verwendet, weil keine Tabelle erkannt wurde.')
            current_day = None
            for row in rows:
                row_text = " ".join(str(cell).replace('\n', ' ') for cell in row if cell).strip()
                if not row_text or row_text.startswith('Tag '):
                    continue
                if 'Wochensumme' in row_text or 'Kontingent' in row_text:
                    current_day = None
                    continue
                date_match = PDF_DATE_PATTERN.search(row_text)
                if date_match:
                    current_day = int(date_match.group(1))
                    if current_day > calendar.monthrange(year, month)[1]:
                        report['warnings'].append(f"Ungültiger Kalendertag {current_day:02d} verworfen.")
                        current_day = None
                        continue
                    report['recognized_rows'] += 1
                elif current_day is None or 'Zeitkonto' in row_text:
                    continue
                blocks = daily_data.setdefault(current_day, [])
                found_type = _pdf_type_for_text(row_text)
                times = pdf_times_from_row(row_text)
                glz_override = _pdf_glz_for_row(row_text, bool(PDF_GLZ_CONTEXT_PATTERN.search(page_text)), report, current_day) if date_match else None
                if found_type == 'missing':
                    blocks.append({'type': '', 'times': [], 'glz_override': None, 'comment': '⚠️ Buchung fehlt'})
                    continue
                if len(times) % 2:
                    report['warnings'].append(f"Tag {current_day:02d}: ungerade Anzahl von Uhrzeiten; letzter Wert verworfen.")
                    times = times[:-1]
                if len(times) >= 2:
                    entry_type = found_type or ''
                    comment = 'Betriebsausflug' if 'betriebsausflug' in row_text.lower() else ''
                    if not entry_type:
                        comment = '⚠️ PDF-Prüfung erforderlich: unbekannter Status'
                        report['warnings'].append(f"Tag {current_day:02d}: unbekannter Status; Zeiten als Prüfeintrag übernommen.")
                        report['warnings'].append(f"Tag {current_day:02d}: Eintrag mit unbekannten Status prüfen.")
                    for index in range(0, len(times), 2):
                        start_time, end_time = times[index], times[index + 1]
                        blocks.append({'type': entry_type, 'times': [start_time, end_time], 'glz_override': glz_override if index == 0 and not blocks else None, 'comment': comment})
                elif found_type in ('vacation', 'sick', 'glz'):
                    blocks.append({'type': found_type, 'times': [], 'glz_override': glz_override if not blocks else None, 'comment': ''})
                elif glz_override is not None and not blocks:
                    blocks.append({'type': '', 'times': [], 'glz_override': glz_override, 'comment': ''})
        for day, blocks in daily_data.items():
            for block in blocks:
                extracted_entries.append({'date': date(year, month, day), 'type': block['type'] or '', 'start': block['times'][0] if block['times'] else '', 'end': block['times'][1] if len(block['times']) > 1 else '', 'comment': block.get('comment', ''), 'glz_override': block.get('glz_override')})
    report['importable_entries'] = len(extracted_entries)
    if not extracted_entries:
        report['warnings'].append('Keine importierbaren Tagesbuchungen erkannt.')
    return (extracted_entries, report) if include_report else extracted_entries

def pdf_block_identity(entry):
    """Identifiziert einen PDF-Zeitblock unabhängig von Kommentar und GLZ-Anker."""
    if isinstance(entry, dict):
        return (
            entry.get('type', '') or '',
            entry.get('start_time', entry.get('start', '')) or '',
            entry.get('end_time', entry.get('end', '')) or '',
        )
    return (
        getattr(entry, 'type', '') or '',
        getattr(entry, 'start_time', getattr(entry, 'start', '')) or '',
        getattr(entry, 'end_time', getattr(entry, 'end', '')) or '',
    )


def merge_pdf_entries(existing_entries, pdf_entries):
    """Führt PDF-Blöcke additiv zusammen und bewahrt manuelle Daten vor Überschreiben."""
    result = {
        'entries_to_add': [],
        'skipped_duplicates': 0,
        'comment_hints': 0,
        'glz_override_conflicts': 0,
    }
    existing_by_identity = {pdf_block_identity(entry): entry for entry in existing_entries}
    known_identities = set(existing_by_identity)
    existing_glz = next((entry.glz_override for entry in existing_entries if entry.glz_override is not None), None)

    for pdf_entry in pdf_entries:
        identity = pdf_block_identity(pdf_entry)
        existing = existing_by_identity.get(identity)
        if identity in known_identities:
            result['skipped_duplicates'] += 1
            if existing:
                pdf_comment = pdf_entry.get('comment', '')
                if not (existing.comment or '') and pdf_comment:
                    existing.comment = pdf_comment
                    result['comment_hints'] += 1
                elif (existing.comment or '') and pdf_comment and existing.comment != pdf_comment:
                    result['comment_hints'] += 1
                if pdf_entry.get('glz_override') is not None and existing_glz is not None and existing_glz != pdf_entry['glz_override']:
                    result['glz_override_conflicts'] += 1
            continue

        entry_to_add = dict(pdf_entry)
        if entry_to_add.get('glz_override') is not None and existing_glz is not None and existing_glz != entry_to_add['glz_override']:
            entry_to_add['glz_override'] = None
            result['glz_override_conflicts'] += 1
        elif entry_to_add.get('glz_override') is not None:
            existing_glz = entry_to_add['glz_override']
        result['entries_to_add'].append(entry_to_add)
        existing_by_identity[identity] = None
        known_identities.add(identity)

    return result


# --- API ROUTEN ---
@app.route('/')
def index():
    root_path = os.path.join(basedir, 'index.html')
    if os.path.exists(root_path): return send_file(root_path)
    return app.send_static_file('index.html')

@app.route('/beta')
def beta_index():
    return redirect(url_for('index'))

@app.route('/api/settings', methods=['GET', 'POST'])
def handle_settings():
    settings = db.session.query(Settings).first()
    if request.method == 'POST':
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"success": False, "message": "Ungültiger Request-Body"}), 400

        weekly_hours = finite_number(data.get('weekly_hours', settings.weekly_hours))
        ho_quota = finite_number(data.get('ho_quota_percent', settings.ho_quota_percent))
        active_list = normalized_weekdays(data.get('active_weekdays', [int(day) for day in settings.active_weekdays.split(',') if day]))
        hide_weekends = normalized_bool(data.get('hide_weekends', settings.hide_weekends))
        auto_convert_planned = normalized_bool(data.get('auto_convert_planned', settings.auto_convert_planned))
        year_end_off = normalized_bool(data.get('christmas_eve_and_new_years_eve_off', getattr(settings, 'christmas_eve_and_new_years_eve_off', True)))
        theme = data.get('theme', getattr(settings, 'theme', 'dark'))
        default_start = data.get('default_start_time', settings.default_start_time)
        normalized_start = normalize_time_str(default_start) if default_start else None

        if weekly_hours is None or weekly_hours <= 0:
            return jsonify({"success": False, "message": "Ungültige Wochenstunden"}), 400
        if ho_quota is None or not 0 <= ho_quota <= 100:
            return jsonify({"success": False, "message": "Ungültige Home-Office-Quote"}), 400
        if active_list is None:
            return jsonify({"success": False, "message": "Ungültige aktive Wochentage"}), 400
        if hide_weekends is None or auto_convert_planned is None or year_end_off is None:
            return jsonify({"success": False, "message": "Ungültiger Wahrheitswert"}), 400
        if theme not in ('dark', 'light'):
            return jsonify({"success": False, "message": "Ungültiges Theme"}), 400
        if normalized_start is None:
            return jsonify({"success": False, "message": "Ungültige Standardstartzeit"}), 400

        settings.weekly_hours = weekly_hours
        settings.active_weekdays = ",".join(str(day) for day in active_list)
        settings.ho_quota_percent = ho_quota
        settings.hide_weekends = hide_weekends
        settings.default_start_time = normalized_start
        settings.auto_convert_planned = auto_convert_planned
        settings.christmas_eve_and_new_years_eve_off = year_end_off
        settings.theme = theme
        db.session.commit()
        return jsonify({"success": True})
    
    active_list = [int(x) for x in settings.active_weekdays.split(',')] if settings.active_weekdays else [0,1,2,3,4]
    return jsonify({ 
        "weekly_hours": settings.weekly_hours, 
        "active_weekdays": active_list, 
        "ho_quota_percent": settings.ho_quota_percent,
        "hide_weekends": settings.hide_weekends,
        "default_start_time": settings.default_start_time,
        "auto_convert_planned": settings.auto_convert_planned,
        "christmas_eve_and_new_years_eve_off": getattr(settings, 'christmas_eve_and_new_years_eve_off', True),
        "theme": getattr(settings, 'theme', 'dark')
    })

@app.route('/api/month/<int:year>/<int:month>', methods=['GET'])
def get_month_data(year, month):
    auto_convert_expired_planned_days()
    settings = db.session.query(Settings).first()
    
    he_holidays = hessen_holidays(settings, year)
    custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
    
    month_str = f"{year}-{month:02d}"
    today_str = str(get_local_now().date())
    
    all_entries = WorkEntry.query.filter(WorkEntry.date.startswith(month_str)).all()
    entries_by_date = {}
    for e in all_entries:
        if e.date not in entries_by_date: entries_by_date[e.date] = []
        entries_by_date[e.date].append(e)

    total_ho, total_office, workdays, current_week_sum = 0.0, 0.0, 0, 0.0
    current_week_target = 0.0
    total_target_hours_month = 0.0 
    response_items = []
    # Die Wochenzusammenfassung steht als Abschnittskopf VOR den Tagen ihrer Woche.
    # Gesammelt werden die Tage deshalb bis zum Wochenende und dann nach dem Kopf
    # ausgegeben.
    week_days = []
    week_iso = None
    
    running_glz = get_glz_carryover(year, month, settings, custom_map)
    num_days = calendar.monthrange(year, month)[1]
    
    for day in range(1, num_days + 1):
        date_obj = date(year, month, day)
        date_str = str(date_obj)
        iso_week = date_obj.isocalendar()[1]
        info = get_day_info(date_obj, settings, he_holidays, custom_map)
        
        is_future = date_str > today_str
        
        if info["is_workday"]: 
            workdays += 1
            total_target_hours_month += info["target"]
            
        current_week_target += info["target"]

        day_entries = entries_by_date.get(date_str, [])
        day_net = 0.0
        day_ho_sum = 0.0
        day_office_sum = 0.0
        day_override = None
        day_override_source = None
        
        timed_entries = [
            e for e in day_entries
            if e.type in ["planned", "home", "office", "dr"] and e.start_time and e.end_time
        ]
        timed_gross_hours = sum(calculate_gross_hours(e.start_time, e.end_time) for e in timed_entries)
        timed_net_hours = calculate_daily_net_hours([(e.start_time, e.end_time) for e in timed_entries])
        frontend_entries = []
        for e in day_entries:
            hours = 0.0
            if e in timed_entries and timed_gross_hours > 0:
                hours = timed_net_hours * calculate_gross_hours(e.start_time, e.end_time) / timed_gross_hours
            elif e.type == 'planned':
                hours = info["target"]
            elif e.type in ["home", "office", "dr"] and is_future:
                hours = info["target"]
            
            glz_over = getattr(e, 'glz_override', None)
            glz_source = getattr(e, 'glz_override_source', None)
            
            if glz_over is not None: 
                day_override = glz_over
                day_override_source = glz_source

            frontend_entries.append({
                "id": e.id, "type": e.type, "start": e.start_time or "", "end": e.end_time or "",
                "net": round(hours, 2), "comment": e.comment or "", 
                "glz_override": glz_over,
                "glz_override_source": glz_source
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
            
        day_delta = 0.0
        is_paid_leave = any(e.type in ['sick', 'vacation'] for e in day_entries)
        is_glz_day = any(e.type == 'glz' for e in day_entries)
        is_empty = len(day_entries) == 0 or all(not e.type for e in day_entries)
        
        if info["is_workday"]:
            if is_paid_leave: day_delta = day_net
            elif is_glz_day: day_delta = day_net - info["target"]
            elif is_empty and is_future: day_delta = 0.0
            else: day_delta = day_net - info["target"]
        else:
            day_delta = day_net

        running_glz += day_delta
        if day_override is not None: running_glz = day_override
        
        if not week_days:
            week_iso = iso_week
        week_days.append({
            "row_type": "day", "date": date_str, "day_num": day, "weekday_index": date_obj.weekday(),
            "iso_week": iso_week, "is_holiday": (info["holiday_name"] != "" and not info["is_workday"]),
            "holiday_name": info["holiday_name"], "is_short_day": info["is_short_day"], 
            "is_off_day": info["is_off_day"], "daily_target": info["target"],
            "entries": frontend_entries, "total_net": round(day_net, 2), "main_type": main_type,
            "glz_saldo": round(running_glz, 2), "glz_override": day_override,
            "glz_override_source": day_override_source,
            "day_delta": round(day_delta, 2)
        })
        
        if date_obj.weekday() == 6 or day == num_days:
            if current_week_target > 0 or current_week_sum > 0:
                response_items.append({
                    "row_type": "summary", "iso_week": week_iso if week_iso is not None else iso_week,
                    "sum": round(current_week_sum, 2), "target": round(current_week_target, 2)
                })
            response_items.extend(week_days)
            week_days = []
            week_iso = None
            current_week_sum = 0.0
            current_week_target = 0.0

    max_ho = total_target_hours_month * (settings.ho_quota_percent / 100)
    weeks_count = len([x for x in response_items if x['row_type'] == 'summary'])
    avg_per_week = round((total_ho + total_office) / weeks_count, 2) if weeks_count else 0
    
    return jsonify({
        "items": response_items,
        "stats": {
            "total_ho_made": round(total_ho, 2), "total_office_made": round(total_office, 2),
            "total_work_made": round(total_ho + total_office, 2), "total_ho_allowed": round(max_ho, 2),
            "work_hours_target": round(total_target_hours_month, 2),
            "avg_per_week": avg_per_week, "workdays_month": workdays, "current_glz": round(running_glz, 2)
        }
    })

@app.route('/api/year/<int:year>', methods=['GET'])
def get_year_data(year):
    settings = db.session.query(Settings).first()
    he_holidays = hessen_holidays(settings, year)
    custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}
    
    today_str = str(get_local_now().date())
    all_entries = WorkEntry.query.filter(WorkEntry.date.startswith(f"{year}-")).all()
    
    data = []
    for m in range(1, 13):
        m_str = f"{year}-{m:02d}"
        m_entries = [e for e in all_entries if e.date.startswith(m_str)]
        
        ho_h, off_h, wd_count, target_month = 0.0, 0.0, 0, 0.0
        d_ho, d_off, d_vac = set(), set(), set()
        holiday_preview = []
        planned_workdays = 0
        open_workdays = 0

        entries_by_date = {}
        for entry in m_entries:
            entries_by_date.setdefault(entry.date, []).append(entry)

        num_days = calendar.monthrange(year, m)[1]
        for day in range(1, num_days+1):
            dt = date(year, m, day)
            date_str = str(dt)
            inf = get_day_info(dt, settings, he_holidays, custom_map)
            if inf["holiday_name"]:
                holiday_preview.append(f"{day}. {inf['holiday_name']}")
            if inf["is_workday"]:
                wd_count += 1
                target_month += inf["target"]
                day_entries = entries_by_date.get(date_str, [])
                if any(entry.type == "planned" for entry in day_entries):
                    planned_workdays += 1
                elif not day_entries:
                    open_workdays += 1

        for entry_date, day_entries in entries_by_date.items():
            timed_entries = [
                entry for entry in day_entries
                if entry.type in ["planned", "home", "office", "dr"] and entry.start_time and entry.end_time
            ]
            timed_gross_hours = sum(calculate_gross_hours(entry.start_time, entry.end_time) for entry in timed_entries)
            timed_net_hours = calculate_daily_net_hours([(entry.start_time, entry.end_time) for entry in timed_entries])
            is_future = entry_date > today_str

            for entry in day_entries:
                h = 0.0
                if entry in timed_entries and timed_gross_hours > 0:
                    h = timed_net_hours * calculate_gross_hours(entry.start_time, entry.end_time) / timed_gross_hours
                elif entry.type == 'planned':
                    h = get_day_info(datetime.strptime(entry_date, "%Y-%m-%d").date(), settings, he_holidays, custom_map)["target"]
                elif entry.type in ['home', 'office', 'dr'] and is_future:
                    h = get_day_info(datetime.strptime(entry_date, "%Y-%m-%d").date(), settings, he_holidays, custom_map)["target"]

                if entry.type in ['home', 'planned']:
                    ho_h += h
                    d_ho.add(entry_date)
                elif entry.type in ['office', 'dr']:
                    off_h += h
                    d_off.add(entry_date)
                elif entry.type == 'vacation':
                    d_obj = datetime.strptime(entry_date, "%Y-%m-%d").date()
                    if get_day_info(d_obj, settings, he_holidays, custom_map)["is_workday"]:
                        d_vac.add(entry_date)
        
        data.append({ 
            "month": m, "workdays": wd_count, "days_ho": len(d_ho), "days_office": len(d_off), 
            "days_vacation": len(d_vac), "ho_hours_made": round(ho_h, 2), 
            "ho_hours_allowed": round(target_month * (settings.ho_quota_percent/100), 2), 
            "office_hours_made": round(off_h, 2),
            "work_hours_target": round(target_month, 2),
            "holiday_preview": holiday_preview,
            "planned_workdays": planned_workdays,
            "open_workdays": open_workdays
        })
    return jsonify(data)

@app.route('/api/entry', methods=['POST'])
def save_entry():
    d = request.get_json(silent=True)
    if not isinstance(d, dict): return jsonify({"success": False, "message": "Ungültiger Request-Body"}), 400
    if not is_valid_date(d.get('date')): return jsonify({"success": False, "message": "Ungültiges Datum"}), 400
    if d.get('type') not in VALID_TYPES: return jsonify({"success": False, "message": "Ungültiger Typ"}), 400
    for field in ('start', 'end'):
        if field in d and not is_valid_time(d[field]):
            return jsonify({"success": False, "message": "Ungültige Zeit"}), 400
    if d.get('id'):
        entry = db.session.get(WorkEntry, d.get('id'))
        if not entry: return jsonify({"success": False, "message": "Nicht gefunden"}), 404
    else:
        entry = WorkEntry(date=d.get('date'))
        db.session.add(entry)

    entry.type = d.get('type')
    entry.start_time = normalize_time_str(d.get('start'))
    entry.end_time = normalize_time_str(d.get('end'))
    entry.comment = d.get('comment').strip() if d.get('comment') else ''
    
    if 'glz_override_source' in d and d['glz_override_source'] not in ('manual', 'pdf', None):
        return jsonify({"success": False, "message": "Ungültige GLZ-Quelle"}), 400

    if 'glz_override' in d:
        val = d.get('glz_override')
        if val is not None and str(val).strip() != '':
            new_val = finite_number(val)
            if new_val is None:
                return jsonify({"success": False, "message": "Ungültiger GLZ-Abgleich"}), 400
            entry.glz_override = new_val
            entry.glz_override_source = d.get('glz_override_source', 'manual')
        else: 
            entry.glz_override = None
            entry.glz_override_source = None
    
    has_override = getattr(entry, 'glz_override', None) is not None
    if not entry.type and not entry.start_time and not entry.comment and not has_override:
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

@app.route('/api/entry/copy-or-move', methods=['POST'])
def copy_or_move_entries():
    """Kopiert oder verschiebt einen vollständigen Tag mit expliziter Konfliktstrategie."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "message": "Ungültiger Request-Body"}), 400

    source_date = payload.get('source_date')
    target_date = payload.get('target_date')
    operation = payload.get('operation')
    conflict_mode = payload.get('conflict_mode', 'cancel')
    if not is_valid_date(source_date) or not is_valid_date(target_date):
        return jsonify({"success": False, "message": "Ungültiges Datum"}), 400
    if source_date == target_date:
        return jsonify({"success": False, "message": "Quell- und Zieldatum müssen unterschiedlich sein"}), 400
    if operation not in ('copy', 'move'):
        return jsonify({"success": False, "message": "Ungültige Operation"}), 400
    if conflict_mode not in ('cancel', 'merge', 'overwrite'):
        return jsonify({"success": False, "message": "Ungültige Konfliktstrategie"}), 400

    source_entries = WorkEntry.query.filter_by(date=source_date).order_by(WorkEntry.id).all()
    if not source_entries:
        return jsonify({"success": False, "message": "Am Quelldatum sind keine Einträge vorhanden"}), 404
    target_entries = WorkEntry.query.filter_by(date=target_date).order_by(WorkEntry.id).all()
    if target_entries and conflict_mode == 'cancel':
        return jsonify({
            "success": False,
            "conflict": True,
            "message": "Das Zieldatum enthält bereits Einträge. Bitte Zusammenführen oder Überschreiben ausdrücklich bestätigen.",
            "source_entries": len(source_entries),
            "target_entries": len(target_entries),
        }), 409

    try:
        overwritten_entries = 0
        skipped_duplicates = 0
        glz_override_conflicts = 0
        entries_to_copy = source_entries

        if target_entries and conflict_mode == 'overwrite':
            overwritten_entries = len(target_entries)
            for entry in target_entries:
                db.session.delete(entry)
            known_entries = set()
            target_glz_override = None
        else:
            known_entries = {
                (entry.type, entry.start_time or '', entry.end_time or '', entry.comment or '')
                for entry in target_entries
            }
            target_glz_override = next(
                (entry.glz_override for entry in target_entries if entry.glz_override is not None),
                None,
            )

        copied_entries = 0
        # Beim Verschieben wird die Quelle erst gelöscht, nachdem alle Zielblöcke
        # vorbereitet sind. Der abschließende Commit bleibt atomar.
        for entry in entries_to_copy:
            identity = (entry.type, entry.start_time or '', entry.end_time or '', entry.comment or '')
            if identity in known_entries:
                skipped_duplicates += 1
                continue

            glz_override = entry.glz_override
            glz_override_source = entry.glz_override_source
            if glz_override is not None:
                if target_glz_override is not None and target_glz_override != glz_override:
                    glz_override = None
                    glz_override_source = None
                    glz_override_conflicts += 1
                else:
                    target_glz_override = glz_override

            db.session.add(WorkEntry(
                date=target_date,
                type=entry.type,
                start_time=entry.start_time,
                end_time=entry.end_time,
                comment=entry.comment,
                glz_override=glz_override,
                glz_override_source=glz_override_source,
            ))
            known_entries.add(identity)
            copied_entries += 1

        if operation == 'move':
            for entry in source_entries:
                db.session.delete(entry)

        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Kopieren/Verschieben fehlgeschlagen")
        return jsonify({"success": False, "message": "Kopieren oder Verschieben konnte nicht gespeichert werden."}), 500

    action = 'verschoben' if operation == 'move' else 'kopiert'
    suffix = ' und Ziel überschrieben' if target_entries and conflict_mode == 'overwrite' else ''
    suffix = ' und mit dem Ziel zusammengeführt' if target_entries and conflict_mode == 'merge' else suffix
    return jsonify({
        "success": True,
        "message": f"{copied_entries} Einträge {action}{suffix}.",
        "copied_entries": copied_entries,
        "skipped_duplicates": skipped_duplicates,
        "replaced_entries": overwritten_entries,
        "glz_override_conflicts": glz_override_conflicts,
    })

def build_series_plan(payload):
    """Ermittelt eine Serienplanung ohne Daten zu verändern."""
    if not isinstance(payload, dict):
        return None, ("Ungültiger Request-Body", 400)
    if not is_valid_date(payload.get('start')) or not is_valid_date(payload.get('end')):
        return None, ("Ungültiger Zeitraum", 400)

    start_date = datetime.strptime(payload['start'], '%Y-%m-%d').date()
    end_date = datetime.strptime(payload['end'], '%Y-%m-%d').date()
    weekdays = normalized_weekdays(payload.get('weekdays'))
    target_type = payload.get('type')
    overwrite = normalized_bool(payload.get('overwrite', False))
    if start_date > end_date:
        return None, ("Ungültiger Zeitraum", 400)
    if weekdays is None:
        return None, ("Ungültige Wochentage", 400)
    # Ein leerer Status ist kein speicherbarer Serienplan. Das verhindert, dass
    # die UI-Vorlage "Standardwoche" versehentlich Leerblöcke erzeugt.
    if target_type not in VALID_TYPES or target_type == '':
        return None, ("Für die Serienplanung ist ein konkreter Typ erforderlich", 400)
    if overwrite is None:
        return None, ("Ungültiger Wahrheitswert", 400)

    settings = Settings.query.first()
    default_start = settings.default_start_time or "08:00"
    existing_by_date = {}
    for entry in WorkEntry.query.filter(WorkEntry.date >= str(start_date), WorkEntry.date <= str(end_date)).all():
        existing_by_date.setdefault(entry.date, []).append(entry)
    custom_map = {datetime.strptime(item.date, "%Y-%m-%d").date(): item for item in CustomHoliday.query.all()}
    holidays = hessen_holidays(settings, list(range(start_date.year, end_date.year + 1)))
    today = get_local_now().date()
    plan = {"entries": [], "created_dates": [], "skipped_existing_dates": [], "overwritten_dates": [], "excluded_dates": []}

    current = start_date
    while current <= end_date:
        day_iso = str(current)
        if current.weekday() not in weekdays:
            current += timedelta(days=1)
            continue
        day_info = get_day_info(current, settings, holidays, custom_map)
        if not day_info['is_workday']:
            plan['excluded_dates'].append(day_iso)
            current += timedelta(days=1)
            continue

        existing = existing_by_date.get(day_iso, [])
        if existing and not overwrite:
            plan['skipped_existing_dates'].append(day_iso)
            current += timedelta(days=1)
            continue
        if existing:
            plan['overwritten_dates'].append(day_iso)

        final_type, start_time, end_time = target_type, '', ''
        if target_type == 'home' and current > today:
            final_type = 'planned'
        elif target_type in ('home', 'office', 'dr') and day_info['target'] > 0:
            start_time = normalize_time_str(default_start)
            start_hours, start_minutes_part = map(int, start_time.split(':'))
            start_minutes = start_hours * 60 + start_minutes_part
            end_minutes = start_minutes + calculate_gross_time_needed(day_info['target']) * 60
            end_time = f"{int(end_minutes // 60):02d}:{int(end_minutes % 60):02d}"
        plan['entries'].append({"date": day_iso, "type": final_type, "start": start_time, "end": end_time})
        plan['created_dates'].append(day_iso)
        current += timedelta(days=1)
    return plan, None


@app.route('/api/plan/series/preview', methods=['POST'])
def preview_series_plan():
    plan, error = build_series_plan(request.get_json(silent=True))
    if error:
        return jsonify({"success": False, "message": error[0]}), error[1]
    return jsonify({"success": True, **plan})


@app.route('/api/plan/series', methods=['POST'])
def plan_series():
    plan, error = build_series_plan(request.get_json(silent=True))
    if error:
        return jsonify({"success": False, "message": error[0]}), error[1]
    try:
        for day_iso in plan['overwritten_dates']:
            WorkEntry.query.filter_by(date=day_iso).delete()
        for entry in plan['entries']:
            db.session.add(WorkEntry(date=entry['date'], type=entry['type'], start_time=entry['start'], end_time=entry['end']))
        db.session.commit()
        return jsonify({"success": True, **plan})
    except Exception:
        db.session.rollback()
        app.logger.exception("Fehler im Serienplaner")
        return jsonify({"success": False, "message": "Ein Fehler ist beim Speichern aufgetreten."}), 500

@app.route('/api/custom-holidays', methods=['GET', 'POST'])
def handle_custom_holidays():
    if request.method == 'GET':
        hols = CustomHoliday.query.all()
        return jsonify(sorted([{'id': h.id, 'date': h.date, 'name': h.name, 'hours': h.hours or 0} for h in hols], key=lambda x: x['date']))
    
    data = request.get_json(silent=True)
    if not isinstance(data, dict): return jsonify({"success": False, "message": "Ungültiger Request-Body"}), 400
    if not is_valid_date(data.get('date')): return jsonify({"success": False, "message": "Ungültiges Datum"}), 400
    if not isinstance(data.get('name'), str) or not data['name'].strip(): return jsonify({"success": False, "message": "Ungültiger Name"}), 400
    hours = finite_number(data.get('hours', 0))
    if hours is None or hours < 0: return jsonify({"success": False, "message": "Ungültige Stunden"}), 400
        
    holiday_id = data.get('id')
    
    existing_for_date = CustomHoliday.query.filter_by(date=data['date']).first()
    if holiday_id:
        existing = db.session.get(CustomHoliday, holiday_id)
        if not existing:
            return jsonify({"success": False, "message": "Sondertag nicht gefunden"}), 404
        if existing_for_date and existing_for_date.id != existing.id:
            existing_for_date.name = data['name'].strip()
            existing_for_date.hours = hours
            db.session.delete(existing)
        else:
            existing.date = data['date']
            existing.name = data['name'].strip()
            existing.hours = hours
    elif existing_for_date:
        existing_for_date.name = data['name'].strip()
        existing_for_date.hours = hours
    else:
        db.session.add(CustomHoliday(date=data['date'], name=data['name'].strip(), hours=hours))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        app.logger.exception("Sondertag konnte nicht gespeichert werden")
        return jsonify({"success": False, "message": "Sondertag konnte nicht gespeichert werden"}), 409
    return jsonify({"success": True})

@app.route('/api/custom-holidays/<int:id>', methods=['DELETE'])
def delete_custom_holiday(id):
    h = db.session.get(CustomHoliday, id)
    if h: 
        db.session.delete(h)
        db.session.commit()
    return jsonify({"success": True})

def create_import_backup():
    """Erstellt unmittelbar vor einem expliziten JSON-Überschreiben ein SQLite-Backup."""
    timestamp = get_local_now().strftime('%Y%m%d_%H%M%S')
    backup_file = os.path.join(backup_dir, f'db_before_json_import_{timestamp}.db')
    if not os.path.exists(db_path):
        return None
    if not create_sqlite_backup(backup_file):
        raise RuntimeError("SQLite-Backup vor JSON-Import konnte nicht erstellt werden.")
    app.logger.info("Datenbank-Backup vor JSON-Import erstellt: %s", backup_file)
    return os.path.basename(backup_file)


def serialize_export():
    settings = Settings.query.first()
    active_weekdays = [int(value) for value in (settings.active_weekdays or '').split(',') if value.strip().isdigit()]
    return {
        "format": "ho-planer-export",
        "version": 1,
        "exported_at": get_local_now().isoformat(),
        "settings": {
            "weekly_hours": settings.weekly_hours,
            "active_weekdays": active_weekdays,
            "ho_quota_percent": settings.ho_quota_percent,
            "hide_weekends": settings.hide_weekends,
            "default_start_time": settings.default_start_time,
            "auto_convert_planned": settings.auto_convert_planned,
            "christmas_eve_and_new_years_eve_off": getattr(settings, 'christmas_eve_and_new_years_eve_off', True),
        },
        "custom_holidays": [
            {"date": holiday.date, "name": holiday.name, "hours": holiday.hours or 0.0}
            for holiday in CustomHoliday.query.order_by(CustomHoliday.date).all()
        ],
        "entries": [
            {
                "date": entry.date,
                "type": entry.type,
                "start": entry.start_time or "",
                "end": entry.end_time or "",
                "comment": entry.comment or "",
                "glz_override": entry.glz_override,
                "glz_override_source": entry.glz_override_source,
            }
            for entry in WorkEntry.query.order_by(WorkEntry.date, WorkEntry.id).all()
        ],
    }


def normalized_import_entry(raw_entry):
    """Validiert genau einen Austausch-Eintrag und liefert einen neutralen Fehlercode."""
    if not isinstance(raw_entry, dict):
        return None, 'invalid_object'
    entry_date = raw_entry.get('date')
    entry_type = raw_entry.get('type', '')
    start = raw_entry.get('start', '')
    end = raw_entry.get('end', '')
    if not is_valid_date(entry_date):
        return None, 'invalid_date'
    if entry_type not in VALID_TYPES:
        return None, 'invalid_type'
    if not is_valid_time(start) or not is_valid_time(end):
        return None, 'invalid_time'
    override_raw = raw_entry.get('glz_override')
    override = None if override_raw is None or override_raw == '' else finite_number(override_raw)
    if override_raw is not None and override_raw != '' and override is None:
        return None, 'invalid_glz_override'
    source = raw_entry.get('glz_override_source')
    if source not in VALID_GLZ_OVERRIDE_SOURCES:
        return None, 'invalid_glz_override_source'
    return {"date": entry_date, "type": entry_type, "start": start, "end": end,
            "comment": str(raw_entry.get('comment') or '').strip(), "glz_override": override,
            "glz_override_source": source}, None


def normalized_import_holiday(raw_holiday):
    """Validiert genau einen Sondertag und liefert einen neutralen Fehlercode.

    Vorschau und Import teilen diese Prüfung: zwei getrennte Implementierungen
    haben unterschiedliche Fehlercodes und Zähler erzeugt.
    """
    if not isinstance(raw_holiday, dict):
        return None, 'invalid_object'
    if not is_valid_date(raw_holiday.get('date')):
        return None, 'invalid_date'
    if not str(raw_holiday.get('name') or '').strip():
        return None, 'invalid_name'
    hours = finite_number(raw_holiday.get('hours', 0))
    if hours is None or hours < 0:
        return None, 'invalid_hours'
    return {"date": raw_holiday['date'], "name": str(raw_holiday['name']).strip(), "hours": hours}, None


def json_import_preview(payload):
    """Analysiert einen Export ohne Datenbankänderungen für die Importbestätigung."""
    if not isinstance(payload, dict) or payload.get('format') != 'ho-planer-export' or payload.get('version') != 1:
        return None, "Nicht unterstütztes Exportformat oder unbekannte Formatversion."
    if not isinstance(payload.get('entries'), list) or not isinstance(payload.get('custom_holidays'), list):
        return None, "Ungültiger Eintrags- oder Sondertagscontainer in der Exportdatei."

    result = {"valid_entries": 0, "skipped_entries": 0, "invalid_entries": 0,
              "entry_conflicts": 0, "valid_custom_holidays": 0, "skipped_custom_holidays": 0,
              "holiday_conflicts": 0, "glz_override_conflicts": 0, "details": []}
    known_entries = {
        (entry.date, entry.type, entry.start_time or '', entry.end_time or '', entry.comment or '')
        for entry in WorkEntry.query.all()
    }
    # Nur vor dem Import vorhandene Anker erzeugen Konflikte. Unterschiedliche
    # Anker aus derselben Datei bleiben gültig; beim Speichern gewinnt der letzte.
    existing_overrides_by_date = {
        entry.date: entry.glz_override
        for entry in WorkEntry.query.filter(WorkEntry.glz_override.isnot(None)).order_by(WorkEntry.id).all()
    }
    for index, raw_entry in enumerate(payload['entries']):
        entry, error_code = normalized_import_entry(raw_entry)
        if error_code:
            result['invalid_entries'] += 1
            result['details'].append(f'entries[{index}]: {error_code}')
            continue
        identity = (entry['date'], entry['type'], entry['start'], entry['end'], entry['comment'])
        if identity in known_entries:
            result['skipped_entries'] += 1
            continue
        if (
            entry['glz_override'] is not None
            and entry['date'] in existing_overrides_by_date
            and existing_overrides_by_date[entry['date']] != entry['glz_override']
        ):
            result['glz_override_conflicts'] += 1
        known_entries.add(identity)
        result['valid_entries'] += 1

    for index, raw_holiday in enumerate(payload['custom_holidays']):
        holiday, error_code = normalized_import_holiday(raw_holiday)
        if error_code:
            result['holiday_conflicts'] += 1
            result['details'].append(f'custom_holidays[{index}]: {error_code}')
            continue
        hours = holiday['hours']
        existing = CustomHoliday.query.filter_by(date=holiday['date']).first()
        if existing and (existing.name != holiday['name'] or (existing.hours or 0.0) != hours):
            result['holiday_conflicts'] += 1
        elif existing:
            result['skipped_custom_holidays'] += 1
        else:
            result['valid_custom_holidays'] += 1
    return result, None


@app.route('/api/import/json/preview', methods=['POST'])
def preview_json_import():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Keine JSON-Datei ausgewählt."}), 400
    try:
        payload = json.load(request.files['file'])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"success": False, "message": "Ungültige JSON-Datei."}), 400
    result, error = json_import_preview(payload)
    if error:
        return jsonify({"success": False, "message": error}), 400
    return jsonify({"success": True, **result})


@app.route('/api/export/json', methods=['GET'])
def export_json():
    payload = json.dumps(serialize_export(), ensure_ascii=False, indent=2)
    filename = f"ho-planer-export-{get_local_now().date().isoformat()}.json"
    return Response(payload, mimetype='application/json', headers={'Content-Disposition': f'attachment; filename={filename}'})


@app.route('/api/import/json', methods=['POST'])
def import_json():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Keine JSON-Datei ausgewählt."}), 400

    try:
        payload = json.load(request.files['file'])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"success": False, "message": "Ungültige JSON-Datei."}), 400

    if not isinstance(payload, dict) or payload.get('format') != 'ho-planer-export' or payload.get('version') != 1:
        return jsonify({"success": False, "message": "Nicht unterstütztes Exportformat oder unbekannte Formatversion."}), 400
    if 'entries' not in payload or not isinstance(payload['entries'], list):
        return jsonify({"success": False, "message": "Ungültiger Eintragscontainer in der Exportdatei."}), 400
    if 'custom_holidays' not in payload or not isinstance(payload['custom_holidays'], list):
        return jsonify({"success": False, "message": "Ungültiger Sondertagscontainer in der Exportdatei."}), 400

    overwrite = request.form.get('overwrite') == 'true'
    result = {"imported_entries": 0, "skipped_entries": 0, "invalid_entries": 0,
              "entry_conflicts": 0, "imported_custom_holidays": 0, "skipped_custom_holidays": 0,
              "holiday_conflicts": 0, "glz_override_conflicts": 0, "settings_imported": False,
              "backup_created": None, "details": []}

    try:
        if overwrite:
            result['backup_created'] = create_import_backup()

        # Nur vor dem Import vorhandene Anker sind Konfliktkandidaten. Mehrere
        # Anker aus demselben portablen Import müssen ihre Reihenfolge und damit
        # die Semantik "zuletzt gespeicherter Anker gewinnt" behalten.
        existing_overrides_by_date = {
            entry.date: entry
            for entry in WorkEntry.query.filter(WorkEntry.glz_override.isnot(None)).order_by(WorkEntry.id).all()
        }

        for index, raw_entry in enumerate(payload['entries']):
            entry_data, error_code = normalized_import_entry(raw_entry)
            if error_code:
                result['invalid_entries'] += 1
                result['details'].append(f'entries[{index}]: {error_code}')
                continue

            identical = WorkEntry.query.filter_by(
                date=entry_data['date'], type=entry_data['type'], start_time=entry_data['start'],
                end_time=entry_data['end'], comment=entry_data['comment']
            ).first()
            if identical:
                if entry_data['glz_override'] is not None and identical.glz_override != entry_data['glz_override']:
                    if overwrite:
                        identical.glz_override = entry_data['glz_override']
                        identical.glz_override_source = entry_data['glz_override_source']
                    else:
                        result['glz_override_conflicts'] += 1
                result['skipped_entries'] += 1
                continue

            existing_override = existing_overrides_by_date.get(entry_data['date'])
            if entry_data['glz_override'] is not None and existing_override and existing_override.glz_override != entry_data['glz_override']:
                if overwrite:
                    existing_override.glz_override = entry_data['glz_override']
                    existing_override.glz_override_source = entry_data['glz_override_source']
                    entry_data['glz_override'] = None
                else:
                    entry_data['glz_override'] = None
                    result['glz_override_conflicts'] += 1

            db.session.add(WorkEntry(date=entry_data['date'], type=entry_data['type'], start_time=entry_data['start'],
                                     end_time=entry_data['end'], comment=entry_data['comment'],
                                     glz_override=entry_data['glz_override'], glz_override_source=entry_data['glz_override_source']))
            result['imported_entries'] += 1

        for index, raw_holiday in enumerate(payload['custom_holidays']):
            holiday, error_code = normalized_import_holiday(raw_holiday)
            if error_code:
                result['holiday_conflicts'] += 1
                result['details'].append(f'custom_holidays[{index}]: {error_code}')
                continue
            existing = CustomHoliday.query.filter_by(date=holiday['date']).first()
            if not existing:
                db.session.add(CustomHoliday(date=holiday['date'], name=holiday['name'], hours=holiday['hours']))
                result['imported_custom_holidays'] += 1
            elif existing.name == holiday['name'] and (existing.hours or 0.0) == holiday['hours']:
                result['skipped_custom_holidays'] += 1
            elif overwrite:
                existing.name = holiday['name']
                existing.hours = holiday['hours']
            else:
                result['holiday_conflicts'] += 1

        db.session.commit()
        message = f"{result['imported_entries']} Einträge ergänzt, {result['skipped_entries']} bereits vorhandene Einträge übersprungen."
        return jsonify({"success": True, "message": message, **result})
    except Exception as error:
        db.session.rollback()
        app.logger.error("JSON-Import fehlgeschlagen: %s", error, exc_info=True)
        return jsonify({"success": False, "message": "Fehler beim JSON-Import."}), 500


@app.errorhandler(RequestEntityTooLarge)
def handle_upload_too_large(_error):
    return jsonify({"success": False, "message": f"Datei ist zu groß. Maximal erlaubt sind {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB."}), 413


@app.route('/api/import/pdf', methods=['POST'])
def import_pdf():
    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Keine Datei ausgewählt."}), 400

    file = request.files['file']
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({"success": False, "message": "Bitte lade nur PDF-Dateien hoch."}), 400

    signature = file.stream.read(5)
    file.stream.seek(0)
    if signature != b'%PDF-':
        return jsonify({"success": False, "message": "Die Datei ist keine gültige PDF-Datei."}), 400

    overwrite = request.form.get('overwrite') == 'true'

    try:
        settings = Settings.query.first()
        extracted_entries, report = parse_pdf_content(file, include_report=True)

        if not extracted_entries:
             return jsonify({"success": True, "message": "Keine Einträge gefunden.", "report": report})
             
        y = extracted_entries[0]['date'].year
        he_holidays = hessen_holidays(settings, y)
        custom_map = {datetime.strptime(c.date, "%Y-%m-%d").date(): c for c in CustomHoliday.query.all()}

        result = {
            'imported_entries': 0,
            'skipped_duplicates': 0,
            'comment_hints': 0,
            'glz_override_conflicts': 0,
        }
        entries_by_date = {}
        for entry in extracted_entries:
            entries_by_date.setdefault(entry['date'], []).append(entry)

        for date_obj, entries in entries_by_date.items():
            date_iso = str(date_obj)
            day_info = get_day_info(date_obj, settings, he_holidays, custom_map)
            is_free_day = not day_info['is_workday']
            valid_entries = [
                entry for entry in entries
                if entry['start'] and entry['end'] or entry['comment'] or entry['glz_override'] is not None or not is_free_day
            ]
            if not valid_entries:
                continue

            existing_entries = WorkEntry.query.filter_by(date=date_iso).all()
            if overwrite:
                WorkEntry.query.filter_by(date=date_iso).delete()
                entries_to_add = valid_entries
            else:
                merged = merge_pdf_entries(existing_entries, valid_entries)
                entries_to_add = merged['entries_to_add']
                for field in ('skipped_duplicates', 'comment_hints', 'glz_override_conflicts'):
                    result[field] += merged[field]

            for entry in entries_to_add:
                new_entry = WorkEntry(
                    date=date_iso,
                    type=entry['type'],
                    start_time=entry['start'],
                    end_time=entry['end'],
                    comment=entry['comment'],
                    glz_override=entry.get('glz_override'),
                    glz_override_source='pdf' if entry.get('glz_override') is not None else None,
                )
                db.session.add(new_entry)
                result['imported_entries'] += 1

        db.session.commit()
        result['success'] = True
        result['message'] = f"{result['imported_entries']} Einträge importiert."
        result['report'] = report
        return jsonify(result)
            
    except ValueError as error:
        app.logger.info("PDF-Import abgelehnt: %s", error)
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        app.logger.error("PDF-Import fehlgeschlagen: %s", error, exc_info=True)
        return jsonify({"success": False, "message": "PDF konnte nicht verarbeitet werden."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
