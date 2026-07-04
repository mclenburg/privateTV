from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from privatetv.config import settings_from_mapping
from privatetv.db import MediaRepository, ScheduleRepository, connect_database, initialize_database
from privatetv.domain.models import CurrentProgramme, MediaAsset, MediaItem, ScheduleEntry, SourceKind
from privatetv.http import create_app
from privatetv.streaming import StreamProvider


class FakeStreamProvider(StreamProvider):
    def __init__(self, chunks: tuple[bytes, ...] = (b"abc", b"def")) -> None:
        self.chunks = chunks
        self.seen_offsets: list[float] = []
        self.seen_assets: list[Sequence[MediaAsset]] = []

    async def open_stream(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> AsyncIterator[bytes]:
        self.seen_offsets.append(programme.offset_seconds)
        self.seen_assets.append(assets)
        for chunk in self.chunks:
            yield chunk


def _settings(tmp_path: Path, *, max_parallel_streams: int = 4):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    return settings_from_mapping(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 9988,
                "public_base_url": "http://privatetv.test:9988",
            },
            "channel": {
                "id": "privatetv",
                "name": "PrivateTV",
                "group_title": "Local",
                "language": "de",
            },
            "media": {"directories": [str(media_dir)]},
            "schedule": {
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "shuffle_no_repeat",
            },
            "streaming": {
                "max_parallel_streams": max_parallel_streams,
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


async def _get_text(settings, path: str, stream_provider: StreamProvider | None = None) -> tuple[int, str, str]:
    server = TestServer(create_app(settings, stream_provider=stream_provider))
    client = TestClient(server)
    await client.start_server()
    try:
        response = await client.get(path)
        return response.status, response.headers.get("Content-Type", ""), await response.text()
    finally:
        await client.close()


def test_http_playlist_endpoint_returns_stable_m3u(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/playlist.m3u"))

    assert status == 200
    assert "audio/x-mpegurl" in content_type
    assert '#EXTM3U url-tvg="http://privatetv.test:9988/xmltv.xml"' in body
    assert "http://privatetv.test:9988/stream/main.ts" in body


def test_http_xmltv_endpoint_returns_empty_channel_when_no_schedule_exists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/xmltv.xml"))

    assert status == 200
    assert "application/xml" in content_type
    assert '<channel id="privatetv">' in body
    assert "<programme" not in body


def test_http_health_is_degraded_without_schedule(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/health"))

    assert status == 200
    assert "application/json" in content_type
    assert '"status": "degraded"' in body
    assert '"max_parallel_streams": 4' in body


def test_stream_endpoint_returns_503_when_no_current_programme_exists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/stream/main.ts", FakeStreamProvider()))

    assert status == 503
    assert "application/json" in content_type
    assert "no_current_programme" in body


def test_stream_endpoint_streams_current_programme_with_offset(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = FakeStreamProvider()
    _insert_current_programme(settings, tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/stream/main.ts", provider))

    assert status == 200
    assert "video/MP2T" in content_type
    assert body == "abcdef"
    assert provider.seen_offsets[0] >= 0
    assert provider.seen_assets[0][0].role == "primary"


def _insert_current_programme(settings, tmp_path: Path) -> None:
    initialize_database(settings.database.path)
    media_file = tmp_path / "movie.mp4"
    media_file.write_bytes(b"movie")
    now = datetime.now(settings.schedule.zoneinfo).replace(microsecond=0)
    start = now - timedelta(minutes=27)
    end = now + timedelta(minutes=33)
    media = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=media_file.as_uri(),
        source_root=tmp_path,
        title="Movie",
        media_type="video_file",
        duration_seconds=3600,
        file_size_bytes=media_file.stat().st_size,
        mtime=int(media_file.stat().st_mtime),
    )
    asset = MediaAsset(None, 0, 1, media_file, "primary", media_file.stat().st_size)
    with connect_database(settings.database.path) as connection:
        media_id = MediaRepository(connection).upsert_media_item(media, (asset,))
        ScheduleRepository(connection).append_entries(
            [
                ScheduleEntry(
                    id=None,
                    channel_id=settings.channel.id,
                    media_item_id=media_id,
                    start_time=start,
                    end_time=end,
                    start_offset_seconds=0,
                    title="Movie",
                    description="Fixture movie",
                )
            ]
        )


def test_http_startup_extends_schedule_when_horizon_is_below_minimum(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    now = datetime.now(settings.schedule.zoneinfo).replace(microsecond=0)
    with connect_database(settings.database.path) as connection:
        media_id = MediaRepository(connection).upsert_media_item(
            MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri="file:///short-horizon.mp4",
                source_root=None,
                title="Short Horizon",
                media_type="video_file",
                duration_seconds=3600,
            )
        )
        ScheduleRepository(connection).append_entries(
            [
                ScheduleEntry(
                    id=None,
                    channel_id=settings.channel.id,
                    media_item_id=media_id,
                    start_time=now,
                    end_time=now + timedelta(days=2),
                    start_offset_seconds=0,
                    title="Short Horizon",
                    description="Fixture movie",
                )
            ]
        )

    status, content_type, body = asyncio.run(_get_text(settings, "/health"))

    assert status == 200
    assert "application/json" in content_type
    assert '"status": "ok"' in body
    assert '"schedule_needs_extension": false' in body
    assert '"schedule_minimum_days_ahead": 3' in body
    assert '"schedule_target_days_ahead": 5' in body


def test_hazard_stream_endpoint_is_disabled_by_default(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    status, content_type, body = asyncio.run(_get_text(settings, "/stream/hazard.ts"))

    assert status == 404
    assert "application/json" in content_type
    assert "hazard_disabled" in body

class FakeHazardProvider:
    async def open_stream(self) -> AsyncIterator[bytes]:
        yield b"hazard"


def _hazard_settings(tmp_path: Path, *, max_parallel_streams: int = 4):
    media_dir = tmp_path / "hazard-media"
    media_dir.mkdir()
    return settings_from_mapping(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 9988,
                "public_base_url": "http://privatetv.test:9988",
            },
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "hazard_channel": {"enabled": True, "id": "hazardtv", "name": "Hazard TV"},
            "media": {"directories": [str(media_dir)]},
            "schedule": {
                "minimum_days_ahead": 3,
                "days_ahead": 5,
                "timezone": "Europe/Berlin",
                "rebuild_hour": 3,
                "strategy": "shuffle_no_repeat",
            },
            "streaming": {
                "max_parallel_streams": max_parallel_streams,
                "output_container": "mpegts",
                "prefer_stream_copy": True,
                "transcode_when_needed": False,
                "ffmpeg_path": "/usr/bin/ffmpeg",
                "ffprobe_path": "/usr/bin/ffprobe",
            },
            "database": {"path": str(tmp_path / "hazard.sqlite3")},
            "logging": {"level": "INFO"},
        }
    )


def _insert_hazard_media(settings, tmp_path: Path) -> None:
    initialize_database(settings.database.path)
    media_file = tmp_path / "hazard.mp4"
    media_file.write_bytes(b"movie")
    media = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=media_file.as_uri(),
        source_root=tmp_path,
        title="Hazard Movie",
        media_type="video_file",
        duration_seconds=60,
        file_size_bytes=media_file.stat().st_size,
        mtime=int(media_file.stat().st_mtime),
    )
    asset = MediaAsset(None, 0, 1, media_file, "primary", media_file.stat().st_size)
    with connect_database(settings.database.path) as connection:
        MediaRepository(connection).upsert_media_item(media, (asset,))


async def _get_text_with_hazard(settings, path: str, hazard_provider) -> tuple[int, str, str]:
    server = TestServer(create_app(settings, hazard_provider=hazard_provider))
    client = TestClient(server)
    await client.start_server()
    try:
        response = await client.get(path)
        return response.status, response.headers.get("Content-Type", ""), await response.text()
    finally:
        await client.close()


def test_hazard_stream_endpoint_streams_when_enabled_and_media_exists(tmp_path: Path) -> None:
    settings = _hazard_settings(tmp_path)
    _insert_hazard_media(settings, tmp_path)

    status, content_type, body = asyncio.run(
        _get_text_with_hazard(settings, "/stream/hazard.ts", FakeHazardProvider())
    )

    assert status == 200
    assert "video/MP2T" in content_type
    assert body == "hazard"


def test_hazard_stream_endpoint_returns_503_when_enabled_without_media(tmp_path: Path) -> None:
    settings = _hazard_settings(tmp_path)

    status, content_type, body = asyncio.run(
        _get_text_with_hazard(settings, "/stream/hazard.ts", FakeHazardProvider())
    )

    assert status == 503
    assert "application/json" in content_type
    assert "hazard_no_media" in body


def test_stream_endpoint_returns_503_when_current_asset_is_missing(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    provider = FakeStreamProvider()
    _insert_current_programme(settings, tmp_path)
    (tmp_path / "movie.mp4").unlink()

    status, content_type, body = asyncio.run(_get_text(settings, "/stream/main.ts", provider))

    assert status == 503
    assert "application/json" in content_type
    assert "missing media assets" in body
    assert provider.seen_offsets == []
