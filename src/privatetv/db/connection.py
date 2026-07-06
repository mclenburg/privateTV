from __future__ import annotations

import sqlite3
from pathlib import Path

from privatetv.db.schema import SCHEMA_SQL


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(path: Path) -> None:
    with connect_database(path) as connection:
        connection.executescript(SCHEMA_SQL)
        _ensure_media_item_columns(connection)
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) "
            "VALUES (1, datetime('now'))"
        )


def _ensure_media_item_columns(connection: sqlite3.Connection) -> None:
    existing = {str(row["name"]) for row in connection.execute("PRAGMA table_info(media_item)")}
    columns = {
        "series_title": "TEXT",
        "season_number": "INTEGER",
        "episode_number": "INTEGER",
        "episode_title": "TEXT",
        "episode_sort_key": "TEXT",
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE media_item ADD COLUMN {name} {definition}")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_item_series "
        "ON media_item(series_title, season_number, episode_number)"
    )
