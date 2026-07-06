from __future__ import annotations

from pathlib import Path

import pytest

from privatetv.config import settings_from_mapping
from privatetv.db import MediaRepository, connect_database, initialize_database
from privatetv.media.local_file_scanner import LocalFileScanner
from privatetv.media.probe import ProbeResult
from privatetv.media.series import SeriesDetector
from privatetv.media.tags import tags_for_media_item


class FakeProbe:
    def probe(self, path: Path) -> ProbeResult:
        return ProbeResult(
            path=path,
            duration_seconds=24 * 60,
            container="matroska",
            video_codec="h264",
            audio_codec="aac",
            file_size_bytes=path.stat().st_size,
            mtime=int(path.stat().st_mtime),
        )


def _settings(tmp_path: Path, *, custom_patterns=None):
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {
                "directories": [str(tmp_path)],
                "recursive": True,
                "extensions": [".mp4", ".mkv"],
                "series_detection": {
                    "enabled": True,
                    "auto_patterns": True,
                    "custom_patterns": custom_patterns or [],
                },
            },
            "schedule": {
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
            "database": {"path": str(tmp_path / "db.sqlite3")},
        }
    )


def test_custom_series_pattern_detects_folder_season_episode(tmp_path: Path) -> None:
    media = tmp_path / "ALF" / "1" / "03_Katzenjammer.mkv"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"episode")
    settings = _settings(
        tmp_path,
        custom_patterns=[
            {"name": "series season episode", "pattern": "{seriesName}/{seasonNo}/{episodeNo}_*"}
        ],
    )

    item, _assets = LocalFileScanner(settings, FakeProbe()).scan()[0]

    assert item.media_type == "episode"
    assert item.series_title == "ALF"
    assert item.season_number == 1
    assert item.episode_number == 3
    assert item.episode_sort_key == "alf|0001|0003"
    assert {"series", "episode"}.issubset(set(tags_for_media_item(item)))


def test_auto_series_pattern_detects_sxxexx_filename(tmp_path: Path) -> None:
    media = tmp_path / "Parker Lewis" / "S02E10 - Der Test.mkv"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"episode")

    item, _assets = LocalFileScanner(_settings(tmp_path), FakeProbe()).scan()[0]

    assert item.media_type == "episode"
    assert item.series_title == "Parker Lewis"
    assert item.season_number == 2
    assert item.episode_number == 10
    assert item.episode_title == "Der Test"


def test_series_detection_does_not_mark_filler_as_episode(tmp_path: Path) -> None:
    filler = tmp_path / "ALF" / "1" / "03_Ad.mkv"
    filler.parent.mkdir(parents=True)
    filler.write_bytes(b"filler")
    settings = _settings(
        tmp_path,
        custom_patterns=[{"pattern": "{seriesName}/{seasonNo}/{episodeNo}_*"}],
    )

    item, _assets = LocalFileScanner(
        settings,
        FakeProbe(),
        directories=(tmp_path,),
        media_type="filler",
        progress_kind="filler",
    ).scan()[0]

    assert item.media_type == "filler"
    assert item.series_title is None


def test_database_persists_series_metadata(tmp_path: Path) -> None:
    media = tmp_path / "ALF" / "1" / "03_Katzenjammer.mkv"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"episode")
    settings = _settings(
        tmp_path,
        custom_patterns=[{"pattern": "{seriesName}/{seasonNo}/{episodeNo}_*"}],
    )
    item, assets = LocalFileScanner(settings, FakeProbe()).scan()[0]

    initialize_database(settings.database.path)
    with connect_database(settings.database.path) as connection:
        repo = MediaRepository(connection)
        media_id = repo.upsert_media_item(item, assets)
        loaded = repo.list_media_items()[0]

    assert media_id == 1
    assert loaded.series_title == "ALF"
    assert loaded.season_number == 1
    assert loaded.episode_number == 3
    assert loaded.media_type == "episode"


def test_custom_pattern_must_contain_required_fields(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="seriesName"):
        _settings(tmp_path, custom_patterns=[{"pattern": "{seriesName}/{episodeNo}_*"}])


def test_custom_pattern_can_repeat_series_placeholder(tmp_path: Path) -> None:
    media = tmp_path / "ALF" / "Season 1" / "ALF - S01E04 - Besuch.mkv"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"episode")
    settings = _settings(
        tmp_path,
        custom_patterns=[
            {
                "pattern": "{seriesName}/Season {seasonNo}/{seriesName} - S{seasonNo}E{episodeNo} - {episodeTitle}"
            }
        ],
    )

    item, _assets = LocalFileScanner(settings, FakeProbe()).scan()[0]

    assert item.series_title == "ALF"
    assert item.season_number == 1
    assert item.episode_number == 4
    assert item.episode_title == "Besuch"
