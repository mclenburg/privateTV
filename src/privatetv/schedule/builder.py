from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from privatetv.config import AppSettings, ProgramBlockAnchorSettings
from privatetv.domain.models import MediaItem, ScheduleEntry, SourceKind
from privatetv.schedule.countdown import COUNTDOWN_DURATION_SECONDS
from privatetv.schedule.strategy import create_schedule_strategy

FILLER_MEDIA_TYPES = frozenset({"filler", "trailer", "bumper", "commercial", "advertisement", "dvd_preview"})


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

        candidates = [item for item in media_items if _is_schedulable_normal_item(item)]
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
        last_filler_block_end = start_at

        while current < target_end:
            ordered = strategy.order(candidates)
            if not ordered:
                break
            for preferred_item in ordered:
                if current >= target_end:
                    break

                item = self._choose_item_for_anchor_window(
                    preferred_item=preferred_item,
                    candidates=ordered,
                    start_at=current,
                    target_end=target_end,
                    countdown_item=countdown_item,
                )

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
                    last_filler_id = _last_real_filler_id(bridge_entries, countdown_item)
                    current = bridge_entries[-1].end_time
                    last_filler_block_end = current
                    if current >= target_end:
                        break

                duration = timedelta(seconds=float(item.duration_seconds))
                stop = current + duration
                entries.append(_entry_for_item(self._settings.channel.id, item, current, stop))
                current = stop

                between_entries = self._build_between_programme_fillers(
                    filler_candidates=filler_strategy.order(filler_candidates),
                    countdown_item=countdown_item,
                    start_at=current,
                    target_end=target_end,
                    last_filler_id=last_filler_id,
                    last_filler_block_end=last_filler_block_end,
                )
                if between_entries:
                    entries.extend(between_entries)
                    last_filler_id = _last_real_filler_id(between_entries, countdown_item)
                    current = between_entries[-1].end_time
                    last_filler_block_end = current
        return ScheduleBuildResult(entries, start_at, target_end)

    def _choose_item_for_anchor_window(
        self,
        *,
        preferred_item: MediaItem,
        candidates: list[MediaItem],
        start_at: datetime,
        target_end: datetime,
        countdown_item: MediaItem | None,
    ) -> MediaItem:
        if not _between_programmes_enabled(self._settings):
            return preferred_item
        anchor_time = _next_anchor_datetime(self._settings.program_blocks.anchors, start_at, target_end)
        if anchor_time is None:
            return preferred_item
        if start_at + timedelta(seconds=float(preferred_item.duration_seconds)) <= anchor_time:
            return preferred_item

        max_countdown = self._settings.program_blocks.generated_countdown.max_duration_seconds if countdown_item else 0
        gap_seconds = (anchor_time - start_at).total_seconds()
        reserve = min(max_countdown, max(0, gap_seconds))
        fitting = [item for item in candidates if item.duration_seconds <= max(0.0, gap_seconds - reserve)]
        if not fitting and countdown_item is not None:
            fitting = [item for item in candidates if item.duration_seconds <= gap_seconds]
        if not fitting:
            return preferred_item
        return max(fitting, key=lambda item: (item.duration_seconds, item.title.lower(), int(item.id or 0)))

    def _build_between_programme_fillers(
        self,
        *,
        filler_candidates: list[MediaItem],
        countdown_item: MediaItem | None,
        start_at: datetime,
        target_end: datetime,
        last_filler_id: int | None,
        last_filler_block_end: datetime,
    ) -> list[ScheduleEntry]:
        fillers = self._settings.program_blocks.fillers
        if not (_between_programmes_enabled(self._settings) and fillers.insert_between_movies and filler_candidates):
            return []
        anchor_time = _next_anchor_datetime(self._settings.program_blocks.anchors, start_at, target_end)
        if anchor_time is None:
            return []
        minutes_since_last_break = (start_at - last_filler_block_end).total_seconds() / 60
        if minutes_since_last_break < fillers.prefer_filler_after_minutes:
            return []
        remaining = (anchor_time - start_at).total_seconds()
        reserve = self._countdown_reserve_seconds(countdown_item, remaining)
        if remaining <= reserve + 60:
            return []
        budget = min(float(fillers.max_total_filler_block_seconds), remaining - reserve)
        return self._build_filler_block(
            filler_candidates=filler_candidates,
            start_at=start_at,
            budget_seconds=budget,
            last_filler_id=last_filler_id,
            max_consecutive=fillers.max_consecutive_fillers,
        )

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
        reserve = self._countdown_reserve_seconds(countdown_item, remaining)
        last_id = last_filler_id

        while remaining > reserve:
            block_budget = remaining - reserve
            if _between_programmes_enabled(self._settings):
                block_budget = min(block_budget, float(self._settings.program_blocks.fillers.max_total_filler_block_seconds))
            block = self._build_filler_block(
                filler_candidates=filler_candidates,
                start_at=cursor,
                budget_seconds=block_budget,
                last_filler_id=last_id,
                max_consecutive=self._settings.program_blocks.fillers.max_consecutive_fillers,
            )
            if not block:
                break
            entries.extend(block)
            cursor = block[-1].end_time
            last_id = _last_real_filler_id(block, countdown_item) or last_id
            remaining = (anchor_time - cursor).total_seconds()
            if _between_programmes_enabled(self._settings) and remaining > reserve:
                fitting_normal_exists = False
                # In between-programmes mode a short filler block should not grow into a wall if
                # normal content can still be placed by the outer scheduling loop.
                if remaining > reserve + 60:
                    fitting_normal_exists = True
                if fitting_normal_exists:
                    break

        remaining = (anchor_time - cursor).total_seconds()
        if countdown_item is not None and 0 < remaining <= max_countdown:
            entries.append(self._countdown_entry(countdown_item, start_at=cursor, anchor_time=anchor_time, anchor=anchor))

        if entries and entries[-1].end_time == anchor_time:
            return entries
        if _between_programmes_enabled(self._settings):
            return entries
        return entries

    def _build_filler_block(
        self,
        *,
        filler_candidates: list[MediaItem],
        start_at: datetime,
        budget_seconds: float,
        last_filler_id: int | None,
        max_consecutive: int,
    ) -> list[ScheduleEntry]:
        entries: list[ScheduleEntry] = []
        cursor = start_at
        remaining = budget_seconds
        last_id = last_filler_id
        while remaining > 0 and len(entries) < max_consecutive:
            filler = _select_filler(filler_candidates, budget_seconds=remaining, last_filler_id=last_id)
            if filler is None:
                break
            stop = cursor + timedelta(seconds=float(filler.duration_seconds))
            entries.append(_entry_for_item(self._settings.channel.id, filler, cursor, stop))
            cursor = stop
            remaining -= float(filler.duration_seconds)
            last_id = int(filler.id)
        return entries

    def _countdown_reserve_seconds(self, countdown_item: MediaItem | None, remaining_seconds: float) -> int:
        if countdown_item is None:
            return 0
        return min(self._settings.program_blocks.generated_countdown.max_duration_seconds, max(0, int(remaining_seconds)))

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


def _entry_for_item(channel_id: str, item: MediaItem, start: datetime, stop: datetime) -> ScheduleEntry:
    return ScheduleEntry(
        id=None,
        channel_id=channel_id,
        media_item_id=int(item.id),
        start_time=start,
        end_time=stop,
        start_offset_seconds=0.0,
        title=item.title,
        description=_description_for(item),
    )


def _between_programmes_enabled(settings: AppSettings) -> bool:
    return (
        settings.program_blocks.enabled
        and settings.program_blocks.fillers.enabled
        and settings.program_blocks.fillers.distribution == "between_programmes"
    )


def _last_real_filler_id(entries: list[ScheduleEntry], countdown_item: MediaItem | None) -> int | None:
    countdown_id = countdown_item.id if countdown_item is not None else None
    for entry in reversed(entries):
        if entry.media_item_id != countdown_id:
            return entry.media_item_id
    return None


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


def _next_anchor_datetime(
    anchors: tuple[ProgramBlockAnchorSettings, ...],
    now: datetime,
    target_end: datetime,
) -> datetime | None:
    anchor = _next_enabled_anchor(anchors, now)
    if anchor is None:
        return None
    value = _anchor_datetime(now, anchor.time)
    if value > target_end:
        return None
    return value


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
