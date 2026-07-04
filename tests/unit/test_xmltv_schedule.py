from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from privatetv.config import settings_from_mapping
from privatetv.domain.models import ScheduleEntry
from privatetv.tvh import render_xmltv


def _settings():
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV", "language": "de"},
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


def test_xmltv_uses_dynamic_timezone_offset() -> None:
    settings = _settings()
    zone = ZoneInfo("Europe/Berlin")
    winter = datetime(2026, 1, 15, 20, 15, tzinfo=zone)
    summer = datetime(2026, 7, 15, 20, 15, tzinfo=zone)
    entries = [
        ScheduleEntry(None, "privatetv", 1, winter, winter + timedelta(hours=1), 0, "Winter"),
        ScheduleEntry(None, "privatetv", 2, summer, summer + timedelta(hours=1), 0, "Summer"),
    ]

    xml = render_xmltv(settings, entries)

    assert 'start="20260115201500 +0100"' in xml
    assert 'start="20260715201500 +0200"' in xml


def test_xmltv_adds_duration_category_and_description() -> None:
    settings = _settings()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 7, 15, 20, 15, tzinfo=zone)
    entry = ScheduleEntry(
        None,
        "privatetv",
        1,
        start,
        start + timedelta(minutes=90),
        0,
        "Example & Movie",
        "Local <media> file",
    )

    xml = render_xmltv(settings, [entry])

    assert "Example &amp; Movie" in xml
    assert "Local &lt;media&gt; file" in xml
    assert '<category lang="en">Movie</category>' in xml
    assert '<length units="seconds">5400</length>' in xml


def test_xmltv_rejects_mismatching_channel_id() -> None:
    settings = _settings()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 7, 15, 20, 15, tzinfo=zone)
    entry = ScheduleEntry(None, "other", 1, start, start + timedelta(minutes=1), 0, "Wrong")

    with pytest.raises(ValueError, match="does not match"):
        render_xmltv(settings, [entry])


def test_xmltv_rejects_naive_times() -> None:
    settings = _settings()
    start = datetime(2026, 7, 15, 20, 15)
    entry = ScheduleEntry(None, "privatetv", 1, start, start + timedelta(minutes=1), 0, "Naive")

    with pytest.raises(ValueError, match="timezone-aware"):
        render_xmltv(settings, [entry])
