from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from privatetv.config import settings_from_mapping
from privatetv.db import MediaRepository, connect_database, initialize_database
from privatetv.domain.models import CurrentProgramme, MediaAsset, MediaItem, SourceKind
from privatetv.hazard import HazardRandomStreamProvider, HazardSelectionError
from privatetv.streaming import StreamProvider


class FirstChoiceRandom:
    def choice(self, seq):
        return seq[0]


class RecordingStreamProvider(StreamProvider):
    def __init__(self) -> None:
        self.programmes: list[CurrentProgramme] = []
        self.assets_seen: list[Sequence[MediaAsset]] = []

    async def open_stream(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> AsyncIterator[bytes]:
        self.programmes.append(programme)
        self.assets_seen.append(assets)
        yield f"{programme.media.title}\n".encode("utf-8")


def _settings(tmp_path: Path):
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    return settings_from_mapping(
        {
            "server": {"public_base_url": "http://test"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "hazard_channel": {
                "enabled": True,
                "id": "hazardtv",
                "name": "Hazard TV",
                "random_seed": 1,
                "avoid_immediate_repeat": True,
            },
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
        }
    )


def _insert_movie(settings, tmp_path: Path, name: str) -> int:
    media_file = tmp_path / f"{name}.mp4"
    media_file.write_bytes(b"movie")
    item = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=media_file.as_uri(),
        source_root=tmp_path,
        title=name,
        media_type="video_file",
        duration_seconds=60,
        file_size_bytes=media_file.stat().st_size,
        mtime=int(media_file.stat().st_mtime),
    )
    with connect_database(settings.database.path) as connection:
        return MediaRepository(connection).upsert_media_item(
            item,
            (MediaAsset(None, 0, 1, media_file, "primary", media_file.stat().st_size),),
        )


def test_hazard_provider_raises_when_no_media_exists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    provider = HazardRandomStreamProvider(settings, RecordingStreamProvider())

    async def run() -> None:
        with pytest.raises(HazardSelectionError):
            await anext(provider.open_stream())

    asyncio.run(run())


def test_hazard_provider_starts_random_movies_at_beginning_and_avoids_immediate_repeat(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    initialize_database(settings.database.path)
    _insert_movie(settings, tmp_path, "Alpha")
    _insert_movie(settings, tmp_path, "Beta")
    stream_provider = RecordingStreamProvider()
    provider = HazardRandomStreamProvider(
        settings,
        stream_provider,
        random_source=FirstChoiceRandom(),
    )

    async def run() -> tuple[bytes, bytes]:
        stream = provider.open_stream()
        first = await anext(stream)
        second = await anext(stream)
        await stream.aclose()
        return first, second

    first, second = asyncio.run(run())

    assert first == b"Alpha\n"
    assert second == b"Beta\n"
    assert [item.offset_seconds for item in stream_provider.programmes] == [0.0, 0.0]
    assert [item.schedule_entry.channel_id for item in stream_provider.programmes] == [
        "hazardtv",
        "hazardtv",
    ]
    assert stream_provider.assets_seen[0][0].role == "primary"
