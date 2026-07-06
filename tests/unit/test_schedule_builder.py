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


def _settings_with_distributed_fillers():
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "program_blocks": {
                "enabled": True,
                "anchors": [{"enabled": True, "time": "20:15", "title": "Der 20:15 Film"}],
                "fillers": {
                    "enabled": True,
                    "directories": ["tests/fixtures/fillers"],
                    "max_duration_seconds": 300,
                    "distribution": "between_programmes",
                    "insert_between_movies": True,
                    "max_consecutive_fillers": 3,
                    "max_total_filler_block_seconds": 120,
                    "prefer_filler_after_minutes": 45,
                    "min_gap_between_filler_blocks_minutes": 20,
                },
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


def test_schedule_builder_distributes_short_fillers_between_programmes_before_anchor() -> None:
    settings = _settings_with_distributed_fillers()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 17, 0, tzinfo=zone)
    end = datetime(2026, 1, 15, 21, 0, tzinfo=zone)
    items = [
        _item(1, "Feature A", 3600),
        _item(2, "Feature B", 3600),
        _item(3, "Primetime Movie", 7200),
        _filler(10, "Toyota Affen", 35),
        _filler(11, "DEA Familie", 30),
        _countdown_item(99),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)
    titles = [entry.title for entry in result.entries]

    assert "Toyota Affen" in titles or "DEA Familie" in titles
    filler_positions = [index for index, title in enumerate(titles) if title in {"Toyota Affen", "DEA Familie"}]
    assert filler_positions
    assert any(0 < position < len(titles) - 1 for position in filler_positions)


def test_schedule_builder_uses_shorter_programme_to_reduce_filler_wall_before_anchor() -> None:
    settings = _settings_with_distributed_fillers()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 19, 0, tzinfo=zone)
    end = datetime(2026, 1, 15, 21, 0, tzinfo=zone)
    items = [
        _item(1, "Long Movie", 7200),
        _item(2, "Short Episode", 3600),
        _filler(10, "Commercial", 30),
        _countdown_item(99),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Short Episode"
    assert result.entries[0].end_time <= datetime(2026, 1, 15, 20, 15, tzinfo=zone)


def _tagged_item(item_id: int, title: str, duration: int, *tags: str) -> MediaItem:
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=f"file:///{title}.mp4",
        source_root=None,
        title=title,
        media_type="file",
        duration_seconds=duration,
        tags=tuple(tags),
    )


def _settings_with_kids_block():
    raw = {
        "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
        "channel": {"id": "privatetv", "name": "PrivateTV"},
        "program_blocks": {
            "enabled": True,
            "blocks": [
                {
                    "enabled": True,
                    "start": "06:00",
                    "duration": "02:30:00",
                    "title": "PrivateTV Kinderzeit",
                    "allowed_tags": ["kids"],
                    "denied_tags": ["nicht_fuer_kinder"],
                }
            ],
        },
        "media": {"directories": ["tests/fixtures/media"]},
        "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
        "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe"},
        "database": {"path": ":memory:"},
    }
    return settings_from_mapping(raw)


def test_schedule_builder_prefers_matching_items_inside_time_block() -> None:
    settings = _settings_with_kids_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 6, 0, tzinfo=zone)
    end = start + timedelta(hours=1)
    items = [
        _tagged_item(1, "Action Movie", 1800, "movie"),
        _tagged_item(2, "Simsala Grimm", 1500, "kids", "series"),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Simsala Grimm"
    assert all(entry.media_item_id == 2 for entry in result.entries[:2])


def test_schedule_builder_uses_fitting_item_before_upcoming_block() -> None:
    settings = _settings_with_kids_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 5, 30, tzinfo=zone)
    end = datetime(2026, 1, 15, 6, 30, tzinfo=zone)
    items = [
        _tagged_item(1, "Long Movie", 7200, "movie"),
        _tagged_item(2, "Short Feature", 1500, "movie"),
        _tagged_item(3, "Kids Episode", 1200, "kids"),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries[0].title == "Short Feature"
    assert result.entries[0].end_time <= datetime(2026, 1, 15, 6, 0, tzinfo=zone)
    assert result.entries[1].title == "Kids Episode"


def _settings_with_skip_empty_kids_block():
    raw = {
        "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
        "channel": {"id": "privatetv", "name": "PrivateTV"},
        "program_blocks": {
            "enabled": True,
            "blocks": [
                {
                    "enabled": True,
                    "start": "06:00",
                    "duration": "02:30:00",
                    "title": "PrivateTV Kinderzeit",
                    "allowed_tags": ["kids"],
                    "if_empty": "skip_block",
                }
            ],
        },
        "media": {"directories": ["tests/fixtures/media"]},
        "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
        "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe"},
        "database": {"path": ":memory:"},
    }
    return settings_from_mapping(raw)


def test_schedule_builder_skips_empty_time_block_when_configured() -> None:
    settings = _settings_with_skip_empty_kids_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 6, 0, tzinfo=zone)
    end = datetime(2026, 1, 15, 9, 0, tzinfo=zone)
    items = [_tagged_item(1, "Action Movie", 1800, "movie")]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries
    assert result.entries[0].title == "Action Movie"
    assert result.entries[0].start_time == datetime(2026, 1, 15, 8, 30, tzinfo=zone)


def test_schedule_builder_keeps_empty_time_block_when_continue_current_mode() -> None:
    settings = _settings_with_kids_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 6, 0, tzinfo=zone)
    end = datetime(2026, 1, 15, 7, 0, tzinfo=zone)
    items = [_tagged_item(1, "Action Movie", 1800, "movie")]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)

    assert result.entries
    assert result.entries[0].title == "Action Movie"
    assert result.entries[0].start_time == start


def _episode(item_id: int, series: str, season: int, episode: int, title: str, duration: int = 1200, *tags: str) -> MediaItem:
    return MediaItem(
        id=item_id,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=f"file:///{series}/S{season:02d}E{episode:02d}.mkv",
        source_root=None,
        title=title,
        media_type="episode",
        duration_seconds=duration,
        tags=tuple(tags or ("vorabendserie", "episode", "series")),
        series_title=series,
        season_number=season,
        episode_number=episode,
        episode_title=title,
        episode_sort_key=f"{series.casefold()}:s{season:04d}:e{episode:04d}",
    )


def _settings_with_series_rotation_block():
    raw = {
        "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://127.0.0.1:9988"},
        "channel": {"id": "privatetv", "name": "PrivateTV"},
        "program_blocks": {
            "enabled": True,
            "blocks": [
                {
                    "enabled": True,
                    "start": "18:00",
                    "duration": "00:45:00",
                    "title": "Vorabendserie",
                    "mode": "series_rotation",
                    "allowed_tags": ["vorabendserie"],
                    "series": {"on_series_end": "restart", "remember_position": True},
                }
            ],
        },
        "media": {"directories": ["tests/fixtures/media"]},
        "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
        "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe"},
        "database": {"path": ":memory:"},
    }
    return settings_from_mapping(raw)


def test_series_rotation_block_schedules_episodes_in_episode_order() -> None:
    settings = _settings_with_series_rotation_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 18, 0, tzinfo=zone)
    items = [
        _item(50, "Movie", 1800),
        _episode(3, "ALF", 1, 3, "ALF S01E03"),
        _episode(1, "ALF", 1, 1, "ALF S01E01"),
        _episode(2, "ALF", 1, 2, "ALF S01E02"),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=start + timedelta(hours=1))

    assert [entry.title for entry in result.entries[:3]] == ["ALF S01E01", "ALF S01E02", "ALF S01E03"]
    assert result.series_rotation_updates[-1].rotation_name == "Vorabendserie"
    assert result.series_rotation_updates[-1].episode_number == 3


def test_series_rotation_continues_from_persisted_state() -> None:
    from privatetv.domain.models import SeriesRotationSnapshot

    settings = _settings_with_series_rotation_block()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 18, 0, tzinfo=zone)
    state = {"Vorabendserie": SeriesRotationSnapshot(series_title="ALF", media_item_id=1, season_number=1, episode_number=1, episode_sort_key="alf:s0001:e0001")}
    items = [
        _episode(1, "ALF", 1, 1, "ALF S01E01"),
        _episode(2, "ALF", 1, 2, "ALF S01E02"),
        _episode(3, "ALF", 1, 3, "ALF S01E03"),
    ]

    result = ScheduleBuilder(settings, series_rotation_state=state).build(items, start_at=start, end_at=start + timedelta(minutes=30))

    assert result.entries[0].title == "ALF S01E02"


def test_schedule_builder_rotates_fillers_fairly_instead_of_reusing_first_two() -> None:
    settings = _settings_with_distributed_fillers()
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 1, 15, 10, 0, tzinfo=zone)
    end = datetime(2026, 1, 15, 20, 20, tzinfo=zone)
    items = [
        _item(1, "Film 1", 3600),
        _item(2, "Film 2", 3600),
        _item(3, "Film 3", 3600),
        _item(4, "Prime", 7200),
        _filler(10, "Filler A", 30),
        _filler(11, "Filler B", 30),
        _filler(12, "Filler C", 30),
        _filler(13, "Filler D", 30),
        _filler(14, "Filler E", 30),
        _countdown_item(99),
    ]

    result = ScheduleBuilder(settings).build(items, start_at=start, end_at=end)
    filler_titles = [entry.title for entry in result.entries if entry.title.startswith("Filler ")]

    assert len(filler_titles) >= 3
    assert len(set(filler_titles[:5])) >= 3
    for previous, current in zip(filler_titles, filler_titles[1:]):
        assert previous != current
