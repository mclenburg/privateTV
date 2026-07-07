from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from privatetv.config import settings_from_mapping
from privatetv.domain.models import CurrentProgramme, MediaAsset, MediaItem, ScheduleEntry, SourceKind
from privatetv.streaming import FfmpegCommandFactory


def _settings(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://test"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": [str(media_dir)]},
            "schedule": {
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "shuffle_no_repeat",
            },
            "streaming": {
                "max_parallel_streams": 4,
                "output_container": "mpegts",
                "prefer_stream_copy": True,
                "transcode_when_needed": False,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
                "accepted_seek_tolerance_seconds": 12,
            },
            "database": {"path": str(tmp_path / "db.sqlite3")},
        }
    )


def _programme(source_kind: SourceKind, source_uri: str) -> CurrentProgramme:
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 7, 4, 20, 0, tzinfo=zone)
    media = MediaItem(
        id=1,
        source_kind=source_kind,
        source_uri=source_uri,
        source_root=None,
        title="Movie",
        media_type="video_file",
        duration_seconds=3600,
    )
    entry = ScheduleEntry(
        id=1,
        channel_id="privatetv",
        media_item_id=1,
        start_time=start,
        end_time=start + timedelta(hours=1),
        start_offset_seconds=0,
        title="Movie",
    )
    return CurrentProgramme(media=media, schedule_entry=entry, offset_seconds=1620.25)


def test_ffmpeg_local_file_command_uses_seek_realtime_copy_and_mpegts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    media_file = tmp_path / "movie.mp4"
    media_file.write_bytes(b"not real video")
    programme = _programme(SourceKind.LOCAL_FILE, media_file.as_uri())
    assets = [MediaAsset(None, 1, 1, media_file, "primary", media_file.stat().st_size)]

    command = FfmpegCommandFactory(settings).build(programme, assets)

    assert command.seek_tolerance_seconds == 12
    assert command.argv[:9] == (
        "/usr/bin/ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-ss",
        "1620.250",
        "-re",
        "-fflags",
        "+genpts",
    )
    assert "-c" in command.argv
    assert "copy" in command.argv
    assert "-avoid_negative_ts" in command.argv
    assert "make_zero" in command.argv
    assert command.argv[-3:] == ("-f", "mpegts", "pipe:1")


def test_ffmpeg_dvd_command_uses_concat_and_genpts(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    concat_file = tmp_path / "dvd.ffconcat"
    concat_file.write_text("ffconcat version 1.0\n", encoding="utf-8")
    programme = _programme(SourceKind.DVD_STRUCTURE, "dvd:///movie/VIDEO_TS")

    command = FfmpegCommandFactory(settings).build(programme, [], concat_file=concat_file)

    assert "-fflags" in command.argv
    assert "+genpts" in command.argv
    assert "concat" in command.argv
    assert str(concat_file) in command.argv

import pytest

from privatetv.streaming.ffmpeg import StreamPreparationError, _escape_ffconcat_path, _write_concat_file


def test_ffmpeg_command_rejects_missing_local_asset(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    missing_file = tmp_path / "missing.mp4"
    programme = _programme(SourceKind.LOCAL_FILE, missing_file.as_uri())
    assets = [MediaAsset(None, 1, 1, missing_file, "primary", None)]

    with pytest.raises(StreamPreparationError, match="does not exist"):
        FfmpegCommandFactory(settings).build(programme, assets)


def test_ffconcat_path_escaping_is_ffmpeg_style() -> None:
    assert _escape_ffconcat_path(Path("/media/O'Reilly\\Movie.VOB")) == "/media/O\\'Reilly\\\\Movie.VOB"


def test_write_concat_file_rejects_missing_vob_asset(tmp_path: Path) -> None:
    missing = tmp_path / "VTS_01_1.VOB"

    with pytest.raises(StreamPreparationError, match="missing VOB assets"):
        _write_concat_file([MediaAsset(None, 1, 1, missing, "dvd_main_title_part", None)])


def test_ffmpeg_local_file_command_transcodes_when_stream_copy_is_disabled(tmp_path: Path) -> None:
    settings = settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://test"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": [str(tmp_path / "media")]},
            "schedule": {
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "shuffle_no_repeat",
            },
            "streaming": {
                "max_parallel_streams": 4,
                "output_container": "mpegts",
                "prefer_stream_copy": False,
                "transcode_when_needed": True,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
            },
            "database": {"path": str(tmp_path / "db.sqlite3")},
        }
    )
    (tmp_path / "media").mkdir(exist_ok=True)
    media_file = tmp_path / "movie.mp4"
    media_file.write_bytes(b"not real video")
    programme = _programme(SourceKind.LOCAL_FILE, media_file.as_uri())
    assets = [MediaAsset(None, 1, 1, media_file, "primary", media_file.stat().st_size)]

    command = FfmpegCommandFactory(settings).build(programme, assets)

    assert "-c:v" in command.argv
    assert "libx264" in command.argv
    assert "-c:a" in command.argv
    assert "aac" in command.argv
    assert not ("-c" in command.argv and "copy" in command.argv)


def test_ffmpeg_dvd_command_transcodes_when_stream_copy_is_disabled(tmp_path: Path) -> None:
    settings = settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://test"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": [str(tmp_path / "media")]},
            "schedule": {
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "shuffle_no_repeat",
            },
            "streaming": {
                "max_parallel_streams": 4,
                "output_container": "mpegts",
                "prefer_stream_copy": False,
                "transcode_when_needed": True,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
            },
            "database": {"path": str(tmp_path / "db.sqlite3")},
        }
    )
    (tmp_path / "media").mkdir(exist_ok=True)
    concat_file = tmp_path / "dvd.ffconcat"
    concat_file.write_text("ffconcat version 1.0\n", encoding="utf-8")
    programme = _programme(SourceKind.DVD_STRUCTURE, "dvd:///movie/VIDEO_TS")

    command = FfmpegCommandFactory(settings).build(programme, [], concat_file=concat_file)

    assert "-c:v" in command.argv
    assert "libx264" in command.argv
    assert "-c:a" in command.argv
    assert "aac" in command.argv

import asyncio

from privatetv.streaming.ffmpeg import _SharedFfmpegSession


def test_shared_main_fanout_evicts_stalled_subscriber_without_blocking(tmp_path: Path) -> None:
    async def run() -> None:
        settings = _settings(tmp_path)
        programme = _programme(SourceKind.LOCAL_FILE, (tmp_path / "movie.mp4").as_uri())
        session = _SharedFfmpegSession(
            settings,
            FfmpegCommandFactory(settings),
            programme,
            (),
            chunk_size=16,
            on_closed=lambda _session: None,
        )
        healthy: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1)
        stalled: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=1)
        stalled.put_nowait(b"already full")
        session._subscribers.update({healthy, stalled})

        await asyncio.wait_for(session._publish(b"chunk"), timeout=1.0)

        assert await healthy.get() == b"chunk"
        assert healthy in session._subscribers
        assert stalled not in session._subscribers

    asyncio.run(run())
