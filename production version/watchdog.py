import ctypes
import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "data" / "automat.db"
APP_URL = "http://127.0.0.1:5000/api/settings"
MUTEX_NAME = "Local\\AutomatAutorunWatchdog"
LOG_PATH = ROOT / "data" / "watchdog.log"


def log(message):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def acquire_single_instance():
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle or ctypes.windll.kernel32.GetLastError() == 183:
        return None
    return handle


def autorun_enabled():
    if not DATABASE.exists():
        return False
    try:
        with sqlite3.connect(DATABASE, timeout=2) as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='autorun'").fetchone()
    except sqlite3.Error:
        return False
    if not row:
        return False
    try:
        return bool(json.loads(row[0]))
    except (TypeError, json.JSONDecodeError):
        return False


def server_alive():
    try:
        with urllib.request.urlopen(APP_URL, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def start_server():
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    if pythonw.exists():
        executable = pythonw
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [str(executable), str(ROOT / "run.py")],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )


def main():
    handle = acquire_single_instance()
    if handle is None:
        return
    log("Watchdog bezi. Program spusti jen pri zapnutem Autorun.")
    while True:
        if autorun_enabled() and not server_alive():
            log("Autorun je zapnuty a server nebezi. Spoustim Automat.")
            start_server()
            time.sleep(15)
        time.sleep(5)


if __name__ == "__main__":
    main()
