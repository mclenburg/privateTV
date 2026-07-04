from pathlib import Path

from privatetv.config import load_settings, settings_from_mapping


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
