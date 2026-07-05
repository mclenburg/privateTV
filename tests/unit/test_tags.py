from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

from privatetv.config.settings import settings_from_mapping
from privatetv.db.connection import connect_database, initialize_database
from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import MediaItem, SourceKind
from privatetv.media.tags import TagRules, tags_for_media_item
from privatetv.schedule.builder import ScheduleBuilder


def _settings(program_blocks=None):
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "program_blocks": program_blocks or {"enabled": False},
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


def _item(item_id: int, title: str, duration: int, tags=()):
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=f"file:///data/{title}.mp4",
        source_root=Path("/data"),
        title=title,
        media_type="video_file",
        duration_seconds=duration,
        tags=tuple(tags),
    )


def test_tags_for_media_item_combines_automatic_directory_and_file_rules(tmp_path: Path) -> None:
    media_dir = tmp_path / "Kinder"
    media_dir.mkdir()
    path = media_dir / "Film.mp4"
    path.write_bytes(b"x")
    item = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=path.resolve().as_uri(),
        source_root=media_dir.resolve(),
        title="Film",
        media_type="video_file",
        duration_seconds=3600,
    )
    rules = TagRules(
        directory_tags={media_dir.resolve(): ("kids", "family")},
        file_tags={path.resolve(): type("Rule", (), {"add": ("late",), "remove": ("kids",)})()},
    )

    assert tags_for_media_item(item, rules) == ("family", "late", "movie", "video_file")


def test_media_repository_stores_and_lists_tag_counts(tmp_path: Path) -> None:
    db_path = tmp_path / "test.sqlite3"
    initialize_database(db_path)
    with connect_database(db_path) as connection:
        repository = MediaRepository(connection)
        media_id = repository.upsert_media_item(_item(1, "A", 60))
        repository.replace_media_tags(media_id, ["movie", "kids"])
        connection.commit()

        assert repository.list_tag_counts() == [("kids", 1), ("movie", 1)]
        assert [item.title for item in repository.list_media_items(tag="kids")] == ["A"]


def test_schedule_builder_prefers_anchor_item_matching_allowed_tags() -> None:
    settings = _settings(
        {
            "enabled": True,
            "anchors": [
                {"enabled": True, "time": "20:15", "title": "Kinderzeit", "allowed_tags": ["kids"]}
            ],
        }
    )
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 20, 15, tzinfo=zone)
    items = [_item(1, "Z Late Movie", 3600, tags=("movie", "late")), _item(2, "A Kids", 1800, tags=("movie", "kids"))]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=start + timedelta(hours=1))

    assert result.entries[0].title == "A Kids"
