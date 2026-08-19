#!/bin/sh

# Stoppt das Skript sofort, wenn ein Befehl fehlschlägt
set -e

echo "--- Container Start ---"

# 1. Datenbank-Migrationen ausführen
# Wir führen dein migrate.py aus, um sicherzustellen, dass die DB aktuell ist
if [ -f "migrate.py" ]; then
    echo "Führe Datenbank-Migrationen aus..."
    python migrate.py
fi

# 2. Gunicorn starten
# exec ist wichtig: Es ersetzt den Shell-Prozess durch Gunicorn.
# Damit empfängt Gunicorn Signale (wie 'Stop') direkt.
echo "Starte Gunicorn Server..."
exec gunicorn -w 2 -b 0.0.0.0:5000 app:app