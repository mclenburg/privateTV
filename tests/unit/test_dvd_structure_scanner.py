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


def test_dvd_scanner_stores_absolute_asset_paths_for_relative_media_root(
    tmp_path: Path, monkeypatch
) -> None:
    video_ts = tmp_path / "relative-root" / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    (video_ts / "VIDEO_TS.IFO").write_bytes(b"ifo")
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (video_ts / "VTS_01_2.VOB").write_bytes(b"b" * 12)
    monkeypatch.chdir(tmp_path)

    settings = settings_from_mapping(
        {
            "server": {"host": "127.0.0.1", "port": 9988, "public_base_url": "http://x"},
            "channel": {"id": "privatetv", "name": "PrivateTV"},
            "media": {
                "directories": ["relative-root"],
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

    items = DvdStructureScanner(settings, FakeProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert Path(item.source_root).is_absolute()
    assert all(asset.path.is_absolute() for asset in assets)
    assert [asset.path for asset in assets] == [
        (video_ts / "VTS_01_1.VOB").resolve(),
        (video_ts / "VTS_01_2.VOB").resolve(),
    ]


def test_dvd_scanner_imports_loose_dvd_directory_as_one_media_item(tmp_path: Path) -> None:
    dvd_dir = tmp_path / "Felix 2"
    dvd_dir.mkdir()
    (dvd_dir / "VIDEO_TS.IFO").write_bytes(b"ifo")
    (dvd_dir / "VTS_01_0.VOB").write_bytes(b"menu")
    (dvd_dir / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (dvd_dir / "VTS_01_2.VOB").write_bytes(b"b" * 12)

    items = DvdStructureScanner(_settings(tmp_path), FakeProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert item.title == "Felix 2"
    assert item.media_type == "dvd_main_title"
    assert item.duration_seconds == 20.0
    assert [asset.path.name for asset in assets] == ["VTS_01_1.VOB", "VTS_01_2.VOB"]


class DurationByNameProbe:
    def probe(self, path: Path) -> ProbeResult:
        durations = {
            "VTS_01_1.VOB": 10.0,
            "VTS_01_2.VOB": 10.0,
            "VTS_02_1.VOB": 60.0,
        }
        return ProbeResult(
            path=path,
            duration_seconds=durations[path.name],
            container="mpeg",
            video_codec="mpeg2video",
            audio_codec="ac3",
            file_size_bytes=path.stat().st_size,
            mtime=int(path.stat().st_mtime),
        )


def test_dvd_scanner_prefers_longer_duration_over_larger_bonus_titleset(tmp_path: Path) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    (video_ts / "VIDEO_TS.IFO").write_bytes(b"ifo")
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 100)
    (video_ts / "VTS_01_2.VOB").write_bytes(b"b" * 100)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"c" * 10)

    items = DvdStructureScanner(_settings(tmp_path), DurationByNameProbe()).scan()

    assert items[0][0].media_type == "dvd_main_title"
    _item, assets = items[0]
    assert [asset.path.name for asset in assets] == ["VTS_02_1.VOB"]
    assert any(item.media_type == "dvd_extra_filler" for item, _assets in items[1:])


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _write_vmg_ifo(path: Path, visible_vts_numbers: list[int]) -> None:
    data = bytearray(4096)
    data[0xC4:0xC8] = (1).to_bytes(4, "big")
    table = 2048
    data[table : table + 2] = len(visible_vts_numbers).to_bytes(2, "big")
    data[table + 4 : table + 8] = (8 + len(visible_vts_numbers) * 12).to_bytes(4, "big")
    for index, vts_no in enumerate(visible_vts_numbers):
        offset = table + 8 + index * 12
        data[offset + 6] = vts_no
        data[offset + 7] = 1
    path.write_bytes(bytes(data))


def _write_vts_ifo(path: Path, durations: list[tuple[int, int, int]]) -> None:
    data = bytearray(8192)
    data[0xCC:0xD0] = (1).to_bytes(4, "big")
    table = 2048
    data[table : table + 2] = len(durations).to_bytes(2, "big")
    for index, (hours, minutes, seconds) in enumerate(durations):
        entry_offset = table + 8 + index * 8
        pgc_start = 0x80 + index * 0x40
        data[entry_offset + 4 : entry_offset + 8] = pgc_start.to_bytes(4, "big")
        pgc_offset = table + pgc_start
        data[pgc_offset] = 1
        data[pgc_offset + 1] = 1
        data[pgc_offset + 2] = _bcd(hours)
        data[pgc_offset + 3] = _bcd(minutes)
        data[pgc_offset + 4] = _bcd(seconds)
        data[pgc_offset + 5] = 0x00
    path.write_bytes(bytes(data))


class ShortProbe:
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


def test_dvd_scanner_uses_ifo_pgc_duration_for_main_title(tmp_path: Path) -> None:
    video_ts = tmp_path / "Felix 2" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1])
    _write_vts_ifo(video_ts / "VTS_01_0.IFO", [(1, 24, 5)])
    (video_ts / "VTS_01_0.VOB").write_bytes(b"menu")
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (video_ts / "VTS_01_2.VOB").write_bytes(b"b" * 10)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert item.title == "Felix 2"
    assert item.duration_seconds == 5045.0
    assert [asset.path.name for asset in assets] == ["VTS_01_1.VOB", "VTS_01_2.VOB"]


def test_dvd_scanner_prefers_ifo_main_title_over_larger_probe_candidate(tmp_path: Path) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1])
    _write_vts_ifo(video_ts / "VTS_01_0.IFO", [(1, 30, 0)])
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"b" * 1000)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    assert len(items) == 1
    item, assets = items[0]
    assert item.duration_seconds == 5400.0
    assert [asset.path.name for asset in assets] == ["VTS_01_1.VOB"]


def test_dvd_scanner_imports_short_non_main_vts_as_dvd_extra_filler(tmp_path: Path) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1, 2])
    _write_vts_ifo(video_ts / "VTS_01_0.IFO", [(1, 33, 1)])
    _write_vts_ifo(video_ts / "VTS_02_0.IFO", [(0, 0, 30)])
    (video_ts / "VTS_01_0.VOB").write_bytes(b"menu")
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 100)
    (video_ts / "VTS_02_0.VOB").write_bytes(b"menu")
    (video_ts / "VTS_02_1.VOB").write_bytes(b"b" * 10)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    assert [item.media_type for item, _assets in items] == ["dvd_main_title", "dvd_extra_filler"]
    extra, extra_assets = items[1]
    assert extra.title == "Movie DVD – DVD Extra 02"
    assert extra.duration_seconds == 30.0
    assert extra.source_uri.endswith("#extra-vts-02")
    assert [asset.role for asset in extra_assets] == ["dvd_extra_part"]
    assert [asset.path.name for asset in extra_assets] == ["VTS_02_1.VOB"]


def test_dvd_scanner_does_not_import_long_bonus_vts_as_filler(tmp_path: Path) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1, 2])
    _write_vts_ifo(video_ts / "VTS_01_0.IFO", [(1, 33, 1)])
    _write_vts_ifo(video_ts / "VTS_02_0.IFO", [(0, 12, 0)])
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 100)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"b" * 10)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    assert len(items) == 1
    assert items[0][0].media_type == "dvd_main_title"


def _write_vts_ifo_with_cells(path: Path, durations: list[tuple[int, int, int, int, int]]) -> None:
    """Write tiny VTS fixture with PGC times and first/last cell sectors."""
    data = bytearray(12288)
    data[0xCC:0xD0] = (1).to_bytes(4, "big")
    table = 2048
    data[table : table + 2] = len(durations).to_bytes(2, "big")
    for index, (hours, minutes, seconds, first_sector, last_sector) in enumerate(durations):
        entry_offset = table + 8 + index * 8
        pgc_start = 0x100 + index * 0x80
        data[entry_offset + 4 : entry_offset + 8] = pgc_start.to_bytes(4, "big")
        pgc_offset = table + pgc_start
        data[pgc_offset] = 1  # programs
        data[pgc_offset + 1] = 1  # cells
        data[pgc_offset + 2] = _bcd(hours)
        data[pgc_offset + 3] = _bcd(minutes)
        data[pgc_offset + 4] = _bcd(seconds)
        data[pgc_offset + 5] = 0x00
        cell_table = 0x40
        data[pgc_offset + 0x12 : pgc_offset + 0x14] = cell_table.to_bytes(2, "big")
        cell_offset = pgc_offset + cell_table
        data[cell_offset + 8 : cell_offset + 12] = first_sector.to_bytes(4, "big")
        data[cell_offset + 20 : cell_offset + 24] = last_sector.to_bytes(4, "big")
    path.write_bytes(bytes(data))


def test_dvd_ifo_parser_reads_pgc_sector_ranges(tmp_path: Path) -> None:
    from privatetv.media.dvd_ifo import parse_dvd_ifo_pgc_candidates

    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1])
    _write_vts_ifo_with_cells(video_ts / "VTS_01_0.IFO", [(1, 33, 1, 0, 4000), (0, 1, 15, 500, 700)])

    candidates = parse_dvd_ifo_pgc_candidates(video_ts)

    assert [(c.title_set, c.pgc_number, c.duration_seconds, c.first_sector, c.last_sector) for c in candidates] == [
        ("01", 1, 5581.0, 0, 4000),
        ("01", 2, 75.0, 500, 700),
    ]


def test_dvd_scanner_imports_short_same_vts_pgc_extra_as_generated_filler(tmp_path: Path, monkeypatch) -> None:
    video_ts = tmp_path / "Movie DVD" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1])
    _write_vts_ifo_with_cells(video_ts / "VTS_01_0.IFO", [(1, 33, 1, 0, 4000), (0, 1, 15, 1, 1)])
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 4096)

    def fake_extract(self, files, candidate, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"clip")
        return True

    monkeypatch.setattr(DvdStructureScanner, "_extract_pgc_extra_clip", fake_extract)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    media_types = [item.media_type for item, _assets in items]
    assert media_types == ["dvd_main_title", "dvd_pgc_extra_filler"]
    extra, assets = items[1]
    assert extra.title == "Movie DVD – DVD Extra 01/2"
    assert extra.source_uri.startswith("generated://dvd-extra/")
    assert extra.duration_seconds == 75.0
    assert assets[0].role == "dvd_pgc_extra_clip"
    assert assets[0].path.name.endswith("_vts01_pgc002.mp4")


def test_dvd_ifo_parser_ignores_implausible_21_hour_pgc_time(tmp_path: Path) -> None:
    from privatetv.media.dvd_ifo import parse_dvd_ifo_main_title_candidates

    video_ts = tmp_path / "Corinna" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [2])
    _write_vts_ifo(video_ts / "VTS_02_0.IFO", [(21, 21, 1)])

    assert parse_dvd_ifo_main_title_candidates(video_ts) == ()


def test_dvd_scanner_falls_back_to_concat_probe_when_ifo_duration_is_implausible(
    tmp_path: Path, monkeypatch
) -> None:
    video_ts = tmp_path / "corinna corinna" / "VIDEO_TS"
    video_ts.mkdir(parents=True)
    _write_vmg_ifo(video_ts / "VIDEO_TS.IFO", [1, 2])
    _write_vts_ifo(video_ts / "VTS_01_0.IFO", [(0, 20, 0)])
    _write_vts_ifo(video_ts / "VTS_02_0.IFO", [(21, 21, 1)])
    (video_ts / "VTS_01_1.VOB").write_bytes(b"a" * 10)
    (video_ts / "VTS_02_1.VOB").write_bytes(b"b" * 10)
    (video_ts / "VTS_02_2.VOB").write_bytes(b"c" * 10)
    (video_ts / "VTS_02_3.VOB").write_bytes(b"d" * 10)
    (video_ts / "VTS_02_4.VOB").write_bytes(b"e" * 10)

    def fake_concat_duration(self, files):
        names = [path.name for path in files]
        if names and names[0].startswith("VTS_02_"):
            return 3393.64
        return 1200.0

    monkeypatch.setattr(DvdStructureScanner, "_probe_title_set_concat_duration", fake_concat_duration)

    items = DvdStructureScanner(_settings(tmp_path), ShortProbe()).scan()

    main, assets = items[0]
    assert main.media_type == "dvd_main_title"
    assert main.title == "corinna corinna"
    assert main.duration_seconds == 3393.64
    assert [asset.path.name for asset in assets] == [
        "VTS_02_1.VOB",
        "VTS_02_2.VOB",
        "VTS_02_3.VOB",
        "VTS_02_4.VOB",
    ]
