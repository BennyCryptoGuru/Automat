import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS sites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    locator TEXT NOT NULL,
    alternatives TEXT NOT NULL DEFAULT '[]',
    frame_path TEXT NOT NULL DEFAULT '[]',
    parent_id INTEGER REFERENCES elements(id) ON DELETE SET NULL,
    preview_path TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    element_id INTEGER REFERENCES elements(id) ON DELETE SET NULL,
    parameters TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    username_element_id INTEGER NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
    password_element_id INTEGER NOT NULL REFERENCES elements(id) ON DELETE CASCADE,
    submit_element_id INTEGER REFERENCES elements(id) ON DELETE SET NULL,
    extra_actions TEXT NOT NULL DEFAULT '[]',
    username_cipher BLOB NOT NULL,
    password_cipher BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_elements_site ON elements(site_id);
CREATE INDEX IF NOT EXISTS idx_actions_workflow ON actions(workflow_id, position);
CREATE INDEX IF NOT EXISTS idx_credentials_site ON credentials(site_id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection):
        credential_columns = {row["name"] for row in connection.execute("PRAGMA table_info(credentials)").fetchall()}
        if "extra_actions" not in credential_columns:
            connection.execute("ALTER TABLE credentials ADD COLUMN extra_actions TEXT NOT NULL DEFAULT '[]'")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def all(self, sql, values=()):
        with self.connect() as connection:
            return [self._row(row) for row in connection.execute(sql, values).fetchall()]

    def one(self, sql, values=()):
        with self.connect() as connection:
            row = connection.execute(sql, values).fetchone()
            return self._row(row) if row else None

    def execute(self, sql, values=()):
        with self.connect() as connection:
            cursor = connection.execute(sql, values)
            return cursor.lastrowid

    @staticmethod
    def _row(row):
        value = dict(row)
        for key in ("alternatives", "frame_path", "metadata", "parameters", "extra_actions"):
            if key in value:
                try:
                    value[key] = json.loads(value[key])
                except (TypeError, json.JSONDecodeError):
                    value[key] = [] if key in ("alternatives", "frame_path", "extra_actions") else {}
        if "enabled" in value:
            value["enabled"] = bool(value["enabled"])
        return value
