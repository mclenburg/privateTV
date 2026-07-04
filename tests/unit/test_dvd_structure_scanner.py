from __future__ import annotations

from pathlib import Path

from privatetv.config import settings_from_mapping
from privatetv.domain.models import SourceKind
from privatetv.media.dvd_structure_scanner import DvdStructureScanner
from privatetv.media.probe import ProbeResult


class FakeProbe:
    def probe(self, path: Path) -> ProbeResult:
        return ProbeResult(
            path=path,
            duration_seconds=10.0,
            container="mpeg",
            video_codec="mpeg2video",
            audio_codec="ac3",
            file_size_bytes=path.stat().st_size,
            mtime=int(path.stat().st_mtime),
        )


def _settings(tmp_path: Path):
    return settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {
                "directories": [str(tmp_path)],
                "recursive": True,
                "extensions": [".mp4", ".vob"],
                "dvd": {
                    "enabled": True,
                    "detect_video_ts": True,
                    "main_title_strategy": "largest_titleset",
                    "min_main_title_size_mb": 0,
                    "min_main_title_duration_seconds": 1,
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


def test_dvd_scanner_imports_largest_titleset_as_one_media_item(tmp_path: Path) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    (video_ts / "VIDEO_TS.IFO").write_bytes(b"ifo")
    (video_ts / "VTS_01_0.VOB").write_bytes(b"menu")
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (video_ts / "VTS_01_2.VOB").write_bytes(b"b" * 12)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"c" * 5)

    items = DvdStructureScanner(_settings(tmp_path), FakeProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert item.source_kind == SourceKind.DVD_STRUCTURE
    assert item.source_uri.startswith("dvd://")
    assert item.title == "Movie DVD"
    assert item.media_type == "dvd_main_title"
    assert item.duration_seconds == 20.0
    assert [asset.path.name for asset in assets] == ["VTS_01_1.VOB", "VTS_01_2.VOB"]
    assert all(asset.role == "dvd_main_title_part" for asset in assets)
