from __future__ import annotations

import asyncio
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from privatetv.config import load_settings, settings_from_mapping, settings_to_mapping
from privatetv.http import create_app


def _settings(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
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
                "strategy": "shuffle_no_repeat",
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
            "logging": {"level": "INFO"},
        }
    )


async def _get(settings, path: str, *, config_path: Path | None = None):
    client = TestClient(TestServer(create_app(settings, config_path=config_path)))
    await client.start_server()
    try:
        response = await client.get(path)
        return response.status, response.headers.get("Content-Type", ""), await response.text()
    finally:
        await client.close()


async def _post(settings, path: str, data: dict, *, config_path: Path):
    client = TestClient(TestServer(create_app(settings, config_path=config_path)))
    await client.start_server()
    try:
        response = await client.post(path, data=data)
        return response.status, response.headers.get("Content-Type", ""), await response.text()
    finally:
        await client.close()


def test_root_serves_configuration_page(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get(settings, "/"))

    assert status == 200
    assert "text/html" in content_type
    assert "PrivateTV configuration" in body
    assert "server-side PrivateTV configuration" in body


def test_config_browse_lists_server_directories(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    child = tmp_path / "media" / "Movies"
    child.mkdir()

    status, content_type, body = asyncio.run(_get(settings, f"/config/browse?path={tmp_path / 'media'}"))

    assert status == 200
    assert "text/html" in content_type
    assert "Select directories from the filesystem of the PrivateTV server" in body
    assert "Movies/" in body


def test_settings_to_mapping_roundtrip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    roundtrip = settings_from_mapping(settings_to_mapping(settings))

    assert roundtrip.channel.name == "PrivateTV"
    assert roundtrip.media.directories == settings.media.directories


def test_config_post_saves_yaml_file(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    config_path = tmp_path / "config.yml"
    data = settings_to_mapping(settings)
    data["channel"]["name"] = "New Name"
    form = _flatten_for_form(data)

    status, content_type, body = asyncio.run(_post(settings, "/config", form, config_path=config_path))

    assert status == 200
    assert "text/html" in content_type
    assert "Saved" in body
    saved = load_settings(config_path)
    assert saved.channel.name == "New Name"


def _flatten_for_form(data: dict) -> dict[str, str]:
    form: dict[str, str] = {}
    for section, section_values in data.items():
        if not isinstance(section_values, dict):
            continue
        for key, value in section_values.items():
            full_key = f"{section}.{key}"
            if isinstance(value, dict):
                for subkey, subvalue in value.items():
                    form[f"{full_key}.{subkey}"] = _form_value(subvalue)
            else:
                form[full_key] = _form_value(value)
    form["media.directories"] = "\n".join(data["media"]["directories"])
    form["media.extensions"] = "\n".join(data["media"]["extensions"])
    return form


def _form_value(value) -> str:
    if isinstance(value, bool):
        return "on" if value else ""
    if value is None:
        return ""
    return str(value)
