from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from privatetv.db import ScheduleRepository, connect_database, initialize_database
from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import MediaItem, ScheduleEntry, SourceKind


def test_schedule_repository_stores_and_reads_entries(tmp_path) -> None:
    db_path = tmp_path / "privatetv.sqlite3"
    initialize_database(db_path)
    zone = ZoneInfo("Europe/Berlin")
    start = datetime(2026, 7, 4, 20, 15, tzinfo=zone)

    with connect_database(db_path) as connection:
        media_id = MediaRepository(connection).upsert_media_item(
            MediaItem(
                id=None,
                source_kind=SourceKind.LOCAL_FILE,
                source_uri="file:///movie.mp4",
                source_root=None,
                title="Movie",
                media_type="file",
                duration_seconds=3600,
            )
        )
        repo = ScheduleRepository(connection)
        repo.append_entries(
            [
                ScheduleEntry(
                    id=None,
                    channel_id="privatetv",
                    media_item_id=media_id,
                    start_time=start,
                    end_time=start + timedelta(hours=1),
                    start_offset_seconds=0,
                    title="Movie",
                    description="Local media file",
                )
            ]
        )
        entries = repo.list_entries("privatetv")
        joined = repo.list_entries_with_media("privatetv")

    assert len(entries) == 1
    assert entries[0].title == "Movie"
    assert joined[0][1].source_uri == "file:///movie.mp4"
