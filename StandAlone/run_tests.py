import subprocess
import sys
import time
import os

def run_tests():
    print("🚀 Starte Test-Umgebung...")

    # 1. Lokalen Webserver im Hintergrund starten
    # Wir nutzen subprocess.Popen, damit er parallel läuft
    server_process = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8000"],
        stdout=subprocess.DEVNULL, # Unterdrückt Server-Logs (sauberer)
        stderr=subprocess.DEVNULL
    )

    try:
        print("⏳ Warte auf Server (Port 8000)...")
        time.sleep(2) # Kurz warten, bis der Server bereit ist

        print("🧪 Führe Tests aus...")
        # 2. Pytest starten
        # Rückgabewert 0 = Alles OK, 1 = Fehler
        result = subprocess.call([sys.executable, "-m", "pytest", "test_standalone.py"])

        if result == 0:
            print("\n✅ ALLE TESTS BESTANDEN! Du kannst einchecken.")
        else:
            print("\n❌ TESTS FEHLGESCHLAGEN. Bitte prüfen.")
        
        return result

    finally:
        # 3. Server garantiert beenden (auch bei Fehlern)
        print("🛑 Stoppe Server...")
        server_process.terminate()

if __name__ == "__main__":
    sys.exit(run_tests())