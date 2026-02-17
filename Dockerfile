FROM python:slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Berlin

# System-Pakete
RUN apt-get update && apt-get install -y tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App-Code & Migrations-Skripte kopieren
COPY . .

# WICHTIG: Entrypoint ausführbar machen
RUN chmod +x entrypoint.sh

RUN mkdir -p /app/data

EXPOSE 5000

# Wir nutzen ENTRYPOINT statt CMD, damit das Skript immer läuft
ENTRYPOINT ["./entrypoint.sh"]