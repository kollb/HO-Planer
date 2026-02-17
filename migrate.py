import sqlite3
import os

DB_PATH = '/app/data/database.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print("[Migrate] Keine Datenbank gefunden. Wird beim App-Start erstellt.")
        return

    # Verbindung direkt herstellen (ohne SQLAlchemy App-Kontext für Speed/Sicherheit)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Prüfen, ob die Tabelle 'work_entry' existiert
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='work_entry'")
        if not cursor.fetchone():
            return

        # PRÜFUNG: Hat die Tabelle ein UNIQUE Constraint auf 'date'?
        # Wir schauen uns das CREATE TABLE Statement an
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='work_entry'")
        row = cursor.fetchone()
        if row:
            create_sql = row[0]
            # Wenn "UNIQUE" im SQL steht (und es sich auf date bezieht), müssen wir migrieren
            # Alte Version hatte: date ... UNIQUE oder UNIQUE(date)
            if "UNIQUE" in create_sql.upper() and "date" in create_sql:
                print("[Migrate] Alte Datenbank-Struktur erkannt (Unique Constraint). Starte Migration...")
                perform_migration(conn, cursor)
            else:
                print("[Migrate] Datenbank ist bereits auf dem neuesten Stand.")
    except Exception as e:
        print(f"[Migrate] Fehler bei der Prüfung: {e}")
    finally:
        conn.close()

def perform_migration(conn, cursor):
    try:
        # 1. Tabelle umbenennen
        cursor.execute("ALTER TABLE work_entry RENAME TO work_entry_old")
        
        # 2. Neue Tabelle erstellen (OHNE Unique Constraint)
        # Wir kopieren hier exakt das Schema aus models.py
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
        
        # 3. Daten kopieren
        # Wir ermitteln die Spalten der alten Tabelle, um Fehler zu vermeiden
        cursor.execute("PRAGMA table_info(work_entry_old)")
        columns = [row[1] for row in cursor.fetchall()]
        cols_str = ", ".join(columns)
        
        cursor.execute(f"INSERT INTO work_entry ({cols_str}) SELECT {cols_str} FROM work_entry_old")
        
        # 4. Alte Tabelle löschen
        cursor.execute("DROP TABLE work_entry_old")
        
        conn.commit()
        print("[Migrate] Migration erfolgreich abgeschlossen! Split-Buchungen nun möglich.")
        
    except Exception as e:
        print(f"[Migrate] KRTISCHER FEHLER bei Migration: {e}")
        conn.rollback()

if __name__ == "__main__":
    migrate()