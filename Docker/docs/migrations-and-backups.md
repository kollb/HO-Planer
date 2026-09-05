# SQLite-Migrationen, Backup und Wiederherstellung

## Datenhaltung

Die Docker-Variante speichert produktive Daten in SQLite:

```text
/app/data/database.db
```

Der Ordner `/app/data` muss außerhalb des Containers als Docker-Volume persistiert werden. Er enthält Datenbank, Protokolle und Backups.

## Migrationen

Beim Containerstart führt [`../entrypoint.sh`](../entrypoint.sh) vor Gunicorn `python migrate.py` aus. Das bestehende leichtgewichtige Migrationssystem erkennt bekannte ältere Schemata und führt nur erforderliche Änderungen aus.

Zusätzlich heilt sich die Anwendung beim Start selbst: `app.py` ergänzt vor dem ersten Datenbankzugriff alle rein additiven, datenverlustfreien Spalten (`settings.christmas_eve_and_new_years_eve_off`, `settings.theme`, `work_entry.glz_override`, `work_entry.glz_override_source`). Das ist notwendig, weil `db.create_all()` keine Spalten in bestehenden Tabellen ergänzt und ein alter Datenstand sonst jede Abfrage – auch den Import von `migrate.py` – mit `no such column` abbrechen ließe. Für diese Spalten ist kein Backup erforderlich; strukturelle Eingriffe laufen weiterhin ausschließlich über `migrate.py` mit vorherigem Backup. Beide Stellen nutzen dieselben Spaltendefinitionen aus `app.py`, damit sie nicht auseinanderlaufen können.

Vor jeder tatsächlichen strukturellen Schemaänderung erstellt `migrate.py` ein Backup:

```text
/app/data/backups/db_before_migration_YYYYMMDD_HHMMSS.db
```

Die Migration läuft transaktional. Schlägt sie fehl, wird die Transaktion zurückgerollt; das zuvor erzeugte Backup bleibt als Wiederherstellungsoption erhalten.

Die derzeit bekannten Schemaänderungen sind:

- **V1:** entfernt eine veraltete Eindeutigkeitsbeschränkung auf `work_entry.date`, damit mehrere Tagesblöcke möglich sind.
- **V2:** ergänzt `work_entry.glz_override`.
- **V3:** ergänzt `work_entry.glz_override_source`.
- **V4:** ergänzt `settings.christmas_eve_and_new_years_eve_off` mit dem rückwärtskompatiblen Standardwert `true`.
- **V5:** begrenzt eigene Sondertage auf einen Datensatz je Datum und bereinigt ältere Dubletten vor dem eindeutigen Index.
- **V6:** ergänzt `settings.theme` mit dem Standardwert `dark`.

Jede erfolgreich angewendete Version wird in `schema_migrations` erfasst. Eine Migration erzeugt nur dann ein Backup, wenn sie tatsächlich eine Schemaänderung ausführt.

## Weitere Backups

- täglich: `db_backup_YYYY-MM-DD.db`
- vor JSON-Import im Überschreibmodus: `db_before_json_import_YYYYMMDD_HHMMSS.db`
- vor Schema-Migration: `db_before_migration_YYYYMMDD_HHMMSS.db`

Backups und die SQLite-Datenbank gehören zum selben persistenten Volume. Zusätzlich sollte das Volume selbst regelmäßig außerhalb des NAS oder Servers gesichert werden.

## Wiederherstellung

1. Container stoppen, damit während des Dateiaustauschs keine SQLite-Verbindung schreibt.
2. Die gewünschte Sicherung als `database.db` in das persistente Datenverzeichnis kopieren.
3. Container wieder starten; die Migration prüft das wiederhergestellte Schema beim Start.

Beispiel für einen lokalen Docker-Volume-Mount:

```bash
docker stop ho-planer-app
cp ./data/backups/db_backup_YYYY-MM-DD.db ./data/database.db
docker start ho-planer-app
```

Eine Wiederherstellung ersetzt den aktuellen Datenstand. Daher vor dem Kopieren auch die aktuelle `database.db` separat sichern.

## Betriebshinweise für SQLite

- Backups im selben Volume schützen nicht gegen NAS-, Datenträger- oder Volume-Ausfall. Sichere `/app/data` zusätzlich auf ein getrenntes Ziel und überwache den freien Speicher.
- Restore- oder Kopieraktionen nur bei gestopptem Container durchführen. Mehrere unabhängige Schreibinstanzen dürfen nicht dieselbe SQLite-Datei verwenden.
- Bei `database is locked` die Logs prüfen und parallele Schreibzugriffe reduzieren. Der Container startet derzeit Gunicorn mit zwei Workern; das ist für die vorgesehene kleine LAN-Installation zu beobachten.
- Eine optionale Integritätsprüfung auf einer gestoppten Datenbankkopie lautet `PRAGMA integrity_check;`. WAL erst aktivieren, wenn NAS-Dateisystem und Backup-Verfahren dafür getestet sind.

## Grenzen

JSON ist für Export, Import und den Austausch mit Standalone vorgesehen. Es ersetzt SQLite nicht und ist keine automatische Datenbankmigration.
