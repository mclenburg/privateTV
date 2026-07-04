from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from privatetv.config import settings_from_mapping
from privatetv.db import MediaRepository, ScheduleRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, MediaItem, ScheduleEntry, SourceKind
from privatetv.schedule import ScheduleMaintainer


def _settings(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)
    return settings_from_mapping(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 9988,
                "public_base_url": "http://privatetv.test:9988",
            },
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": [str(media_dir)]},
            "schedule": {
                "minimum_days_ahead": 3,
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "alphabetical",
            },
            "streaming": {
                "max_parallel_streams": 4,
                "output_container": "mpegts",
                "prefer_stream_copy": True,
                "transcode_when_needed": False,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
            },
            "database": {"path": str(tmp_path / "privatetv.sqlite3")},
        }
    )


def _insert_media(connection, tmp_path: Path) -> int:
    media_file = tmp_path / "media" / "movie.mp4"
    media_file.write_bytes(b"movie")
    media = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=media_file.as_uri(),
        source_root=tmp_path / "media",
        title="Movie",
        media_type="video_file",
        duration_seconds=3600,
        file_size_bytes=media_file.stat().st_size,
        mtime=int(media_file.stat().st_mtime),
    )
    asset = MediaAsset(None, 0, 1, media_file, "primary", media_file.stat().st_size)
    return MediaRepository(connection).upsert_media_item(media, (asset,))


def test_schedule_maintainer_extends_empty_schedule_to_target_horizon(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    now = datetime(2026, 7, 4, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with connect_database(settings.database.path) as connection:
        _insert_media(connection, tmp_path)
        result = ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
        schedule_until = ScheduleRepository(connection).get_schedule_end(settings.channel.id)

    assert result.inserted_entries > 0
    assert result.schedule_until_before is None
    assert schedule_until is not None
    assert schedule_until >= now + timedelta(days=5)


def test_schedule_maintainer_does_not_extend_when_minimum_horizon_is_met(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    now = datetime(2026, 7, 4, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with connect_database(settings.database.path) as connection:
        media_id = _insert_media(connection, tmp_path)
        ScheduleRepository(connection).append_entries(
            [
                ScheduleEntry(
                    id=None,
                    channel_id=settings.channel.id,
                    media_item_id=media_id,
                    start_time=now,
                    end_time=now + timedelta(days=4),
                    start_offset_seconds=0,
                    title="Movie",
                    description="Fixture movie",
                )
            ]
        )
        result = ScheduleMaintainer(settings).ensure_schedule(connection, now=now)

    assert result.had_enough_schedule
    assert result.inserted_entries == 0
    assert result.schedule_until_after == now + timedelta(days=4)


def test_schedule_maintainer_extends_when_horizon_falls_below_minimum(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    now = datetime(2026, 7, 4, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))

    with connect_database(settings.database.path) as connection:
        media_id = _insert_media(connection, tmp_path)
        ScheduleRepository(connection).append_entries(
            [
                ScheduleEntry(
                    id=None,
                    channel_id=settings.channel.id,
                    media_item_id=media_id,
                    start_time=now,
                    end_time=now + timedelta(days=2),
                    start_offset_seconds=0,
                    title="Movie",
                    description="Fixture movie",
                )
            ]
        )
        result = ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
        schedule_until = ScheduleRepository(connection).get_schedule_end(settings.channel.id)

    assert result.inserted_entries > 0
    assert result.schedule_until_before == now + timedelta(days=2)
    assert schedule_until is not None
    assert schedule_until >= now + timedelta(days=5)
