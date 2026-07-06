from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from privatetv.config import AppSettings
from privatetv.db import ScheduleRepository
from privatetv.schedule.builder import ScheduleBuilder
from privatetv.schedule.countdown import ensure_generated_countdown_media
from privatetv.schedule.promos import PromoGenerator


@dataclass(frozen=True, slots=True)
class ScheduleMaintenanceResult:
    """Result of ensuring that the stored EPG timeline is long enough."""

    schedule_until_before: datetime | None
    schedule_until_after: datetime | None
    required_until: datetime
    target_until: datetime
    start_at: datetime | None
    schedulable_media_items: int
    inserted_entries: int

    @property
    def extended(self) -> bool:
        return self.inserted_entries > 0

    @property
    def had_enough_schedule(self) -> bool:
        return (
            self.schedule_until_before is not None
            and self.schedule_until_before >= self.required_until
        )


class ScheduleMaintainer:
    """Extends the stored linear timeline without changing past entries."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def ensure_schedule(
        self,
        connection: sqlite3.Connection,
        *,
        now: datetime,
    ) -> ScheduleMaintenanceResult:
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        repository = ScheduleRepository(connection)
        before = repository.get_schedule_end(self._settings.channel.id)
        required_until = now + timedelta(days=self._settings.schedule.minimum_days_ahead)
        target_until = now + timedelta(days=self._settings.schedule.days_ahead)

        if before is not None and before >= required_until:
            return ScheduleMaintenanceResult(
                schedule_until_before=before,
                schedule_until_after=before,
                required_until=required_until,
                target_until=target_until,
                start_at=None,
                schedulable_media_items=0,
                inserted_entries=0,
            )

        ensure_generated_countdown_media(connection, self._settings)
        media_items = repository.list_schedulable_media_items()
        if not media_items:
            return ScheduleMaintenanceResult(
                schedule_until_before=before,
                schedule_until_after=before,
                required_until=required_until,
                target_until=target_until,
                start_at=None,
                schedulable_media_items=0,
                inserted_entries=0,
            )

        start_at = before if before is not None and before > now else now
        if start_at >= target_until:
            return ScheduleMaintenanceResult(
                schedule_until_before=before,
                schedule_until_after=before,
                required_until=required_until,
                target_until=target_until,
                start_at=start_at,
                schedulable_media_items=len(media_items),
                inserted_entries=0,
            )

        promo_generator = PromoGenerator(connection, self._settings)
        build_result = ScheduleBuilder(self._settings, promo_factory=promo_generator.create).build(
            media_items,
            start_at=start_at,
            end_at=target_until,
        )
        inserted = repository.append_entries(build_result.entries)
        after = repository.get_schedule_end(self._settings.channel.id)
        return ScheduleMaintenanceResult(
            schedule_until_before=before,
            schedule_until_after=after,
            required_until=required_until,
            target_until=target_until,
            start_at=start_at,
            schedulable_media_items=len(media_items),
            inserted_entries=inserted,
        )
