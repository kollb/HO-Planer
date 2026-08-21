import os

from sqlalchemy import inspect, text

from app import app, backup_dir, create_sqlite_backup, db, db_path, get_local_now


MIGRATION_TABLE = "schema_migrations"
CURRENT_COLUMNS = [
    "id", "date", "type", "start_time", "end_time", "comment",
    "glz_override", "glz_override_source",
]


def create_migration_backup():
    """Sichert die vorhandene SQLite-Datei genau vor einer Schemaänderung."""
    if not os.path.exists(db_path):
        return None

    timestamp = get_local_now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"db_before_migration_{timestamp}.db")
    if not create_sqlite_backup(backup_file):
        raise RuntimeError("SQLite-Backup vor Migration konnte nicht erstellt werden.")
    app.logger.info("Migrations-Backup erstellt: %s", backup_file)
    return backup_file


def ensure_migration_table(conn):
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
            version INTEGER NOT NULL PRIMARY KEY,
            applied_at VARCHAR(32) NOT NULL
        )
    """))


def record_migration(conn, version):
    conn.execute(
        text(f"INSERT OR IGNORE INTO {MIGRATION_TABLE} (version, applied_at) VALUES (:version, :applied_at)"),
        {"version": version, "applied_at": get_local_now().isoformat()},
    )


def has_legacy_unique_date_constraint(conn):
    row = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='work_entry'")).fetchone()
    create_sql = row[0] if row else ""
    return bool(create_sql and "UNIQUE" in create_sql.upper() and "DATE" in create_sql.upper())


def perform_unique_constraint_migration(conn):
    """Ersetzt die alte Eintragstabelle durch das aktuelle Schema ohne Tages-UNIQUE."""
    conn.execute(text("ALTER TABLE work_entry RENAME TO work_entry_old"))
    conn.execute(text("""
        CREATE TABLE work_entry (
            id INTEGER NOT NULL,
            date VARCHAR(10) NOT NULL,
            type VARCHAR(20),
            start_time VARCHAR(5),
            end_time VARCHAR(5),
            comment VARCHAR(255),
            glz_override FLOAT,
            glz_override_source VARCHAR(20),
            PRIMARY KEY (id)
        )
    """))

    old_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(work_entry_old)")).fetchall()}
    transferable_columns = [column for column in CURRENT_COLUMNS if column in old_columns]
    if transferable_columns:
        columns_sql = ", ".join(transferable_columns)
        conn.execute(text(
            f"INSERT INTO work_entry ({columns_sql}) SELECT {columns_sql} FROM work_entry_old"
        ))

    conn.execute(text("DROP TABLE work_entry_old"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_work_entry_date ON work_entry (date)"))


def migrate():
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        if not inspector.has_table("work_entry"):
            app.logger.info("[Migrate] work_entry wird beim App-Start neu angelegt; keine Datenmigration erforderlich.")
            return

        with engine.connect() as conn:
            legacy_unique = has_legacy_unique_date_constraint(conn)
            columns = {column["name"] for column in inspect(conn).get_columns("work_entry")}
            needs_override = "glz_override" not in columns
            needs_source = "glz_override_source" not in columns
            needs_metadata = not inspect(conn).has_table(MIGRATION_TABLE)

        if not any((legacy_unique, needs_override, needs_source, needs_metadata)):
            app.logger.info("[Migrate] Datenbank-Schema ist aktuell.")
            return

        needs_schema_change = any((legacy_unique, needs_override, needs_source))
        backup_file = create_migration_backup() if needs_schema_change else None
        try:
            with engine.begin() as conn:
                ensure_migration_table(conn)
                if legacy_unique:
                    perform_unique_constraint_migration(conn)
                    record_migration(conn, 1)

                columns = {row[1] for row in conn.execute(text("PRAGMA table_info(work_entry)")).fetchall()}
                if "glz_override" not in columns:
                    conn.execute(text("ALTER TABLE work_entry ADD COLUMN glz_override FLOAT"))
                record_migration(conn, 2)

                columns = {row[1] for row in conn.execute(text("PRAGMA table_info(work_entry)")).fetchall()}
                if "glz_override_source" not in columns:
                    conn.execute(text("ALTER TABLE work_entry ADD COLUMN glz_override_source VARCHAR(20)"))
                record_migration(conn, 3)

            app.logger.info("[Migrate] Migration erfolgreich abgeschlossen. Backup: %s", backup_file)
        except Exception:
            app.logger.exception("[Migrate] Migration fehlgeschlagen. Backup bleibt erhalten: %s", backup_file)
            raise


if __name__ == "__main__":
    migrate()