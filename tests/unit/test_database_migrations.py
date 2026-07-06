from __future__ import annotations

import sqlite3

from privatetv.db.connection import initialize_database


def test_initialize_database_migrates_existing_media_item_table(tmp_path):
    db_path = tmp_path / "privatetv.sqlite3"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE media_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_kind TEXT NOT NULL,
                source_uri TEXT NOT NULL,
                source_root TEXT,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                container TEXT,
                video_codec TEXT,
                audio_codec TEXT,
                duration_seconds REAL NOT NULL,
                file_size_bytes INTEGER,
                mtime INTEGER,
                enabled INTEGER NOT NULL DEFAULT 1,
                scan_status TEXT NOT NULL,
                scan_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_kind, source_uri)
            );
            """
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(media_item)")}
        assert "series_title" in columns
        assert "season_number" in columns
        assert "episode_number" in columns
        assert "episode_title" in columns
        assert "episode_sort_key" in columns

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "series_rotation_state" in tables

        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
        assert "idx_media_item_series" in indexes
