import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests


PROJECT_DIR = Path(__file__).resolve().parent


def wait_for_server(url, timeout=10):
    """Wartet aktiv, bis der Testserver erfolgreich antwortet."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.25)
    return False


def run_tests():
    print("🚀 Starte isolierte Flask-Test-Umgebung...")
    with tempfile.TemporaryDirectory(prefix="ho-planer-tests-") as test_data_dir:
        env = os.environ.copy()
        env["HO_PLANER_DATA_DIR"] = test_data_dir
        log_file = Path(test_data_dir) / "server-output.log"

        with log_file.open("w", encoding="utf-8") as output:
            server_process = subprocess.Popen(
                [sys.executable, "app.py"],
                stdout=output,
                stderr=subprocess.STDOUT,
                cwd=PROJECT_DIR,
                env=env,
            )
            try:
                base_url = "http://127.0.0.1:5000"
                print(f"⏳ Warte auf Flask-Testserver ({base_url})...")
                if not wait_for_server(base_url):
                    print("❌ Server antwortet nicht. Server-Ausgabe:")
                    output.flush()
                    print(log_file.read_text(encoding="utf-8"))
                    return 1

                print("🧪 Führe Pytest mit separater SQLite-Datei aus...")
                result = subprocess.call(
                    [sys.executable, "-m", "pytest", "tests"],
                    cwd=PROJECT_DIR,
                    env=env,
                )
                print("\n✅ ALLE TESTS BESTANDEN!" if result == 0 else "\n❌ TESTS FEHLGESCHLAGEN.")
                return result
            finally:
                print("🛑 Stoppe Flask-Testserver...")
                server_process.terminate()
                try:
                    server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server_process.kill()
                    server_process.wait()


if __name__ == "__main__":
    sys.exit(run_tests())
