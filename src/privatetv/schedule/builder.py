from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from privatetv.config import AppSettings, ProgramBlockAnchorSettings
from privatetv.domain.models import MediaItem, ScheduleEntry, SourceKind
from privatetv.schedule.countdown import COUNTDOWN_DURATION_SECONDS
from privatetv.schedule.strategy import create_schedule_strategy

FILLER_MEDIA_TYPES = frozenset({"filler", "trailer", "bumper"})


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
            if _is_schedulable_normal_item(item)
        ]
        if not candidates:
            return ScheduleBuildResult([], start_at, target_end)

        filler_candidates = [
            item
            for item in media_items
            if _is_schedulable_filler_item(item, self._settings.program_blocks.fillers.max_duration_seconds)
        ]
        countdown_item = _countdown_item(media_items)
        strategy = create_schedule_strategy(
            self._settings.schedule.strategy,
            random_seed=self._settings.schedule.random_seed,
        )
        filler_strategy = create_schedule_strategy(
            self._settings.schedule.strategy,
            random_seed=self._settings.schedule.random_seed,
        )
        current = start_at
        entries: list[ScheduleEntry] = []
        last_filler_id: int | None = None

        while current < target_end:
            ordered = strategy.order(candidates)
            if not ordered:
                break
            for item in ordered:
                if current >= target_end:
                    break

                bridge_entries = self._build_anchor_bridge_entries(
                    filler_candidates=filler_strategy.order(filler_candidates),
                    countdown_item=countdown_item,
                    next_item=item,
                    start_at=current,
                    target_end=target_end,
                    last_filler_id=last_filler_id,
                )
                if bridge_entries:
                    entries.extend(bridge_entries)
                    for entry in bridge_entries:
                        if entry.media_item_id != (countdown_item.id if countdown_item else None):
                            last_filler_id = entry.media_item_id
                    current = bridge_entries[-1].end_time
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

    def _build_anchor_bridge_entries(
        self,
        *,
        filler_candidates: list[MediaItem],
        countdown_item: MediaItem | None,
        next_item: MediaItem,
        start_at: datetime,
        target_end: datetime,
        last_filler_id: int | None,
    ) -> list[ScheduleEntry]:
        if not self._settings.program_blocks.enabled:
            return []
        anchor = _next_enabled_anchor(self._settings.program_blocks.anchors, start_at)
        if anchor is None:
            return []
        anchor_time = _anchor_datetime(start_at, anchor.time)
        if anchor_time <= start_at or anchor_time > target_end:
            return []

        gap_seconds = (anchor_time - start_at).total_seconds()
        if gap_seconds <= 0:
            return []

        max_countdown = self._settings.program_blocks.generated_countdown.max_duration_seconds
        if countdown_item is not None and gap_seconds <= max_countdown:
            return [self._countdown_entry(countdown_item, start_at=start_at, anchor_time=anchor_time, anchor=anchor)]

        next_stop = start_at + timedelta(seconds=float(next_item.duration_seconds))
        if next_stop <= anchor_time:
            return []

        if not (self._settings.program_blocks.fillers.enabled and filler_candidates):
            return []

        entries: list[ScheduleEntry] = []
        cursor = start_at
        remaining = (anchor_time - cursor).total_seconds()
        reserve = max_countdown if countdown_item is not None else 0
        last_id = last_filler_id

        while remaining > reserve:
            budget = remaining - reserve
            filler = _select_filler(filler_candidates, budget_seconds=budget, last_filler_id=last_id)
            if filler is None:
                break
            stop = cursor + timedelta(seconds=float(filler.duration_seconds))
            entries.append(
                ScheduleEntry(
                    id=None,
                    channel_id=self._settings.channel.id,
                    media_item_id=int(filler.id),
                    start_time=cursor,
                    end_time=stop,
                    start_offset_seconds=0.0,
                    title=filler.title,
                    description=_description_for(filler),
                )
            )
            cursor = stop
            last_id = int(filler.id)
            remaining = (anchor_time - cursor).total_seconds()

        if countdown_item is not None and 0 < remaining <= max_countdown:
            entries.append(self._countdown_entry(countdown_item, start_at=cursor, anchor_time=anchor_time, anchor=anchor))

        return entries

    def _countdown_entry(
        self,
        countdown_item: MediaItem,
        *,
        start_at: datetime,
        anchor_time: datetime,
        anchor: ProgramBlockAnchorSettings,
    ) -> ScheduleEntry:
        gap_seconds = (anchor_time - start_at).total_seconds()
        start_offset = max(0.0, COUNTDOWN_DURATION_SECONDS - gap_seconds)
        return ScheduleEntry(
            id=None,
            channel_id=self._settings.channel.id,
            media_item_id=int(countdown_item.id),
            start_time=start_at,
            end_time=anchor_time,
            start_offset_seconds=start_offset,
            title=self._settings.program_blocks.generated_countdown.title,
            description=f"PrivateTV Countdown bis {anchor.time}",
        )


def _is_schedulable_normal_item(item: MediaItem) -> bool:
    return (
        item.id is not None
        and item.enabled
        and item.duration_seconds > 0
        and item.source_kind != SourceKind.GENERATED
        and item.media_type not in FILLER_MEDIA_TYPES
    )


def _is_schedulable_filler_item(item: MediaItem, max_duration_seconds: int) -> bool:
    return (
        item.id is not None
        and item.enabled
        and item.duration_seconds > 0
        and item.media_type in FILLER_MEDIA_TYPES
        and item.duration_seconds <= max_duration_seconds
    )


def _select_filler(
    filler_candidates: list[MediaItem],
    *,
    budget_seconds: float,
    last_filler_id: int | None,
) -> MediaItem | None:
    fitting = [item for item in filler_candidates if item.duration_seconds <= budget_seconds]
    if not fitting:
        return None
    non_repeated = [item for item in fitting if item.id != last_filler_id]
    pool = non_repeated or fitting
    return max(pool, key=lambda item: (item.duration_seconds, item.title.lower(), int(item.id or 0)))


def _countdown_item(media_items: list[MediaItem]) -> MediaItem | None:
    for item in media_items:
        if (
            item.id is not None
            and item.enabled
            and item.source_kind == SourceKind.GENERATED
            and item.media_type == "generated_countdown"
            and item.duration_seconds >= COUNTDOWN_DURATION_SECONDS
        ):
            return item
    return None


def _next_enabled_anchor(
    anchors: tuple[ProgramBlockAnchorSettings, ...],
    now: datetime,
) -> ProgramBlockAnchorSettings | None:
    enabled = [anchor for anchor in anchors if anchor.enabled]
    if not enabled:
        return None
    return min(enabled, key=lambda anchor: _anchor_datetime(now, anchor.time))


def _anchor_datetime(now: datetime, value: str) -> datetime:
    hour, minute = (int(part) for part in value.split(":"))
    candidate = datetime.combine(now.date(), time(hour=hour, minute=minute), tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _description_for(item: MediaItem) -> str:
    if item.media_type in FILLER_MEDIA_TYPES:
        return "PrivateTV filler clip"
    if item.source_kind == SourceKind.DVD_STRUCTURE:
        return "Local DVD structure"
    if item.source_kind == SourceKind.GENERATED:
        return "Generated PrivateTV clip"
    return "Local media file"
