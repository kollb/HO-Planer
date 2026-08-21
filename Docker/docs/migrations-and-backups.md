# SQLite-Migrationen, Backup und Wiederherstellung

## Datenhaltung

Die Docker-Variante speichert produktive Daten in SQLite:

```text
/app/data/database.db
```

Der Ordner `/app/data` muss außerhalb des Containers als Docker-Volume persistiert werden. Er enthält Datenbank, Protokolle und Backups.

## Migrationen

Beim Containerstart führt [`../entrypoint.sh`](../entrypoint.sh) vor Gunicorn `python migrate.py` aus. Das bestehende leichtgewichtige Migrationssystem erkennt bekannte ältere Schemata und führt nur erforderliche Änderungen aus.

Vor jeder tatsächlichen strukturellen Schemaänderung erstellt `migrate.py` ein Backup:

```text
/app/data/backups/db_before_migration_YYYYMMDD_HHMMSS.db
```

Die Migration läuft transaktional. Schlägt sie fehl, wird die Transaktion zurückgerollt; das zuvor erzeugte Backup bleibt als Wiederherstellungsoption erhalten.

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

## Grenzen

JSON ist für Export, Import und den Austausch mit Standalone vorgesehen. Es ersetzt SQLite nicht und ist keine automatische Datenbankmigration.
