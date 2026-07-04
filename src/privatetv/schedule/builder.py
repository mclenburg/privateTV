from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from privatetv.config import AppSettings
from privatetv.domain.models import MediaItem, ScheduleEntry
from privatetv.schedule.strategy import create_schedule_strategy


@dataclass(frozen=True, slots=True)
class ScheduleBuildResult:
    entries: list[ScheduleEntry]
    start_at: datetime
    end_at: datetime


class ScheduleBuilder:
    """Builds a continuous linear schedule from enabled media items."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build(
        self,
        media_items: list[MediaItem],
        *,
        start_at: datetime,
        end_at: datetime | None = None,
    ) -> ScheduleBuildResult:
        if start_at.tzinfo is None:
            raise ValueError("start_at must be timezone-aware")
        target_end = end_at or start_at + timedelta(days=self._settings.schedule.days_ahead)
        if target_end.tzinfo is None:
            raise ValueError("end_at must be timezone-aware")
        if target_end <= start_at:
            return ScheduleBuildResult([], start_at, target_end)

        candidates = [
            item
            for item in media_items
            if item.id is not None and item.enabled and item.duration_seconds > 0
        ]
        if not candidates:
            return ScheduleBuildResult([], start_at, target_end)

        strategy = create_schedule_strategy(
            self._settings.schedule.strategy,
            random_seed=self._settings.schedule.random_seed,
        )
        current = start_at
        entries: list[ScheduleEntry] = []
        while current < target_end:
            ordered = strategy.order(candidates)
            if not ordered:
                break
            for item in ordered:
                if current >= target_end:
                    break
                duration = timedelta(seconds=float(item.duration_seconds))
                stop = current + duration
                entries.append(
                    ScheduleEntry(
                        id=None,
                        channel_id=self._settings.channel.id,
                        media_item_id=int(item.id),
                        start_time=current,
                        end_time=stop,
                        start_offset_seconds=0.0,
                        title=item.title,
                        description=_description_for(item),
                    )
                )
                current = stop
        return ScheduleBuildResult(entries, start_at, target_end)


def _description_for(item: MediaItem) -> str:
    if item.source_kind.value == "dvd_structure":
        return "Local DVD structure"
    return "Local media file"
