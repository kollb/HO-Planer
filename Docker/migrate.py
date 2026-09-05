import os

from sqlalchemy import inspect, text

from app import ADDITIVE_SCHEMA_COLUMNS, app, backup_dir, create_sqlite_backup, db, db_path, get_local_now


MIGRATION_TABLE = "schema_migrations"
CURRENT_COLUMNS = [
    "id", "date", "type", "start_time", "end_time", "comment",
    "glz_override", "glz_override_source",
]
# Die Spaltendefinitionen stammen aus app.py, damit Start-Selbstheilung und
# versionierte Migration niemals auseinanderlaufen können.
ADDITIVE_COLUMN_DDL = {
    table: dict(columns) for table, columns in ADDITIVE_SCHEMA_COLUMNS.items()
}


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
        has_work_entry = inspector.has_table("work_entry")
        has_settings = inspector.has_table("settings")

        with engine.connect() as conn:
            legacy_unique = has_work_entry and has_legacy_unique_date_constraint(conn)
            work_columns = {column["name"] for column in inspect(conn).get_columns("work_entry")} if has_work_entry else set()
            settings_columns = {column["name"] for column in inspect(conn).get_columns("settings")} if has_settings else set()
            needs_override = has_work_entry and "glz_override" not in work_columns
            needs_source = has_work_entry and "glz_override_source" not in work_columns
            needs_year_end_option = has_settings and "christmas_eve_and_new_years_eve_off" not in settings_columns
            needs_theme = has_settings and "theme" not in settings_columns
            holiday_indexes = inspect(conn).get_indexes("custom_holiday") if inspect(conn).has_table("custom_holiday") else []
            has_holiday_unique_index = any(index["unique"] and index["column_names"] == ["date"] for index in holiday_indexes)
            needs_unique_holiday_date = bool(holiday_indexes is not None) and inspect(conn).has_table("custom_holiday") and not has_holiday_unique_index
            needs_metadata = not inspect(conn).has_table(MIGRATION_TABLE)

        if not any((legacy_unique, needs_override, needs_source, needs_year_end_option, needs_theme, needs_unique_holiday_date, needs_metadata)):
            app.logger.info("[Migrate] Datenbank-Schema ist aktuell.")
            return

        needs_schema_change = any((legacy_unique, needs_override, needs_source, needs_year_end_option, needs_theme, needs_unique_holiday_date))
        backup_file = create_migration_backup() if needs_schema_change else None
        try:
            with engine.begin() as conn:
                ensure_migration_table(conn)
                if has_work_entry:
                    if legacy_unique:
                        perform_unique_constraint_migration(conn)
                        record_migration(conn, 1)

                    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(work_entry)")).fetchall()}
                    if "glz_override" not in columns:
                        conn.execute(text(f"ALTER TABLE work_entry ADD COLUMN glz_override {ADDITIVE_COLUMN_DDL['work_entry']['glz_override']}"))
                    record_migration(conn, 2)

                    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(work_entry)")).fetchall()}
                    if "glz_override_source" not in columns:
                        conn.execute(text(f"ALTER TABLE work_entry ADD COLUMN glz_override_source {ADDITIVE_COLUMN_DDL['work_entry']['glz_override_source']}"))
                    record_migration(conn, 3)

                if has_settings:
                    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)")).fetchall()}
                    if "christmas_eve_and_new_years_eve_off" not in columns:
                        conn.execute(text(f"ALTER TABLE settings ADD COLUMN christmas_eve_and_new_years_eve_off {ADDITIVE_COLUMN_DDL['settings']['christmas_eve_and_new_years_eve_off']}"))
                    record_migration(conn, 4)

                    columns = {row[1] for row in conn.execute(text("PRAGMA table_info(settings)")).fetchall()}
                    if "theme" not in columns:
                        conn.execute(text(f"ALTER TABLE settings ADD COLUMN theme {ADDITIVE_COLUMN_DDL['settings']['theme']}"))
                    record_migration(conn, 6)

                if inspect(conn).has_table("custom_holiday"):
                    conn.execute(text("""
                        DELETE FROM custom_holiday
                        WHERE id NOT IN (SELECT MAX(id) FROM custom_holiday GROUP BY date)
                    """))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_custom_holiday_date ON custom_holiday (date)"))
                    record_migration(conn, 5)

            app.logger.info("[Migrate] Migration erfolgreich abgeschlossen. Backup: %s", backup_file)
        except Exception:
            app.logger.exception("[Migrate] Migration fehlgeschlagen. Backup bleibt erhalten: %s", backup_file)
            raise


if __name__ == "__main__":
    migrate()