"""Regressionstests: Alte Datenbanken dürfen Start und Migration nicht abbrechen.

Der gemeldete Fehler ``no such column: settings.christmas_eve_and_new_years_eve_off``
entstand, weil ``app.py`` bereits beim Import per ORM auf ``settings`` zugreift,
während ``migrate.py`` zuerst ``app`` importieren muss, bevor es migrieren kann.
Diese Tests sichern die Start-Selbstheilung und die versionierte Migration ab.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app import ensure_additive_schema_columns
from migrate import has_legacy_unique_date_constraint, perform_unique_constraint_migration

PROJECT_DIR = Path(__file__).resolve().parent.parent


def create_legacy_database(path):
    """Erzeugt eine Datenbank im alten Schema: ohne GLZ-Spalten, ohne
    Jahresendoption, ohne Theme, ohne Migrationstabelle und ohne eindeutigen
    Sondertagsindex – dafür mit echten Altdaten."""
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE settings (
                id INTEGER NOT NULL PRIMARY KEY,
                weekly_hours FLOAT,
                active_weekdays VARCHAR(20),
                ho_quota_percent INTEGER,
                hide_weekends BOOLEAN,
                default_start_time VARCHAR(5),
                auto_convert_planned BOOLEAN
            )
            """
        )
        connection.execute(
            """
            INSERT INTO settings
                (id, weekly_hours, active_weekdays, ho_quota_percent, hide_weekends,
                 default_start_time, auto_convert_planned)
            VALUES (1, 39.0, '0,1,2,3,4', 60, 1, '08:00', 1)
            """
        )
        connection.execute(
            """
            CREATE TABLE work_entry (
                id INTEGER NOT NULL PRIMARY KEY,
                date VARCHAR(10) NOT NULL,
                type VARCHAR(20),
                start_time VARCHAR(5),
                end_time VARCHAR(5),
                comment VARCHAR(255)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO work_entry (date, type, start_time, end_time, comment)
            VALUES ('2026-01-05', 'home', '08:00', '16:30', 'Altdaten')
            """
        )
        connection.execute(
            """
            CREATE TABLE custom_holiday (
                id INTEGER NOT NULL PRIMARY KEY,
                date VARCHAR(10) NOT NULL,
                name VARCHAR(50) NOT NULL,
                hours FLOAT
            )
            """
        )
        connection.execute(
            "INSERT INTO custom_holiday (date, name, hours) VALUES ('2026-11-17', 'Altdaten-Sondertag', 0.0)"
        )
        connection.execute("CREATE INDEX ix_work_entry_date ON work_entry (date)")
        connection.commit()
    finally:
        connection.close()


def table_columns(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migrate_py_repairs_legacy_database(tmp_path):
    """Der Einstiegspunkt aus entrypoint.sh muss alte Datenbanken öffnen können.

    Vor der Korrektur brach bereits der ``app``-Import in ``migrate.py`` mit
    ``OperationalError: no such column`` ab, sodass die Migration nie lief.
    """
    data_dir = tmp_path / "legacy-data"
    data_dir.mkdir()
    create_legacy_database(data_dir / "database.db")

    env = os.environ.copy()
    env["HO_PLANER_DATA_DIR"] = str(data_dir)

    completed = subprocess.run(
        [sys.executable, "migrate.py"],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout

    connection = sqlite3.connect(data_dir / "database.db")
    try:
        assert {"christmas_eve_and_new_years_eve_off", "theme"} <= table_columns(connection, "settings")
        assert {"glz_override", "glz_override_source"} <= table_columns(connection, "work_entry")

        settings_row = connection.execute(
            "SELECT COUNT(*), weekly_hours, christmas_eve_and_new_years_eve_off, theme FROM settings"
        ).fetchone()
        assert settings_row == (1, 39.0, 1, "dark")

        entry_row = connection.execute("SELECT date, type, comment FROM work_entry").fetchone()
        assert entry_row == ("2026-01-05", "home", "Altdaten")

        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        assert {2, 3, 4, 5, 6} <= versions

        index_names = {row[1] for row in connection.execute("PRAGMA index_list(custom_holiday)").fetchall()}
        assert "ux_custom_holiday_date" in index_names
    finally:
        connection.close()

    backups = list((data_dir / "backups").glob("db_before_migration_*.db"))
    assert backups, "Strukturelle Migration muss ein Backup erzeugen."

    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app import app; "
            "client = app.test_client(); "
            "response = client.get('/api/settings'); "
            "assert response.status_code == 200, response.status_code; "
            "payload = response.get_json(); "
            "assert payload['christmas_eve_and_new_years_eve_off'] is True, payload; "
            "assert payload['theme'] == 'dark', payload; "
            "print('settings-ok')",
        ],
        cwd=PROJECT_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert probe.returncode == 0, probe.stderr or probe.stdout
    assert "settings-ok" in probe.stdout


def test_ensure_additive_columns_repairs_legacy_schema_without_data_loss(tmp_path):
    """Die Start-Selbstheilung ergänzt Spalten idempotent und erhält Altdaten."""
    db_file = tmp_path / "legacy.db"
    create_legacy_database(db_file)

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        ensure_additive_schema_columns(engine)
        ensure_additive_schema_columns(engine)

        with engine.connect() as connection:
            settings_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(settings)")).fetchall()}
            assert {"christmas_eve_and_new_years_eve_off", "theme"} <= settings_columns
            work_columns = {row[1] for row in connection.execute(text("PRAGMA table_info(work_entry)")).fetchall()}
            assert {"glz_override", "glz_override_source"} <= work_columns

            settings_row = connection.execute(
                text("SELECT weekly_hours, christmas_eve_and_new_years_eve_off, theme FROM settings")
            ).fetchone()
            assert tuple(settings_row) == (39.0, 1, "dark")

            entry_row = connection.execute(text("SELECT date, type, comment FROM work_entry")).fetchone()
            assert tuple(entry_row) == ("2026-01-05", "home", "Altdaten")
    finally:
        engine.dispose()


def test_legacy_unique_constraint_migration_keeps_data(tmp_path):
    """Der V1-Tabellenumbau erhält Blöcke und erlaubt danach Split-Buchungen."""
    db_file = tmp_path / "unique.db"
    connection = sqlite3.connect(db_file)
    try:
        connection.execute(
            """
            CREATE TABLE work_entry (
                id INTEGER NOT NULL PRIMARY KEY,
                date VARCHAR(10) NOT NULL UNIQUE,
                type VARCHAR(20),
                start_time VARCHAR(5),
                end_time VARCHAR(5),
                comment VARCHAR(255)
            )
            """
        )
        connection.execute(
            "INSERT INTO work_entry (date, type, start_time, end_time, comment)"
            " VALUES ('2026-01-05', 'home', '08:00', '12:00', 'Vormittag')"
        )
        connection.execute(
            "INSERT INTO work_entry (date, type, start_time, end_time, comment)"
            " VALUES ('2026-01-06', 'office', '08:00', '16:00', NULL)"
        )
        connection.commit()
    finally:
        connection.close()

    engine = create_engine(f"sqlite:///{db_file}")
    try:
        with engine.begin() as connection:
            assert has_legacy_unique_date_constraint(connection) is True
            perform_unique_constraint_migration(connection)

        with engine.begin() as connection:
            assert has_legacy_unique_date_constraint(connection) is False
            rows = connection.execute(
                text("SELECT date, type, start_time, end_time, comment FROM work_entry ORDER BY date")
            ).fetchall()
            assert [tuple(row) for row in rows] == [
                ("2026-01-05", "home", "08:00", "12:00", "Vormittag"),
                ("2026-01-06", "office", "08:00", "16:00", None),
            ]
            connection.execute(
                text("INSERT INTO work_entry (date, type) VALUES ('2026-01-05', 'office')")
            )

        with engine.connect() as connection:
            same_day_blocks = connection.execute(
                text("SELECT COUNT(*) FROM work_entry WHERE date = '2026-01-05'")
            ).scalar()
            assert same_day_blocks == 2
    finally:
        engine.dispose()
