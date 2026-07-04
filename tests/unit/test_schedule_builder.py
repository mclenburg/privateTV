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
