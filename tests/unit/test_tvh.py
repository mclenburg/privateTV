from pathlib import Path

from privatetv.config import load_settings, settings_from_mapping
from privatetv.tvh import render_empty_xmltv, render_m3u, stream_url, xmltv_url


def test_m3u_contains_stable_channel_stream_and_xmltv_url() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    m3u = render_m3u(settings)

    assert m3u.startswith('#EXTM3U url-tvg="http://127.0.0.1:9988/xmltv.xml"')
    assert 'tvg-id="privatetv"' in m3u
    assert 'tvg-name="PrivateTV"' in m3u
    assert 'group-title="Local"' in m3u
    assert 'http://127.0.0.1:9988/stream/main.ts' in m3u


def test_m3u_includes_logo_when_configured() -> None:
    settings = settings_from_mapping(
        {
            "server": {"public_base_url": "http://pi.local:9988"},
            "channel": {
                "id": "privatetv",
                "name": "PrivateTV",
                "icon": "http://pi.local/icon.png",
                "group_title": "Movies",
                "language": "en",
            },
            "media": {"directories": ["tests/fixtures/media"]},
            "schedule": {"days_ahead": 5, "timezone": "Europe/Berlin", "rebuild_hour": 3, "strategy": "alphabetical"},
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

    m3u = render_m3u(settings)

    assert 'tvg-logo="http://pi.local/icon.png"' in m3u
    assert 'group-title="Movies"' in m3u


def test_xmltv_contains_channel() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    xmltv = render_empty_xmltv(settings)

    assert '<channel id="privatetv">' in xmltv
    assert '<display-name lang="de">PrivateTV</display-name>' in xmltv


def test_public_urls_are_stable_and_base_url_is_not_duplicated() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    assert stream_url(settings) == "http://127.0.0.1:9988/stream/main.ts"
    assert xmltv_url(settings) == "http://127.0.0.1:9988/xmltv.xml"


def test_hazard_channel_is_not_in_m3u_by_default() -> None:
    settings = load_settings(Path("config/privatetv.example.yml"))

    m3u = render_m3u(settings)

    assert "Hazard TV" not in m3u
    assert "/stream/hazard.ts" not in m3u


def test_hazard_channel_can_be_added_to_m3u() -> None:
    settings = settings_from_mapping(
        {
            "server": {"public_base_url": "http://pi.local:9988"},
            "channel": {
                "id": "privatetv",
                "name": "PrivateTV",
                "group_title": "Movies",
                "language": "en",
            },
            "hazard_channel": {
                "enabled": True,
                "id": "hazardtv",
                "name": "Hazard TV",
                "group_title": "Movies",
                "language": "en",
            },
            "media": {"directories": ["tests/fixtures/media"]},
            "schedule": {
                "minimum_days_ahead": 3,
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

    m3u = render_m3u(settings)

    assert 'tvg-id="privatetv"' in m3u
    assert 'tvg-id="hazardtv"' in m3u
    assert "http://pi.local:9988/stream/main.ts" in m3u
    assert "http://pi.local:9988/stream/hazard.ts" in m3u
