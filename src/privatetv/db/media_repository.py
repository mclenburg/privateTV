from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime

from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind

_MEDIA_SELECT = """
SELECT id, source_kind, source_uri, source_root, title, media_type,
       duration_seconds, enabled, container, video_codec, audio_codec,
       file_size_bytes, mtime, scan_status, scan_error,
       series_title, season_number, episode_number, episode_title, episode_sort_key,
       (SELECT group_concat(tag, ',') FROM media_tag WHERE media_tag.media_item_id = media_item.id) AS tags_csv
FROM media_item
"""


class MediaRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def upsert_media_item(self, item: MediaItem, assets: Iterable[MediaAsset] = ()) -> int:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO media_item (
                source_kind, source_uri, source_root, title, media_type, container,
                video_codec, audio_codec, duration_seconds, file_size_bytes, mtime,
                enabled, scan_status, scan_error, series_title, season_number, episode_number,
                episode_title, episode_sort_key, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_kind, source_uri) DO UPDATE SET
                source_root = excluded.source_root,
                title = excluded.title,
                media_type = excluded.media_type,
                container = excluded.container,
                video_codec = excluded.video_codec,
                audio_codec = excluded.audio_codec,
                duration_seconds = excluded.duration_seconds,
                file_size_bytes = excluded.file_size_bytes,
                mtime = excluded.mtime,
                enabled = excluded.enabled,
                scan_status = excluded.scan_status,
                scan_error = excluded.scan_error,
                series_title = excluded.series_title,
                season_number = excluded.season_number,
                episode_number = excluded.episode_number,
                episode_title = excluded.episode_title,
                episode_sort_key = excluded.episode_sort_key,
                updated_at = excluded.updated_at
            """,
            (
                item.source_kind.value,
                item.source_uri,
                str(item.source_root) if item.source_root else None,
                item.title,
                item.media_type,
                item.container,
                item.video_codec,
                item.audio_codec,
                item.duration_seconds,
                item.file_size_bytes,
                item.mtime,
                1 if item.enabled else 0,
                item.scan_status.value,
                item.scan_error,
                item.series_title,
                item.season_number,
                item.episode_number,
                item.episode_title,
                item.episode_sort_key,
                now,
                now,
            ),
        )
        media_item_id = self.get_media_item_id(item.source_kind, item.source_uri)
        if media_item_id is None:
            raise RuntimeError(f"Upsert did not create media item: {item.source_uri}")

        self._connection.execute("DELETE FROM media_asset WHERE media_item_id = ?", (media_item_id,))
        for asset in assets:
            self._connection.execute(
                """
                INSERT INTO media_asset (
                    media_item_id, asset_order, path, role, file_size_bytes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    media_item_id,
                    asset.asset_order,
                    str(asset.path),
                    asset.role,
                    asset.file_size_bytes,
                ),
            )
        return media_item_id

    def replace_media_tags(self, media_item_id: int, tags: Iterable[str], *, source: str = "scan") -> None:
        normalized = sorted({str(tag).strip().lower().replace(" ", "_") for tag in tags if str(tag).strip()})
        self._connection.execute("DELETE FROM media_tag WHERE media_item_id = ?", (media_item_id,))
        self._connection.executemany(
            "INSERT INTO media_tag(media_item_id, tag, source) VALUES (?, ?, ?)",
            [(media_item_id, tag, source) for tag in normalized],
        )

    def get_media_item_id(self, source_kind: SourceKind, source_uri: str) -> int | None:
        row = self._connection.execute(
            "SELECT id FROM media_item WHERE source_kind = ? AND source_uri = ?",
            (source_kind.value, source_uri),
        ).fetchone()
        return int(row["id"]) if row else None

    def mark_missing_except(self, source_kind: SourceKind, seen_source_uris: set[str]) -> int:
        rows = self._connection.execute(
            "SELECT source_uri FROM media_item WHERE source_kind = ? AND scan_status = ?",
            (source_kind.value, ScanStatus.OK.value),
        ).fetchall()
        missing = [row["source_uri"] for row in rows if row["source_uri"] not in seen_source_uris]
        for source_uri in missing:
            self._connection.execute(
                """
                UPDATE media_item
                SET scan_status = ?, enabled = 0, updated_at = datetime('now')
                WHERE source_kind = ? AND source_uri = ?
                """,
                (ScanStatus.MISSING.value, source_kind.value, source_uri),
            )
        return len(missing)

    def list_media_items(self, *, tag: str | None = None) -> list[MediaItem]:
        where = ""
        params: tuple[object, ...] = ()
        if tag:
            where = "WHERE EXISTS (SELECT 1 FROM media_tag mt WHERE mt.media_item_id = media_item.id AND mt.tag = ?)"
            params = (tag.strip().lower().replace(" ", "_"),)
        rows = self._connection.execute(
            f"""
            {_MEDIA_SELECT}
            {where}
            ORDER BY title COLLATE NOCASE, id
            """,
            params,
        ).fetchall()
        return [media_item_from_row(row) for row in rows]

    def list_playable_media_items(self) -> list[MediaItem]:
        rows = self._connection.execute(
            f"""
            {_MEDIA_SELECT}
            WHERE enabled = 1
              AND scan_status = ?
              AND source_kind IN (?, ?, ?)
              AND duration_seconds > 0
            ORDER BY title COLLATE NOCASE, id
            """,
            (ScanStatus.OK.value, SourceKind.LOCAL_FILE.value, SourceKind.DVD_STRUCTURE.value, SourceKind.GENERATED.value),
        ).fetchall()
        return [media_item_from_row(row) for row in rows]

    def list_tag_counts(self) -> list[tuple[str, int]]:
        rows = self._connection.execute(
            """
            SELECT tag, COUNT(*) AS count
            FROM media_tag
            GROUP BY tag
            ORDER BY tag COLLATE NOCASE
            """
        ).fetchall()
        return [(str(row["tag"]), int(row["count"])) for row in rows]

    def list_assets(self, media_item_id: int) -> list[MediaAsset]:
        rows = self._connection.execute(
            """
            SELECT id, media_item_id, asset_order, path, role, file_size_bytes
            FROM media_asset
            WHERE media_item_id = ?
            ORDER BY asset_order, id
            """,
            (media_item_id,),
        ).fetchall()
        return [media_asset_from_row(row) for row in rows]


def media_item_from_row(row: sqlite3.Row) -> MediaItem:
    from pathlib import Path

    keys = set(row.keys())
    tags_csv = row["tags_csv"] if "tags_csv" in keys else None
    tags = tuple(sorted({tag for tag in str(tags_csv or "").split(",") if tag}))
    return MediaItem(
        id=int(row["id"]),
        source_kind=SourceKind(str(row["source_kind"])),
        source_uri=str(row["source_uri"]),
        source_root=Path(row["source_root"]) if row["source_root"] else None,
        title=str(row["title"]),
        media_type=str(row["media_type"]),
        duration_seconds=float(row["duration_seconds"]),
        enabled=bool(row["enabled"]),
        container=row["container"],
        video_codec=row["video_codec"],
        audio_codec=row["audio_codec"],
        file_size_bytes=row["file_size_bytes"],
        mtime=row["mtime"],
        scan_status=ScanStatus(str(row["scan_status"])),
        scan_error=row["scan_error"],
        tags=tags,
        series_title=row["series_title"] if "series_title" in keys else None,
        season_number=row["season_number"] if "season_number" in keys else None,
        episode_number=row["episode_number"] if "episode_number" in keys else None,
        episode_title=row["episode_title"] if "episode_title" in keys else None,
        episode_sort_key=row["episode_sort_key"] if "episode_sort_key" in keys else None,
    )


def media_asset_from_row(row: sqlite3.Row) -> MediaAsset:
    from pathlib import Path

    return MediaAsset(
        id=int(row["id"]),
        media_item_id=int(row["media_item_id"]),
        asset_order=int(row["asset_order"]),
        path=Path(str(row["path"])),
        role=str(row["role"]),
        file_size_bytes=row["file_size_bytes"],
    )
