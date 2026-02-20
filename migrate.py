import sqlite3
import os

# Robust: Dynamische Pfadermittlung (exakt wie in app.py)
basedir = os.path.abspath(os.path.dirname(__file__))
data_dir = os.path.join(basedir, 'data')
DB_PATH = os.path.join(data_dir, 'database.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"[Migrate] Keine Datenbank unter {DB_PATH} gefunden. Wird beim App-Start erstellt.")
        return

    # Verbindung direkt herstellen (ohne SQLAlchemy App-Kontext für Speed/Sicherheit)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Prüfen, ob die Tabelle 'work_entry' existiert
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='work_entry'")
        if not cursor.fetchone():
            return

        # 1. PRÜFUNG: Hat die Tabelle ein UNIQUE Constraint auf 'date'? (Alte Migration)
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='work_entry'")
        row = cursor.fetchone()
        if row:
            create_sql = row[0]
            if "UNIQUE" in create_sql.upper() and "date" in create_sql:
                print("[Migrate] Alte Datenbank-Struktur erkannt (Unique Constraint). Starte Migration 1...")
                perform_unique_constraint_migration(conn, cursor)
                print("[Migrate] Migration 1 erfolgreich abgeschlossen!")

        # 2. PRÜFUNG: Fehlt die neue Spalte 'glz_override'? (Neue Migration)
        cursor.execute("PRAGMA table_info(work_entry)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "glz_override" not in columns:
            print("[Migrate] Spalte 'glz_override' fehlt. Starte Migration 2...")
            cursor.execute("ALTER TABLE work_entry ADD COLUMN glz_override FLOAT")
            conn.commit()
            print("[Migrate] Migration 2 erfolgreich abgeschlossen! GLZ-Override Spalte hinzugefügt.")
        else:
            print("[Migrate] Datenbank-Schema für 'work_entry' ist auf dem neuesten Stand.")
            
    except Exception as e:
        print(f"[Migrate] Fehler bei der Prüfung/Migration: {e}")
    finally:
        conn.close()

def perform_unique_constraint_migration(conn, cursor):
    try:
        cursor.execute("ALTER TABLE work_entry RENAME TO work_entry_old")
        
        cursor.execute("""
            CREATE TABLE work_entry (
                id INTEGER NOT NULL, 
                date VARCHAR(10) NOT NULL, 
                type VARCHAR(20), 
                start_time VARCHAR(5), 
                end_time VARCHAR(5), 
                comment VARCHAR(255), 
                PRIMARY KEY (id)
            )
        """)
        cursor.execute("CREATE INDEX ix_work_entry_date ON work_entry (date)")
        
        cursor.execute("PRAGMA table_info(work_entry_old)")
        columns = [row[1] for row in cursor.fetchall()]
        cols_str = ", ".join(columns)
        
        cursor.execute(f"INSERT INTO work_entry ({cols_str}) SELECT {cols_str} FROM work_entry_old")
        cursor.execute("DROP TABLE work_entry_old")
        
        conn.commit()
        
    except Exception as e:
        print(f"[Migrate] KRTISCHER FEHLER bei Migration 1: {e}")
        conn.rollback()
        raise e

if __name__ == "__main__":
    # Stelle sicher, dass der Ordner existiert, falls migrate.py isoliert aufgerufen wird
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    migrate()