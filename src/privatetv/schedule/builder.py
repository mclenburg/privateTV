from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from privatetv.config import AppSettings, ProgramBlockAnchorSettings, ProgramBlockSettings
from privatetv.domain.models import MediaItem, ScheduleEntry, SourceKind, SeriesRotationSnapshot, SeriesRotationUpdate
from privatetv.schedule.countdown import COUNTDOWN_DURATION_SECONDS
from privatetv.schedule.promos import PromoRequest
from privatetv.schedule.strategy import create_schedule_strategy

FILLER_MEDIA_TYPES = frozenset({"filler", "generated_countdown", "generated_promo", "dvd_extra_filler", "dvd_pgc_extra_filler", "trailer", "bumper", "commercial", "advertisement", "dvd_preview"})
MIN_NORMAL_PROGRAMME_DURATION_SECONDS = 60.0

PromoFactory = Callable[[PromoRequest], MediaItem | None]


@dataclass(frozen=True, slots=True)
class ScheduleBuildResult:
    entries: list[ScheduleEntry]
    start_at: datetime
    end_at: datetime
    series_rotation_updates: tuple[SeriesRotationUpdate, ...] = ()


class ScheduleBuilder:
    """Builds a continuous linear schedule from enabled media items."""

    def __init__(
        self,
        settings: AppSettings,
        *,
        promo_factory: PromoFactory | None = None,
        series_rotation_state: dict[str, SeriesRotationSnapshot] | None = None,
    ) -> None:
        self._settings = settings
        self._promo_factory = promo_factory
        self._series_rotation_state = dict(series_rotation_state or {})
        self._series_rotation_updates: dict[str, SeriesRotationUpdate] = {}

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
            if _is_schedulable_filler_item(item, self._settings.program_blocks.fillers.max_duration_seconds, self._settings.program_blocks.fillers.allowed_tags, self._settings.program_blocks.fillers.denied_tags)
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
        recent_filler_ids: deque[int] = deque(maxlen=_recent_filler_window_size(filler_candidates))
        filler_usage_counts: dict[int, int] = {}
        last_filler_block_end = start_at

        while current < target_end:
            ordered = strategy.order(candidates)
            if not ordered:
                break
            for preferred_item in ordered:
                if current >= target_end:
                    break

                skip_until = self._skip_empty_program_block_until(
                    candidates=ordered,
                    start_at=current,
                    target_end=target_end,
                )
                if skip_until is not None:
                    current = skip_until
                    if current >= target_end:
                        break
                    continue

                active_anchor = _anchor_at(self._settings.program_blocks.anchors, current)
                active_block = _active_block_at(self._settings.program_blocks.blocks, current)
                if active_anchor is not None:
                    preferred_item = _first_matching_anchor_item(ordered, active_anchor) or preferred_item
                elif active_block is not None:
                    series_item = self._choose_series_rotation_item(ordered, active_block, current)
                    preferred_item = series_item or _first_matching_block_item(ordered, active_block) or preferred_item

                item = self._choose_item_for_program_block_window(
                    preferred_item=preferred_item,
                    candidates=ordered,
                    start_at=current,
                    target_end=target_end,
                )
                item = self._choose_item_for_anchor_window(
                    preferred_item=item,
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
                    recent_filler_ids=recent_filler_ids,
                    filler_usage_counts=filler_usage_counts,
                )
                if bridge_entries:
                    entries.extend(bridge_entries)
                    last_filler_id = _last_real_filler_id(bridge_entries, countdown_item)
                    current = bridge_entries[-1].end_time
                    last_filler_block_end = current
                    if current >= target_end:
                        break
                    active_anchor = _anchor_at(self._settings.program_blocks.anchors, current)
                    active_block = _active_block_at(self._settings.program_blocks.blocks, current)
                    if active_anchor is not None:
                        item = _first_matching_anchor_item(ordered, active_anchor) or item
                    elif active_block is not None:
                        series_item = self._choose_series_rotation_item(ordered, active_block, current)
                        item = series_item or _first_matching_block_item(ordered, active_block) or item

                self._remember_series_rotation_if_needed(item, active_block, current)
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
                    recent_filler_ids=recent_filler_ids,
                    filler_usage_counts=filler_usage_counts,
                    last_filler_block_end=last_filler_block_end,
                )
                if between_entries:
                    entries.extend(between_entries)
                    last_filler_id = _last_real_filler_id(between_entries, countdown_item)
                    current = between_entries[-1].end_time
                    last_filler_block_end = current
        return ScheduleBuildResult(
            entries,
            start_at,
            target_end,
            tuple(self._series_rotation_updates.values()),
        )

    def _choose_series_rotation_item(
        self,
        candidates: list[MediaItem],
        block: ProgramBlockSettings,
        moment: datetime,
    ) -> MediaItem | None:
        if not (block.mode == "series_rotation" or block.series.enabled):
            return None
        episodes = [
            item
            for item in candidates
            if _is_series_episode(item)
            and _matches_block_tags(item, block)
            and item.duration_seconds <= block.series.max_episode_duration_seconds
        ]
        if not episodes:
            return None
        by_series: dict[str, list[MediaItem]] = {}
        for item in episodes:
            by_series.setdefault(str(item.series_title), []).append(item)
        for series_items in by_series.values():
            series_items.sort(key=_episode_order_key)

        rotation_name = _rotation_name(block)
        snapshot = self._series_rotation_state.get(rotation_name)
        if snapshot and snapshot.series_title in by_series:
            series_items = by_series[str(snapshot.series_title)]
            next_item = _next_episode_after(series_items, snapshot.episode_sort_key)
            if next_item is not None:
                return next_item
            if block.series.on_series_end == "restart":
                return series_items[0]
            if block.series.on_series_end == "stop_block":
                return None

        series_names = sorted(by_series)
        if snapshot and snapshot.series_title and block.series.on_series_end == "next_series":
            later = [name for name in series_names if name > snapshot.series_title]
            chosen_name = (later or series_names)[0]
            return by_series[chosen_name][0]
        return by_series[series_names[0]][0]

    def _remember_series_rotation_if_needed(
        self,
        item: MediaItem,
        block: ProgramBlockSettings | None,
        moment: datetime,
    ) -> None:
        if block is None or not (block.mode == "series_rotation" or block.series.enabled):
            return
        if not block.series.remember_position or not _is_series_episode(item):
            return
        rotation_name = _rotation_name(block)
        update = SeriesRotationUpdate(
            rotation_name=rotation_name,
            series_title=str(item.series_title),
            media_item_id=int(item.id),
            season_number=int(item.season_number),
            episode_number=int(item.episode_number),
            episode_sort_key=str(item.episode_sort_key or _episode_sort_key(item)),
            updated_at=moment,
        )
        self._series_rotation_updates[rotation_name] = update
        self._series_rotation_state[rotation_name] = SeriesRotationSnapshot(
            series_title=update.series_title,
            media_item_id=update.media_item_id,
            season_number=update.season_number,
            episode_number=update.episode_number,
            episode_sort_key=update.episode_sort_key,
        )

    def _skip_empty_program_block_until(
        self,
        *,
        candidates: list[MediaItem],
        start_at: datetime,
        target_end: datetime,
    ) -> datetime | None:
        if not self._settings.program_blocks.enabled:
            return None
        active_block_info = _active_block_info(self._settings.program_blocks.blocks, start_at)
        if active_block_info is None:
            return None
        block, _block_start, block_end = active_block_info
        if block.if_empty != "skip_block":
            return None
        if any(_matches_block_tags(item, block) for item in candidates):
            return None
        return min(block_end, target_end)

    def _choose_item_for_program_block_window(
        self,
        *,
        preferred_item: MediaItem,
        candidates: list[MediaItem],
        start_at: datetime,
        target_end: datetime,
    ) -> MediaItem:
        if not self._settings.program_blocks.enabled:
            return preferred_item

        active_block_info = _active_block_info(self._settings.program_blocks.blocks, start_at)
        if active_block_info is not None:
            block, _block_start, block_end = active_block_info
            if block.mode == "series_rotation" or block.series.enabled:
                return preferred_item
            block_candidates = [item for item in candidates if _matches_block_tags(item, block)]
            if not block_candidates:
                return preferred_item
            if _matches_block_tags(preferred_item, block):
                preferred_stop = start_at + timedelta(seconds=float(preferred_item.duration_seconds))
                if preferred_stop <= block_end:
                    return preferred_item
            remaining = max(0.0, (block_end - start_at).total_seconds())
            fitting = [item for item in block_candidates if item.duration_seconds <= remaining]
            if fitting:
                return max(fitting, key=lambda item: (item.duration_seconds, item.title.lower(), int(item.id or 0)))
            return min(block_candidates, key=lambda item: (item.duration_seconds, item.title.lower(), int(item.id or 0)))

        next_block_info = _next_block_start_info(self._settings.program_blocks.blocks, start_at, target_end)
        if next_block_info is None:
            return preferred_item
        _block, block_start = next_block_info
        gap_seconds = max(0.0, (block_start - start_at).total_seconds())
        normal_candidates = [item for item in candidates if item.duration_seconds <= gap_seconds]
        non_block_candidates = [item for item in normal_candidates if not _matches_block_tags(item, _block)]
        preferred_stop = start_at + timedelta(seconds=float(preferred_item.duration_seconds))
        if preferred_stop <= block_start and (not _matches_block_tags(preferred_item, _block) or not non_block_candidates):
            return preferred_item
        if not normal_candidates:
            return _first_matching_block_item(candidates, _block) or preferred_item
        pool = non_block_candidates or normal_candidates
        return max(pool, key=lambda item: (item.duration_seconds, item.title.lower(), int(item.id or 0)))


    def _choose_item_for_anchor_window(
        self,
        *,
        preferred_item: MediaItem,
        candidates: list[MediaItem],
        start_at: datetime,
        target_end: datetime,
        countdown_item: MediaItem | None,
    ) -> MediaItem:
        if not self._settings.program_blocks.enabled:
            return preferred_item
        anchor_info = _next_anchor_info(self._settings.program_blocks.anchors, start_at, target_end)
        if anchor_info is None:
            return preferred_item
        anchor, anchor_time = anchor_info
        anchor_candidates = [item for item in candidates if _matches_anchor_tags(item, anchor)] or candidates
        if start_at + timedelta(seconds=float(preferred_item.duration_seconds)) <= anchor_time and _matches_anchor_tags(preferred_item, anchor):
            return preferred_item

        max_countdown = self._settings.program_blocks.generated_countdown.max_duration_seconds if countdown_item else 0
        gap_seconds = (anchor_time - start_at).total_seconds()
        reserve = min(max_countdown, max(0, gap_seconds))
        fitting = [item for item in anchor_candidates if item.duration_seconds <= max(0.0, gap_seconds - reserve)]
        if not fitting and countdown_item is not None:
            fitting = [item for item in anchor_candidates if item.duration_seconds <= gap_seconds]
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
        recent_filler_ids: deque[int],
        filler_usage_counts: dict[int, int],
        last_filler_block_end: datetime,
    ) -> list[ScheduleEntry]:
        fillers = self._settings.program_blocks.fillers
        if not (_between_programmes_enabled(self._settings) and fillers.insert_between_movies and filler_candidates):
            return []
        anchor_info = _next_anchor_info(self._settings.program_blocks.anchors, start_at, target_end)
        if anchor_info is None:
            return []
        _anchor, anchor_time = anchor_info
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
            recent_filler_ids=recent_filler_ids,
            filler_usage_counts=filler_usage_counts,
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
        recent_filler_ids: deque[int],
        filler_usage_counts: dict[int, int],
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

        # Optional TV-style promo near the start of a larger bridge. Promos are
        # generated only for real programme items; the PromoGenerator rejects
        # fillers, bumpers, trailers, countdowns and other generated promos.
        if remaining >= reserve + self._settings.program_blocks.generated_promos.duration_min_seconds + 300:
            promo = self._build_generated_promo_entry(
                kind="coming_soon",
                target_item=next_item,
                start_at=cursor,
                air_time=anchor_time,
                budget_seconds=min(
                    float(self._settings.program_blocks.generated_promos.duration_max_seconds),
                    remaining - reserve,
                ),
            )
            if promo is not None:
                entries.append(promo)
                cursor = promo.end_time
                remaining = (anchor_time - cursor).total_seconds()

        while remaining > reserve:
            block_budget = remaining - reserve
            if _between_programmes_enabled(self._settings):
                block_budget = min(block_budget, float(self._settings.program_blocks.fillers.max_total_filler_block_seconds))
            block = self._build_filler_block(
                filler_candidates=filler_candidates,
                start_at=cursor,
                budget_seconds=block_budget,
                last_filler_id=last_id,
                recent_filler_ids=recent_filler_ids,
                filler_usage_counts=filler_usage_counts,
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
        reserve = self._countdown_reserve_seconds(countdown_item, remaining)
        if remaining > reserve:
            promo = self._build_generated_promo_entry(
                kind="next_up",
                target_item=next_item,
                start_at=cursor,
                air_time=anchor_time,
                budget_seconds=min(
                    float(self._settings.program_blocks.generated_promos.duration_max_seconds),
                    remaining - reserve,
                ),
            )
            if promo is not None:
                entries.append(promo)
                cursor = promo.end_time
                remaining = (anchor_time - cursor).total_seconds()

        if countdown_item is not None and 0 < remaining <= max_countdown:
            entries.append(self._countdown_entry(countdown_item, start_at=cursor, anchor_time=anchor_time, anchor=anchor))

        if entries and entries[-1].end_time == anchor_time:
            return entries
        if _between_programmes_enabled(self._settings):
            return entries
        return entries

    def _build_generated_promo_entry(
        self,
        *,
        kind: str,
        target_item: MediaItem,
        start_at: datetime,
        air_time: datetime,
        budget_seconds: float,
    ) -> ScheduleEntry | None:
        promos = self._settings.program_blocks.generated_promos
        if self._promo_factory is None or not (self._settings.program_blocks.enabled and promos.enabled):
            return None
        variant = promos.next_up if kind == "next_up" else promos.coming_soon
        if not variant.enabled:
            return None
        duration = int(min(promos.duration_max_seconds, max(promos.duration_min_seconds, budget_seconds)))
        if duration > budget_seconds or duration < promos.duration_min_seconds:
            return None
        item = self._promo_factory(
            PromoRequest(kind=kind, target=target_item, air_time=air_time, duration_seconds=duration)
        )
        if item is None or item.id is None:
            return None
        stop = start_at + timedelta(seconds=float(item.duration_seconds))
        return _entry_for_item(self._settings.channel.id, item, start_at, stop)


    def _build_filler_block(
        self,
        *,
        filler_candidates: list[MediaItem],
        start_at: datetime,
        budget_seconds: float,
        last_filler_id: int | None,
        recent_filler_ids: deque[int],
        filler_usage_counts: dict[int, int],
        max_consecutive: int,
    ) -> list[ScheduleEntry]:
        entries: list[ScheduleEntry] = []
        cursor = start_at
        remaining = budget_seconds
        last_id = last_filler_id
        while remaining > 0 and len(entries) < max_consecutive:
            filler = _select_filler(
                filler_candidates,
                budget_seconds=remaining,
                last_filler_id=last_id,
                recent_filler_ids=tuple(recent_filler_ids),
                usage_counts=filler_usage_counts,
            )
            if filler is None:
                break
            stop = cursor + timedelta(seconds=float(filler.duration_seconds))
            entries.append(_entry_for_item(self._settings.channel.id, filler, cursor, stop))
            cursor = stop
            remaining -= float(filler.duration_seconds)
            last_id = int(filler.id)
            _remember_filler_id(last_id, recent_filler_ids, filler_usage_counts)
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


def _is_series_episode(item: MediaItem) -> bool:
    return (
        item.id is not None
        and item.enabled
        and item.media_type == "episode"
        and item.series_title is not None
        and item.season_number is not None
        and item.episode_number is not None
    )


def _episode_order_key(item: MediaItem) -> tuple[str, int, int, str, int]:
    return (
        str(item.series_title or "").casefold(),
        int(item.season_number or 0),
        int(item.episode_number or 0),
        str(item.episode_sort_key or ""),
        int(item.id or 0),
    )


def _next_episode_after(series_items: list[MediaItem], episode_sort_key: str | None) -> MediaItem | None:
    if not episode_sort_key:
        return series_items[0] if series_items else None
    for item in series_items:
        current_key = str(item.episode_sort_key or _sort_key_text(item))
        if current_key > episode_sort_key:
            return item
    return None


def _sort_key_text(item: MediaItem) -> str:
    return f"{str(item.series_title or '').casefold()}:{int(item.season_number or 0):04d}:{int(item.episode_number or 0):04d}:{int(item.id or 0):08d}"


def _rotation_name(block: ProgramBlockSettings) -> str:
    return block.title.strip() or f"series_rotation_{block.start}"


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
        and item.duration_seconds >= MIN_NORMAL_PROGRAMME_DURATION_SECONDS
        and item.source_kind != SourceKind.GENERATED
        and item.media_type not in FILLER_MEDIA_TYPES
    )


def _is_schedulable_filler_item(
    item: MediaItem,
    max_duration_seconds: int,
    allowed_tags: tuple[str, ...] = (),
    denied_tags: tuple[str, ...] = (),
) -> bool:
    return (
        item.id is not None
        and item.enabled
        and item.duration_seconds > 0
        and item.media_type in FILLER_MEDIA_TYPES
        and item.duration_seconds <= max_duration_seconds
        and _matches_tags(item.tags, allowed_tags=allowed_tags, denied_tags=denied_tags, match="any")
    )


def _select_filler(
    filler_candidates: list[MediaItem],
    *,
    budget_seconds: float,
    last_filler_id: int | None,
    recent_filler_ids: tuple[int, ...] = (),
    usage_counts: dict[int, int] | None = None,
) -> MediaItem | None:
    fitting = [item for item in filler_candidates if item.duration_seconds <= budget_seconds and item.id is not None]
    if not fitting:
        return None

    usage_counts = usage_counts or {}
    pool = [item for item in fitting if int(item.id) != last_filler_id] or fitting
    recent_set = set(recent_filler_ids)
    not_recent = [item for item in pool if int(item.id) not in recent_set]
    if not_recent:
        pool = not_recent

    # Fair TV-style rotation: pick the least-used suitable filler first.  Duration
    # remains a secondary criterion so that larger gaps are still filled sensibly,
    # but the first two DB rows cannot dominate the whole schedule anymore.
    return min(
        pool,
        key=lambda item: (
            usage_counts.get(int(item.id), 0),
            -float(item.duration_seconds),
            item.title.casefold(),
            int(item.id),
        ),
    )


def _recent_filler_window_size(filler_candidates: list[MediaItem]) -> int:
    if len(filler_candidates) <= 2:
        return max(0, len(filler_candidates) - 1)
    return min(5, len(filler_candidates) - 1)


def _remember_filler_id(
    media_item_id: int,
    recent_filler_ids: deque[int],
    usage_counts: dict[int, int],
) -> None:
    usage_counts[media_item_id] = usage_counts.get(media_item_id, 0) + 1
    if recent_filler_ids.maxlen and media_item_id not in recent_filler_ids:
        recent_filler_ids.append(media_item_id)
    elif recent_filler_ids.maxlen:
        # Move repeated IDs to the end when the fallback pool had no alternative.
        try:
            recent_filler_ids.remove(media_item_id)
        except ValueError:
            pass
        recent_filler_ids.append(media_item_id)


def _remember_filler_entries(
    entries: list[ScheduleEntry],
    countdown_item: MediaItem | None,
    recent_filler_ids: deque[int],
    usage_counts: dict[int, int],
) -> None:
    countdown_id = countdown_item.id if countdown_item is not None else None
    for entry in entries:
        if entry.media_item_id == countdown_id:
            continue
        _remember_filler_id(entry.media_item_id, recent_filler_ids, usage_counts)


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
    info = _next_anchor_info(anchors, now, target_end)
    return info[1] if info is not None else None


def _next_anchor_info(
    anchors: tuple[ProgramBlockAnchorSettings, ...],
    now: datetime,
    target_end: datetime,
) -> tuple[ProgramBlockAnchorSettings, datetime] | None:
    anchor = _next_enabled_anchor(anchors, now)
    if anchor is None:
        return None
    value = _anchor_datetime(now, anchor.time)
    if value > target_end:
        return None
    return anchor, value


def _next_enabled_anchor(
    anchors: tuple[ProgramBlockAnchorSettings, ...],
    now: datetime,
) -> ProgramBlockAnchorSettings | None:
    enabled = [anchor for anchor in anchors if anchor.enabled]
    if not enabled:
        return None
    return min(enabled, key=lambda anchor: _anchor_datetime(now, anchor.time))


def _anchor_at(anchors: tuple[ProgramBlockAnchorSettings, ...], moment: datetime) -> ProgramBlockAnchorSettings | None:
    hhmm = f"{moment.hour:02d}:{moment.minute:02d}"
    for anchor in anchors:
        if anchor.enabled and anchor.time == hhmm:
            return anchor
    return None


def _active_block_at(blocks: tuple[ProgramBlockSettings, ...], moment: datetime) -> ProgramBlockSettings | None:
    info = _active_block_info(blocks, moment)
    return info[0] if info is not None else None


def _active_block_info(
    blocks: tuple[ProgramBlockSettings, ...], moment: datetime
) -> tuple[ProgramBlockSettings, datetime, datetime] | None:
    active: list[tuple[ProgramBlockSettings, datetime, datetime]] = []
    for block in blocks:
        if not block.enabled:
            continue
        start = _block_start_datetime(moment, block.start)
        end = start + timedelta(seconds=block.duration_seconds)
        if start <= moment < end:
            active.append((block, start, end))
    if not active:
        return None
    # Prefer the most recently started block when definitions overlap.
    return max(active, key=lambda item: item[1])


def _next_block_start_info(
    blocks: tuple[ProgramBlockSettings, ...], now: datetime, target_end: datetime
) -> tuple[ProgramBlockSettings, datetime] | None:
    upcoming: list[tuple[ProgramBlockSettings, datetime]] = []
    for block in blocks:
        if not block.enabled:
            continue
        start = _anchor_datetime(now, block.start)
        if now < start <= target_end:
            upcoming.append((block, start))
    if not upcoming:
        return None
    return min(upcoming, key=lambda item: item[1])


def _block_start_datetime(moment: datetime, value: str) -> datetime:
    start = _anchor_datetime(moment, value)
    if start > moment:
        previous = start - timedelta(days=1)
        return previous
    return start


def _first_matching_anchor_item(items: list[MediaItem], anchor: ProgramBlockAnchorSettings) -> MediaItem | None:
    for item in items:
        if _matches_anchor_tags(item, anchor):
            return item
    return None


def _first_matching_block_item(items: list[MediaItem], block: ProgramBlockSettings) -> MediaItem | None:
    for item in items:
        if _matches_block_tags(item, block):
            return item
    return None


def _anchor_datetime(now: datetime, value: str) -> datetime:
    hour, minute = (int(part) for part in value.split(":"))
    candidate = datetime.combine(now.date(), time(hour=hour, minute=minute), tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _matches_anchor_tags(item: MediaItem, anchor: ProgramBlockAnchorSettings) -> bool:
    return _matches_tags(
        item.tags,
        allowed_tags=anchor.allowed_tags,
        denied_tags=anchor.denied_tags,
        match=anchor.tag_match,
    )


def _matches_block_tags(item: MediaItem, block: ProgramBlockSettings) -> bool:
    return _matches_tags(
        item.tags,
        allowed_tags=block.allowed_tags,
        denied_tags=block.denied_tags,
        match=block.tag_match,
    )


def _matches_tags(
    item_tags: tuple[str, ...],
    *,
    allowed_tags: tuple[str, ...],
    denied_tags: tuple[str, ...],
    match: str,
) -> bool:
    tag_set = set(item_tags)
    if denied_tags and tag_set.intersection(denied_tags):
        return False
    if not allowed_tags:
        return True
    allowed_set = set(allowed_tags)
    if match == "all":
        return allowed_set.issubset(tag_set)
    return bool(tag_set.intersection(allowed_set))


def _description_for(item: MediaItem) -> str:
    if item.media_type in FILLER_MEDIA_TYPES:
        return "PrivateTV filler clip"
    if item.source_kind == SourceKind.DVD_STRUCTURE:
        return "Local DVD structure"
    if item.source_kind == SourceKind.GENERATED:
        return "Generated PrivateTV clip"
    return "Local media file"
