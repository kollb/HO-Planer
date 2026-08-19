import subprocess
import sys
import time
import os
import requests

def wait_for_server(url, timeout=5):
    """Wartet aktiv, bis der Server antwortet, statt nur zu schlafen."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            requests.get(url)
            return True
        except requests.ConnectionError:
            time.sleep(0.5)
    return False

def run_tests():
    print("🚀 Starte Test-Umgebung für Flask...")

    # 1. Flask Server im Hintergrund starten
    # WICHTIG: Wir starten app.py, nicht http.server!
    server_process = subprocess.Popen(
        [sys.executable, "app.py"],
        stdout=subprocess.DEVNULL, # Setze dies auf None, wenn du Server-Logs sehen willst
        stderr=subprocess.DEVNULL,
        cwd=os.getcwd() # Sicherstellen, dass wir im richtigen Ordner sind
    )

    try:
        port = 5000 # Flask Standard
        base_url = f"http://127.0.0.1:{port}"
        
        print(f"⏳ Warte auf Flask-Server ({base_url})...")
        
        # Besser als sturres Sleep: Wir pingen den Server an
        if wait_for_server(base_url):
            print("✅ Server ist online!")
        else:
            print("❌ Server antwortet nicht. Abbruch.")
            return 1

        print("🧪 Führe Pytest aus...")
        
        # 2. Pytest starten
        # Wir rufen "python -m pytest" auf, das löst oft auch die Pfad-Probleme
        # Wir testen den Ordner "tests/"
        test_cmd = [sys.executable, "-m", "pytest", "tests"]
        
        # Optional: Nur GUI Tests, falls gewünscht:
        # test_cmd = [sys.executable, "-m", "pytest", "tests/test_gui.py"]

        result = subprocess.call(test_cmd)

        if result == 0:
            print("\n✅ ALLE TESTS BESTANDEN! Bereit zum Einchecken.")
        else:
            print("\n❌ TESTS FEHLGESCHLAGEN.")
        
        return result

    finally:
        # 3. Server beenden
        print("🛑 Stoppe Flask-Server...")
        server_process.terminate()
        # Manchmal braucht Flask/Werkzeug etwas Nachdruck:
        try:
            server_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    # Prüfen ob 'requests' installiert ist, sonst Fehler verhindern
    try:
        import requests
    except ImportError:
        print("Bitte installiere 'requests' für dieses Skript: pip install requests")
        sys.exit(1)

    sys.exit(run_tests())