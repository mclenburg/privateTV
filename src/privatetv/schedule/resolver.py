from __future__ import annotations

from datetime import datetime

from privatetv.domain.models import CurrentProgramme, MediaItem, ScheduleEntry


def resolve_current_programme(
    entries_with_media: list[tuple[ScheduleEntry, MediaItem]], *, now: datetime
) -> CurrentProgramme | None:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    for entry, media in entries_with_media:
        if entry.start_time <= now < entry.end_time:
            offset = (now - entry.start_time).total_seconds() + entry.start_offset_seconds
            return CurrentProgramme(media=media, schedule_entry=entry, offset_seconds=max(0.0, offset))
    return None
