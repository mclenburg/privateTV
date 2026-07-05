from pathlib import Path

from privatetv.config import load_settings, settings_from_mapping, settings_to_mapping


def test_load_example_config() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    assert settings.channel.id == "privatetv"
    assert settings.channel.name == "PrivateTV"
    assert settings.streaming.max_parallel_streams == 4
    assert settings.schedule.timezone == "Europe/Berlin"


def test_extensions_are_normalized() -> None:
    settings = settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
            "channel": {"id": "c", "name": "C"},
            "media": {"directories": ["."], "extensions": ["MP4", ".MKV"]},
            "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
            "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe"},
            "database": {"path": "var/test.sqlite3"},
        }
    )

    assert settings.media.extensions == (".mp4", ".mkv")


def test_hazard_channel_defaults_to_disabled() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    assert settings.hazard_channel.enabled is False
    assert settings.hazard_channel.name == "Hazard TV"

import pytest

from privatetv.domain.errors import ConfigurationError


def _minimal_config(tmp_path: Path | None = None):
    media_dir = str(tmp_path or Path('.'))
    return {
        "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
        "channel": {"id": "c", "name": "C"},
        "media": {"directories": [media_dir]},
        "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
        "streaming": {"max_parallel_streams": 4, "output_container": "mpegts", "prefer_stream_copy": True, "transcode_when_needed": False, "ffmpeg_path": "/usr/bin/ffmpeg", "ffprobe_path": "/usr/bin/ffprobe"},
        "database": {"path": "var/test.sqlite3"},
    }


def test_public_base_url_must_be_absolute_http_url(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["server"]["public_base_url"] = "privatetv.local:9988"

    with pytest.raises(ConfigurationError, match="public_base_url"):
        settings_from_mapping(raw)


def test_hazard_random_seed_must_be_integer_when_set(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["hazard_channel"] = {"enabled": True, "id": "hazard", "random_seed": "not-an-int"}

    with pytest.raises(ConfigurationError, match="random_seed"):
        settings_from_mapping(raw)


def test_program_blocks_default_to_disabled(tmp_path: Path) -> None:
    settings = settings_from_mapping(_minimal_config(tmp_path))

    assert settings.program_blocks.enabled is False
    assert settings.program_blocks.generated_countdown.enabled is False
    assert settings.program_blocks.generated_countdown.max_duration_seconds == 60


def test_program_blocks_countdown_must_not_exceed_one_minute(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["program_blocks"] = {
        "enabled": True,
        "generated_countdown": {"enabled": True, "max_duration_seconds": 61},
    }

    with pytest.raises(ConfigurationError, match="must not be greater than 60"):
        settings_from_mapping(raw)


def test_program_blocks_roundtrip_preserves_scaffolding(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["program_blocks"] = {
        "enabled": True,
        "anchors": [
            {
                "enabled": True,
                "time": "20:15",
                "title": "Der 20:15 Film",
                "allowed_tags": ["movie"],
            }
        ],
        "fillers": {
            "enabled": False,
            "directories": [str(tmp_path / "fillers")],
            "if_no_filler": "continue_current_mode",
        },
        "generated_countdown": {
            "enabled": True,
            "max_duration_seconds": 60,
            "title": "Gleich geht's weiter",
        },
    }

    settings = settings_from_mapping(raw)
    roundtrip = settings_from_mapping(settings_to_mapping(settings))

    assert roundtrip.program_blocks.enabled is True
    assert roundtrip.program_blocks.anchors[0].time == "20:15"
    assert roundtrip.program_blocks.anchors[0].allowed_tags == ("movie",)
    assert roundtrip.program_blocks.fillers.if_no_filler == "continue_current_mode"


def test_program_blocks_filler_max_duration_is_validated(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["program_blocks"] = {
        "enabled": True,
        "fillers": {"enabled": True, "max_duration_seconds": 0},
    }

    with pytest.raises(ConfigurationError, match="fillers.max_duration_seconds"):
        settings_from_mapping(raw)


def test_program_blocks_parse_time_blocks(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["program_blocks"] = {
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
    }

    settings = settings_from_mapping(raw)

    assert settings.program_blocks.blocks[0].start == "06:00"
    assert settings.program_blocks.blocks[0].duration_seconds == 9000
    assert settings.program_blocks.blocks[0].allowed_tags == ("kids",)


def test_program_blocks_reject_too_short_blocks(tmp_path: Path) -> None:
    raw = _minimal_config(tmp_path)
    raw["program_blocks"] = {
        "enabled": True,
        "blocks": [{"enabled": True, "start": "06:00", "duration": "00:00:30"}],
    }

    with pytest.raises(ConfigurationError, match="duration"):
        settings_from_mapping(raw)
