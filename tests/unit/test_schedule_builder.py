from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from privatetv.config import settings_from_mapping
from privatetv.domain.models import MediaItem, SourceKind
from privatetv.schedule import ScheduleBuilder


def _settings(strategy: str = "alphabetical"):
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {"directories": ["tests/fixtures/media"]},
            "schedule": {
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": strategy,
            },
            "streaming": {
                "max_parallel_streams": 4,
                "output_container": "mpegts",
                "prefer_stream_copy": True,
                "transcode_when_needed": False,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
            },
            "database": {"path": ":memory:"},
        }
    )


def _item(item_id: int, title: str, duration: int) -> MediaItem:
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=f"file:///{title}.mp4",
        source_root=None,
        title=title,
        media_type="file",
        duration_seconds=duration,
    )


def test_schedule_builder_creates_continuous_timeline_without_gaps() -> None:
    settings = _settings()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 12, 0, tzinfo=zone)
    end = start + timedelta(minutes=5)
    items = [_item(1, "A", 60), _item(2, "B", 90)]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries
    assert result.entries[0].start_time == start
    for previous, current in zip(result.entries, result.entries[1:]):
        assert previous.end_time == current.start_time
    assert result.entries[-1].end_time >= end


def test_schedule_builder_ignores_items_without_database_id() -> None:
    settings = _settings()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 12, 0, tzinfo=zone)

    item = _item(1, "A", 60)
    item_without_id = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri="file:///missing-id.mp4",
        source_root=None,
        title="missing-id",
        media_type="file",
        duration_seconds=60,
    )
    result = ScheduleBuilder(settings).build([item_without_id, item], start_at=start, end_at=start + timedelta(minutes=2))

    assert {entry.media_item_id for entry in result.entries} == {1}


def _settings_with_countdown():
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "program_blocks": {
                "enabled": True,
                "anchors": [{"enabled": True, "time": "20:15", "title": "Der 20:15 Film"}],
                "generated_countdown": {"enabled": True, "max_duration_seconds": 60, "title": "Gleich geht's weiter"},
            },
            "media": {"directories": ["tests/fixtures/media"]},
            "schedule": {
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
            "database": {"path": ":memory:"},
        }
    )


def _countdown_item(item_id: int = 99) -> MediaItem:
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.GENERATED,
        source_uri="generated://privatetv/countdown-60",
        source_root=None,
        title="Gleich geht's weiter",
        media_type="generated_countdown",
        duration_seconds=60,
    )


def test_schedule_builder_inserts_generated_countdown_before_anchor_when_gap_is_at_most_one_minute() -> None:
    settings = _settings_with_countdown()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 20, 14, 30, tzinfo=zone)
    end = start + timedelta(minutes=5)
    items = [_item(1, "Movie", 120), _countdown_item()]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Gleich geht's weiter"
    assert result.entries[0].media_item_id == 99
    assert result.entries[0].start_time == start
    assert result.entries[0].end_time == datetime(2026, 1, 15, 20, 15, tzinfo=zone)
    assert result.entries[0].start_offset_seconds == 30
    assert result.entries[1].title == "Movie"
    assert result.entries[1].start_time == datetime(2026, 1, 15, 20, 15, tzinfo=zone)


def test_schedule_builder_does_not_insert_countdown_when_gap_exceeds_configured_maximum() -> None:
    settings = _settings_with_countdown()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 20, 13, 30, tzinfo=zone)
    end = start + timedelta(minutes=5)
    items = [_item(1, "Movie", 120), _countdown_item()]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Movie"
    assert all(entry.media_item_id != 99 for entry in result.entries)


def _filler(item_id: int, title: str, duration: int) -> MediaItem:
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=f"file:///{title}.mp4",
        source_root=None,
        title=title,
        media_type="filler",
        duration_seconds=duration,
    )


def _settings_with_filler_countdown():
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "program_blocks": {
                "enabled": True,
                "anchors": [{"enabled": True, "time": "20:15", "title": "Der 20:15 Film"}],
                "fillers": {"enabled": True, "directories": ["tests/fixtures/fillers"], "max_duration_seconds": 900},
                "generated_countdown": {"enabled": True, "max_duration_seconds": 60, "title": "Gleich geht's weiter"},
            },
            "media": {"directories": ["tests/fixtures/media"]},
            "schedule": {
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
            "database": {"path": ":memory:"},
        }
    )


def test_schedule_builder_uses_local_fillers_then_countdown_before_anchor() -> None:
    settings = _settings_with_filler_countdown()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 20, 0, tzinfo=zone)
    end = start + timedelta(minutes=30)
    items = [_item(1, "Long Movie", 7200), _filler(2, "Trailer", 840), _countdown_item(99)]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert [entry.title for entry in result.entries[:3]] == ["Trailer", "Gleich geht's weiter", "Long Movie"]
    assert result.entries[0].start_time == datetime(2026, 1, 15, 20, 0, tzinfo=zone)
    assert result.entries[0].end_time == datetime(2026, 1, 15, 20, 14, tzinfo=zone)
    assert result.entries[1].start_time == datetime(2026, 1, 15, 20, 14, tzinfo=zone)
    assert result.entries[1].end_time == datetime(2026, 1, 15, 20, 15, tzinfo=zone)
    assert result.entries[2].start_time == datetime(2026, 1, 15, 20, 15, tzinfo=zone)


def test_schedule_builder_ignores_fillers_when_program_blocks_are_disabled() -> None:
    settings = _settings(strategy="alphabetical")
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 20, 0, tzinfo=zone)
    end = start + timedelta(minutes=30)
    items = [_item(1, "Long Movie", 7200), _filler(2, "Trailer", 840)]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Long Movie"
    assert all(entry.title != "Trailer" for entry in result.entries)
