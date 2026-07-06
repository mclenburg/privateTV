from __future__ import annotations

import sqlite3
from pathlib import Path

from privatetv.db.schema import SCHEMA_SQL


MEDIA_ITEM_SERIES_COLUMNS: dict[str, str] = {
    "series_title": "TEXT",
    "season_number": "INTEGER",
    "episode_number": "INTEGER",
    "episode_title": "TEXT",
    "episode_sort_key": "TEXT",
}


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(path: Path) -> None:
    with connect_database(path) as connection:
        # Create all base tables that are missing.  For existing SQLite tables,
        # CREATE TABLE IF NOT EXISTS intentionally does not add new columns; the
        # compatibility migration below handles that case.
        connection.executescript(SCHEMA_SQL)
        _migrate_database(connection)
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) "
            "VALUES (1, datetime('now'))"
        )
        connection.execute(
            "INSERT OR IGNORE INTO schema_version(version, applied_at) "
            "VALUES (32, datetime('now'))"
        )


def _migrate_database(connection: sqlite3.Connection) -> None:
    _ensure_media_item_series_columns(connection)
    _ensure_series_rotation_state_table(connection)
    _ensure_series_indexes(connection)


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_media_item_series_columns(connection: sqlite3.Connection) -> None:
    columns = _table_columns(connection, "media_item")
    for column_name, column_type in MEDIA_ITEM_SERIES_COLUMNS.items():
        if column_name not in columns:
            connection.execute(f"ALTER TABLE media_item ADD COLUMN {column_name} {column_type}")


def _ensure_series_rotation_state_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS series_rotation_state (
            rotation_name TEXT PRIMARY KEY,
            series_title TEXT NOT NULL,
            media_item_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            episode_number INTEGER NOT NULL,
            episode_sort_key TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(media_item_id) REFERENCES media_item(id) ON DELETE CASCADE
        )
        """
    )


def _ensure_series_indexes(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_item_series
        ON media_item(series_title, season_number, episode_number)
        """
    )
