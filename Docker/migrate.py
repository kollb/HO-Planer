import os
from sqlalchemy import text, inspect
from app import app, db

def migrate():
    # Wir führen alles im App-Kontext aus, damit SQLAlchemy greift
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)

        # Prüfen, ob die Tabelle überhaupt existiert
        if not inspector.has_table('work_entry'):
            print("[Migrate] Tabelle 'work_entry' existiert nicht. Wird beim Start von app.py erstellt.")
            return

        try:
            # Verbindung über SQLAlchemy aufbauen
            with engine.connect() as conn:
                # 1. PRÜFUNG: Hat die Tabelle ein UNIQUE Constraint auf 'date'? (Alte Migration)
                result = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='work_entry'"))
                row = result.fetchone()
                if row:
                    create_sql = row[0]
                    if create_sql and "UNIQUE" in create_sql.upper() and "date" in create_sql:
                        print("[Migrate] Alte Datenbank-Struktur erkannt (Unique Constraint). Starte Migration 1...")
                        perform_unique_constraint_migration(conn)
                        print("[Migrate] Migration 1 erfolgreich abgeschlossen!")

            # Inspector neu laden, falls die Tabelle in Migration 1 neu erstellt wurde
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('work_entry')]

            with engine.connect() as conn:
                # 2. PRÜFUNG: Fehlt die Spalte 'glz_override'? (Migration 2)
                if "glz_override" not in columns:
                    print("[Migrate] Spalte 'glz_override' fehlt. Starte Migration 2...")
                    conn.execute(text("ALTER TABLE work_entry ADD COLUMN glz_override FLOAT"))
                    conn.commit()
                    print("[Migrate] Migration 2 erfolgreich abgeschlossen! GLZ-Override Spalte hinzugefügt.")
                else:
                    print("[Migrate] Datenbank-Schema für 'glz_override' ist auf dem neuesten Stand.")

                # 3. PRÜFUNG: Fehlt die Spalte 'glz_override_source'? (Migration 3)
                if "glz_override_source" not in columns:
                    print("[Migrate] Spalte 'glz_override_source' fehlt. Starte Migration 3...")
                    conn.execute(text("ALTER TABLE work_entry ADD COLUMN glz_override_source VARCHAR(20)"))
                    conn.commit()
                    print("[Migrate] Migration 3 erfolgreich abgeschlossen! Source-Spalte hinzugefügt.")
                else:
                    print("[Migrate] Datenbank-Schema für 'glz_override_source' ist auf dem neuesten Stand.")
                
        except Exception as e:
            print(f"[Migrate] Fehler bei der Prüfung/Migration: {e}")

def perform_unique_constraint_migration(conn):
    try:
        conn.execute(text("ALTER TABLE work_entry RENAME TO work_entry_old"))
        
        conn.execute(text("""
            CREATE TABLE work_entry (
                id INTEGER NOT NULL, 
                date VARCHAR(10) NOT NULL, 
                type VARCHAR(20), 
                start_time VARCHAR(5), 
                end_time VARCHAR(5), 
                comment VARCHAR(255), 
                PRIMARY KEY (id)
            )
        """))
        conn.execute(text("CREATE INDEX ix_work_entry_date ON work_entry (date)"))
        
        # Spalten der alten Tabelle auslesen, um sie 1:1 zu kopieren
        result = conn.execute(text("PRAGMA table_info(work_entry_old)"))
        columns = [row[1] for row in result.fetchall()]
        cols_str = ", ".join(columns)
        
        conn.execute(text(f"INSERT INTO work_entry ({cols_str}) SELECT {cols_str} FROM work_entry_old"))
        conn.execute(text("DROP TABLE work_entry_old"))
        
        conn.commit()
        
    except Exception as e:
        print(f"[Migrate] KRITISCHER FEHLER bei Migration 1: {e}")
        conn.rollback()
        raise e

if __name__ == "__main__":
    migrate()