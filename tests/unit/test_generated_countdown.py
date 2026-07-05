from pathlib import Path

from privatetv.config import settings_from_mapping
from privatetv.db import connect_database, initialize_database
from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import SourceKind
from privatetv.schedule.countdown import ensure_generated_countdown_media


def _settings(tmp_path: Path):
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "program_blocks": {
                "enabled": True,
                "anchors": [{"enabled": True, "time": "20:15"}],
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
            "database": {"path": str(tmp_path / "privatetv.sqlite3")},
        }
    )


def test_ensure_generated_countdown_media_registers_existing_clip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    clip = tmp_path / "generated" / "countdowns" / "countdown_60.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"fake mp4 for tests")
    initialize_database(settings.database.path)

    with connect_database(settings.database.path) as connection:
        media_id = ensure_generated_countdown_media(connection, settings)
        connection.commit()
        assert media_id is not None
        items = MediaRepository(connection).list_media_items()

    assert len(items) == 1
    assert items[0].source_kind == SourceKind.GENERATED
    assert items[0].media_type == "generated_countdown"
    assert items[0].duration_seconds == 60
