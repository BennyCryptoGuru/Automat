import ctypes
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import webbrowser
from pathlib import Path
from threading import Timer

from waitress import serve

from automat.app import create_app


APP_LABEL = "Automat"
APP_URL = "http://127.0.0.1:5000"
DATA_DIR = Path(__file__).resolve().parent / "data"


def chrome_candidates():
    paths = []
    env = os.getenv("AUTOMAT_CHROME_BINARY") or os.getenv("AUTOMAT_BROWSER_BINARY")
    if env:
        paths.append(Path(env))
    local = Path(os.getenv("LOCALAPPDATA", ""))
    programs = Path(os.getenv("PROGRAMFILES", "C:/Program Files"))
    programs_x86 = Path(os.getenv("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
    paths.extend([
        programs / "Google/Chrome/Application/chrome.exe",
        programs_x86 / "Google/Chrome/Application/chrome.exe",
        local / "Google/Chrome/Application/chrome.exe",
    ])
    for command in ("chrome", "google-chrome"):
        found = shutil.which(command)
        if found:
            paths.append(Path(found))
    seen = set()
    for path in paths:
        if not path or not path.is_file():
            continue
        resolved = str(path.resolve()).lower()
        if resolved in seen:
            continue
        seen.add(resolved)
        yield path


def open_app_ui():
    for chrome in chrome_candidates():
        try:
            subprocess.Popen([str(chrome), APP_URL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
    webbrowser.open(APP_URL)


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
    handle = ctypes.windll.kernel32.CreateMutexW(None, True, "Local\\AutomatBrowserStudio")
    last_error = ctypes.windll.kernel32.GetLastError()
    if not handle or last_error == 183:
        open_app_ui()
        print(f"Automat is already running. Opening the existing instance: {APP_URL}")
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
        Timer(1.0, open_app_ui).start()
    print(f"Automat ({APP_LABEL}) is running at {APP_URL}")
    serve(app, host="127.0.0.1", port=5000, threads=8)
