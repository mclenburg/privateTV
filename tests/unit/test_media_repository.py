from __future__ import annotations

from pathlib import Path

from privatetv.db import MediaRepository, connect_database, initialize_database
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind


def test_repository_upserts_media_item_and_marks_missing(tmp_path: Path) -> None:
    database = tmp_path / "db.sqlite3"
    initialize_database(database)
    media_path = tmp_path / "movie.mp4"
    media_path.write_bytes(b"movie")

    item = MediaItem(
        id=None,
        source_kind=SourceKind.LOCAL_FILE,
        source_uri=media_path.as_uri(),
        source_root=tmp_path,
        title="movie",
        media_type="video_file",
        duration_seconds=60.0,
        file_size_bytes=media_path.stat().st_size,
        mtime=int(media_path.stat().st_mtime),
    )
    asset = MediaAsset(
        id=None,
        media_item_id=0,
        asset_order=1,
        path=media_path,
        role="primary",
        file_size_bytes=media_path.stat().st_size,
    )

    with connect_database(database) as connection:
        repository = MediaRepository(connection)
        media_id = repository.upsert_media_item(item, (asset,))
        assert media_id > 0
        assert repository.mark_missing_except(SourceKind.LOCAL_FILE, set()) == 1
        stored = repository.list_media_items()[0]

    assert stored.scan_status == ScanStatus.MISSING
    assert stored.enabled is False
