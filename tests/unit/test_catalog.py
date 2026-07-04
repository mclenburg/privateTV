from __future__ import annotations

from pathlib import Path

from privatetv.db import MediaRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, MediaItem, SourceKind
from privatetv.media.catalog import store_scan_results


def _item(tmp_path: Path, source_kind: SourceKind, source_uri: str, title: str) -> tuple[MediaItem, tuple[MediaAsset, ...]]:
    path = tmp_path / f"{title}.mp4"
    path.write_bytes(b"movie")
    return (
        MediaItem(
            id=None,
            source_kind=source_kind,
            source_uri=source_uri,
            source_root=tmp_path,
            title=title,
            media_type="video_file",
            duration_seconds=60.0,
            file_size_bytes=path.stat().st_size,
            mtime=int(path.stat().st_mtime),
        ),
        (
            MediaAsset(
                id=None,
                media_item_id=0,
                asset_order=1,
                path=path,
                role="primary",
                file_size_bytes=path.stat().st_size,
            ),
        ),
    )


def test_store_scan_results_marks_missing_per_source_kind(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite3"
    initialize_database(database)

    first = _item(tmp_path, SourceKind.DVD_STRUCTURE, "dvd:///old", "old")
    second = _item(tmp_path, SourceKind.DVD_STRUCTURE, "dvd:///new", "new")

    with connect_database(database) as connection:
        store_scan_results(connection, [first], {SourceKind.DVD_STRUCTURE})
        store_scan_results(connection, [second], {SourceKind.DVD_STRUCTURE})
        items = MediaRepository(connection).list_media_items()

    by_uri = {item.source_uri: item for item in items}
    assert by_uri["dvd:///old"].enabled is False
    assert by_uri["dvd:///new"].enabled is True
