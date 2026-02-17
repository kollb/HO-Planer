#!/bin/sh

# 1. Migration ausführen (falls nötig)
python migrate.py

# 2. Eigentliche App starten
echo "Starte Flask App..."
exec python app.py