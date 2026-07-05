from __future__ import annotations

import sqlite3
from datetime import datetime

from privatetv.db.media_repository import media_item_from_row
from privatetv.domain.models import MediaItem, ScheduleEntry, ScanStatus


class ScheduleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def list_schedulable_media_items(self) -> list[MediaItem]:
        rows = self._connection.execute(
            """
            SELECT id, source_kind, source_uri, source_root, title, media_type,
                   duration_seconds, enabled, container, video_codec, audio_codec,
                   file_size_bytes, mtime, scan_status, scan_error
            FROM media_item
            WHERE enabled = 1
              AND scan_status = ?
              AND duration_seconds > 0
            ORDER BY title COLLATE NOCASE, id
            """,
            (ScanStatus.OK.value,),
        ).fetchall()
        return [media_item_from_row(row) for row in rows]

    def get_schedule_end(self, channel_id: str) -> datetime | None:
        row = self._connection.execute(
            "SELECT MAX(end_time) AS end_time FROM schedule_entry WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
        return datetime.fromisoformat(row["end_time"]) if row and row["end_time"] else None

    def append_entries(self, entries: list[ScheduleEntry]) -> int:
        if not entries:
            return 0
        self._connection.executemany(
            """
            INSERT INTO schedule_entry (
                channel_id, media_item_id, start_time, end_time,
                start_offset_seconds, title, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    entry.channel_id,
                    entry.media_item_id,
                    entry.start_time.isoformat(),
                    entry.end_time.isoformat(),
                    entry.start_offset_seconds,
                    entry.title,
                    entry.description,
                )
                for entry in entries
            ],
        )
        return len(entries)

    def replace_entries_from(self, channel_id: str, from_time: datetime, entries: list[ScheduleEntry]) -> int:
        self._connection.execute(
            "DELETE FROM schedule_entry WHERE channel_id = ? AND start_time >= ?",
            (channel_id, from_time.isoformat()),
        )
        return self.append_entries(entries)


    def refresh_titles_from_media(self, channel_id: str | None = None) -> int:
        where_clause = ""
        params: tuple[object, ...] = ()
        if channel_id is not None:
            where_clause = "WHERE schedule_entry.channel_id = ?"
            params = (channel_id,)
        cursor = self._connection.execute(
            f"""
            UPDATE schedule_entry
            SET title = (
                SELECT media_item.title
                FROM media_item
                WHERE media_item.id = schedule_entry.media_item_id
            )
            {where_clause}
            """,
            params,
        )
        return int(cursor.rowcount or 0)

    def list_entries(
        self,
        channel_id: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[ScheduleEntry]:
        clauses = ["channel_id = ?"]
        params: list[object] = [channel_id]
        if start_at is not None:
            clauses.append("end_time > ?")
            params.append(start_at.isoformat())
        if end_at is not None:
            clauses.append("start_time < ?")
            params.append(end_at.isoformat())
        rows = self._connection.execute(
            f"""
            SELECT id, channel_id, media_item_id, start_time, end_time,
                   start_offset_seconds, title, description
            FROM schedule_entry
            WHERE {' AND '.join(clauses)}
            ORDER BY start_time, id
            """,
            tuple(params),
        ).fetchall()
        return [schedule_entry_from_row(row) for row in rows]

    def list_entries_with_media(
        self,
        channel_id: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[tuple[ScheduleEntry, MediaItem]]:
        clauses = ["s.channel_id = ?"]
        params: list[object] = [channel_id]
        if start_at is not None:
            clauses.append("s.end_time > ?")
            params.append(start_at.isoformat())
        if end_at is not None:
            clauses.append("s.start_time < ?")
            params.append(end_at.isoformat())
        rows = self._connection.execute(
            f"""
            SELECT
              s.id AS schedule_id, s.channel_id, s.media_item_id, s.start_time, s.end_time,
              s.start_offset_seconds, s.title AS schedule_title, s.description,
              m.id, m.source_kind, m.source_uri, m.source_root, m.title, m.media_type,
              m.duration_seconds, m.enabled, m.container, m.video_codec, m.audio_codec,
              m.file_size_bytes, m.mtime, m.scan_status, m.scan_error
            FROM schedule_entry s
            JOIN media_item m ON m.id = s.media_item_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.start_time, s.id
            """,
            tuple(params),
        ).fetchall()
        return [(schedule_entry_from_joined_row(row), media_item_from_row(row)) for row in rows]


def schedule_entry_from_row(row: sqlite3.Row) -> ScheduleEntry:
    return ScheduleEntry(
        id=int(row["id"]),
        channel_id=str(row["channel_id"]),
        media_item_id=int(row["media_item_id"]),
        start_time=datetime.fromisoformat(str(row["start_time"])),
        end_time=datetime.fromisoformat(str(row["end_time"])),
        start_offset_seconds=float(row["start_offset_seconds"]),
        title=str(row["title"]),
        description=row["description"],
    )


def schedule_entry_from_joined_row(row: sqlite3.Row) -> ScheduleEntry:
    return ScheduleEntry(
        id=int(row["schedule_id"]),
        channel_id=str(row["channel_id"]),
        media_item_id=int(row["media_item_id"]),
        start_time=datetime.fromisoformat(str(row["start_time"])),
        end_time=datetime.fromisoformat(str(row["end_time"])),
        start_offset_seconds=float(row["start_offset_seconds"]),
        title=str(row["schedule_title"]),
        description=row["description"],
    )
