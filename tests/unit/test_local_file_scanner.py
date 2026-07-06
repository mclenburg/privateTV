from __future__ import annotations

from pathlib import Path

from privatetv.config import settings_from_mapping
from privatetv.domain.models import ScanStatus, SourceKind
from privatetv.media.local_file_scanner import LocalFileScanner
from privatetv.media.probe import ProbeResult


class FakeProbe:
    def probe(self, path: Path) -> ProbeResult:
        return ProbeResult(
            path=path,
            duration_seconds=60.0,
            container="mov",
            video_codec="h264",
            audio_codec="aac",
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
                "extensions": [".mp4", ".mkv", ".vob"],
                "dvd": {"enabled": True},
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


def test_scanner_finds_supported_files_recursively_and_skips_video_ts(tmp_path: Path) -> None:
    (tmp_path / "movie.mp4").write_bytes(b"movie")
    nested = tmp_path / "Nested"
    nested.mkdir()
    (nested / "second.mkv").write_bytes(b"movie")
    (nested / "ignored.txt").write_text("ignore", encoding="utf-8")
    video_ts = tmp_path / "DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    (video_ts / "VTS_01_1.VOB").write_bytes(b"dvd part")

    scanner = LocalFileScanner(_settings(tmp_path), FakeProbe())

    items = scanner.scan()

    assert sorted(item.title for item, _assets in items) == ["movie", "second"]
    assert {item.source_kind for item, _assets in items} == {SourceKind.LOCAL_FILE}
    assert all(item.scan_status == ScanStatus.OK for item, _assets in items)
    assert all(assets[0].role == "primary" for _item, assets in items)


def test_scanner_stores_absolute_asset_paths_for_relative_media_root(
    tmp_path: Path, monkeypatch
) -> None:
    media_root = tmp_path / "relative-root"
    media_root.mkdir()
    (media_root / "movie.mp4").write_bytes(b"movie")
    monkeypatch.chdir(tmp_path)

    settings = settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {
                "directories": ["relative-root"],
                "recursive": True,
                "extensions": [".mp4"],
                "dvd": {"enabled": True},
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

    items = LocalFileScanner(settings, FakeProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert Path(item.source_root).is_absolute()
    assert assets[0].path.is_absolute()
    assert assets[0].path == (media_root / "movie.mp4").resolve()


def test_scanner_can_mark_configured_directory_as_filler(tmp_path: Path) -> None:
    filler_root = tmp_path / "filler"
    filler_root.mkdir()
    (filler_root / "coming_up.mp4").write_bytes(b"movie")
    settings = _settings(tmp_path)

    items = LocalFileScanner(
        settings,
        FakeProbe(),
        directories=(filler_root,),
        media_type="filler",
        progress_kind="filler",
    ).scan()

    assert len(items) == 1
    item, _assets = items[0]
    assert item.media_type == "filler"
    assert item.title == "coming up"


def test_scanner_keeps_loose_vob_file_without_dvd_ifo_when_dvd_scanner_is_enabled(tmp_path: Path) -> None:
    loose_vob = tmp_path / "VTS_01_1.VOB"
    loose_vob.write_bytes(b"standalone vob")

    items = LocalFileScanner(_settings(tmp_path), FakeProbe()).scan()

    assert len(items) == 1
