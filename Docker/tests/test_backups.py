import sqlite3

from app import WorkEntry, app, create_sqlite_backup, db


def test_sqlite_backup_contains_data_after_source_changes(tmp_path):
    """Eine SQLite-Sicherung bleibt lesbar, wenn sich die Quelldaten danach ändern."""
    with app.app_context():
        entry = WorkEntry(
            date="2099-12-30",
            type="office",
            start_time="08:00",
            end_time="16:00",
            comment="Backup-Referenzfall",
        )
        db.session.add(entry)
        db.session.commit()

        backup_file = tmp_path / "backup.db"
        try:
            assert create_sqlite_backup(str(backup_file)) is True
            db.session.delete(entry)
            db.session.commit()

            with sqlite3.connect(backup_file) as backup:
                row = backup.execute(
                    "SELECT date, comment FROM work_entry WHERE date = ?",
                    ("2099-12-30",),
                ).fetchone()
            assert row == ("2099-12-30", "Backup-Referenzfall")
        finally:
            WorkEntry.query.filter_by(date="2099-12-30").delete()
            db.session.commit()
