import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


PROJECT_DIR = Path(__file__).resolve().parent
BASE_URL = "http://127.0.0.1:5000"
REQUIRED_MODULES = ("flask", "flask_sqlalchemy", "holidays", "pdfplumber", "pytest", "playwright", "pytest_playwright")


def preflight():
    missing = [module for module in REQUIRED_MODULES if importlib.util.find_spec(module) is None]
    if missing:
        print("INFRASTRUCTURE ERROR: Missing Python packages: " + ", ".join(missing))
        print("Install the dependencies declared in Docker/requirements.txt, then retry.")
        return False

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).is_file():
                print("INFRASTRUCTURE ERROR: Playwright Chromium browser binary is missing.")
                print("Install the configured Chromium browser, then retry.")
                return False
    except Exception as error:
        print(f"INFRASTRUCTURE ERROR: Playwright browser preflight failed: {error}")
        return False
    return True


def wait_for_server(url, server_process, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server_process.poll() is not None:
            return False
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except URLError:
            time.sleep(0.25)
    return False


def server_output(log_file):
    output = log_file.read_text(encoding="utf-8", errors="replace").strip()
    return output or "<server produced no output; port 5000 may already be occupied>"


def run_tests():
    print("Starting isolated Flask test environment...")
    if not preflight():
        return 2

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
                print(f"Waiting for Flask test server at {BASE_URL}...")
                if not wait_for_server(BASE_URL, server_process):
                    output.flush()
                    print("INFRASTRUCTURE ERROR: Flask test server did not become reachable.")
                    print(server_output(log_file))
                    return 1

                print("Running pytest with an isolated SQLite database...")
                result = subprocess.call(
                    [sys.executable, "-m", "pytest", "tests"],
                    cwd=PROJECT_DIR,
                    env=env,
                )
                print("ALL TESTS PASSED." if result == 0 else "TESTS FAILED.")
                return result
            finally:
                print("Stopping Flask test server...")
                server_process.terminate()
                try:
                    server_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    server_process.kill()
                    server_process.wait()
                output.flush()
                if server_process.returncode not in (0, -15):
                    print("Server output:")
                    print(server_output(log_file))


if __name__ == "__main__":
    sys.exit(run_tests())
