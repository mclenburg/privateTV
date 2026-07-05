from __future__ import annotations

import sqlite3
from pathlib import Path

from privatetv.db import MediaRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, MediaItem, SourceKind
from privatetv.media.catalog import store_scan_results
from privatetv.media.local_file_scanner import LocalFileScanner
from tests.unit.test_local_file_scanner import FakeProbe, _settings


def test_local_scanner_skips_paths_with_surrogate_characters(tmp_path: Path) -> None:
    good = tmp_path / "good.mp4"
    good.write_bytes(b"movie")
    bad_name = "broken_\udce4.mp4"
    bad = tmp_path / bad_name
    # Create the invalid filename using bytes so pathlib can discover it with surrogateescape.
    (str(tmp_path).encode() + b"/broken_\xe4.mp4")
    bad_bytes = bytes(tmp_path) + b"/broken_\xe4.mp4"
    import os

    with open(bad_bytes, "wb") as handle:
        handle.write(b"movie")

    progress: list[tuple[str, str]] = []
    scanner = LocalFileScanner(_settings(tmp_path), FakeProbe())

    items = scanner.scan()
    items_with_progress = list(scanner.iter_scan_results(lambda kind, path: progress.append((kind, str(path)))))

    assert [item.title for item, _assets in items] == ["good"]
    assert [item.title for item, _assets in items_with_progress] == ["good"]
    assert any(kind == "skip-invalid-path" for kind, _path in progress)


def test_store_scan_results_continues_to_work_for_valid_paths(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite3"
    initialize_database(database)
    path = tmp_path / "movie.mp4"
    path.write_bytes(b"movie")
    item = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=path.resolve().as_uri(),
        source_root=tmp_path,
        title="movie",
        media_type="video_file",
        duration_seconds=60.0,
        file_size_bytes=path.stat().st_size,
        mtime=int(path.stat().st_mtime),
    )
    asset = MediaAsset(
        id=None,
        media_item_id=0,
        asset_order=1,
        path=path,
        role="primary",
        file_size_bytes=path.stat().st_size,
    )

    with connect_database(database) as connection:
        summary = store_scan_results(connection, [(item, (asset,))], {SourceKind.LOCAL_FILE})
        stored = MediaRepository(connection).list_media_items()

    assert summary.imported_items == 1
    assert [stored_item.title for stored_item in stored] == ["movie"]
