SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS media_item (
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
    series_title TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    episode_title TEXT,
    episode_sort_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(source_kind, source_uri)
);

CREATE INDEX IF NOT EXISTS idx_media_item_series
ON media_item(series_title, season_number, episode_number);

CREATE TABLE IF NOT EXISTS media_asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    media_item_id INTEGER NOT NULL,
    asset_order INTEGER NOT NULL,
    path TEXT NOT NULL,
    role TEXT NOT NULL,
    file_size_bytes INTEGER,
    FOREIGN KEY(media_item_id) REFERENCES media_item(id) ON DELETE CASCADE,
    UNIQUE(media_item_id, asset_order)
);

CREATE TABLE IF NOT EXISTS media_tag (
    media_item_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'scan',
    FOREIGN KEY(media_item_id) REFERENCES media_item(id) ON DELETE CASCADE,
    PRIMARY KEY(media_item_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_media_tag_tag
ON media_tag(tag, media_item_id);

CREATE TABLE IF NOT EXISTS schedule_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL,
    media_item_id INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    start_offset_seconds REAL NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(media_item_id) REFERENCES media_item(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_schedule_entry_channel_time
ON schedule_entry(channel_id, start_time, end_time);

CREATE TABLE IF NOT EXISTS series_rotation_state (
    rotation_name TEXT PRIMARY KEY,
    series_title TEXT NOT NULL,
    media_item_id INTEGER NOT NULL,
    season_number INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    episode_sort_key TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(media_item_id) REFERENCES media_item(id) ON DELETE CASCADE
);

"""
