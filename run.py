import ctypes
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from waitress import serve

from automat.app import create_app


APP_LABEL = "vyvojova verze"
APP_URL = "http://127.0.0.1:5000"
DATA_DIR = Path(__file__).resolve().parent / "data"


def ensure_output_streams():
    if sys.stdout is not None and sys.stderr is not None:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stream = open(DATA_DIR / "automat-server.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AutomatBrowserStudio")
    if not handle or ctypes.windll.kernel32.GetLastError() == 183:
        webbrowser.open(APP_URL)
        print(f"Automat uz bezi. Oteviram existujici instanci: {APP_URL}")
        return None
    return handle


def setting_enabled(key):
    database = DATA_DIR / "automat.db"
    if not database.exists():
        return False
    try:
        with sqlite3.connect(database, timeout=2) as connection:
            row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    except sqlite3.Error:
        return False
    if not row:
        return False
    try:
        return bool(json.loads(row[0]))
    except (TypeError, json.JSONDecodeError):
        return False


if __name__ == "__main__":
    ensure_output_streams()
    instance_handle = acquire_single_instance()
    if instance_handle is None:
        sys.exit(0)
    app = create_app({"ENABLE_AUTORUN_MONITOR": True})
    if not setting_enabled("stealth_run"):
        Timer(1.0, lambda: webbrowser.open(APP_URL)).start()
    print(f"Automat ({APP_LABEL}) bezi na {APP_URL}")
    serve(app, host="127.0.0.1", port=5000, threads=8)
