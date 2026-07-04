from __future__ import annotations

import logging
import random
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from privatetv.config import AppSettings
from privatetv.db import MediaRepository, connect_database
from privatetv.domain.errors import PrivateTvError
from privatetv.domain.models import CurrentProgramme, MediaAsset, MediaItem, ScheduleEntry
from privatetv.streaming import StreamProvider
from privatetv.util.time import now_in_zone

LOGGER = logging.getLogger(__name__)


class HazardSelectionError(PrivateTvError):
    """Raised when Hazard TV cannot select a random playable movie."""


class RandomLike(Protocol):
    def choice(self, seq): ...


class HazardRandomStreamProvider:
    """Produces the Hazard TV channel.

    Hazard TV has no playlist and no EPG. Each HTTP request starts with one
    random playable media item at offset 0. When that item ends and the client
    remains connected, another random media item is selected and streamed from
    the beginning. The stream runs until the client disconnects or no playable
    media exists.
    """

    def __init__(
        self,
        settings: AppSettings,
        stream_provider: StreamProvider,
        *,
        random_source: RandomLike | None = None,
    ) -> None:
        self._settings = settings
        self._stream_provider = stream_provider
        self._random = random_source or random.Random(settings.hazard_channel.random_seed)
        self._last_media_id: int | None = None

    async def open_stream(self) -> AsyncIterator[bytes]:
        while True:
            media, assets = self._select_next_media()
            programme = self._programme_for(media)
            LOGGER.info("Hazard TV selected %r", media.title)
            async for chunk in self._stream_provider.open_stream(programme, assets):
                yield chunk

    def _select_next_media(self) -> tuple[MediaItem, list[MediaAsset]]:
        with connect_database(self._settings.database.path) as connection:
            repository = MediaRepository(connection)
            candidates = repository.list_playable_media_items()
            if not candidates:
                raise HazardSelectionError("Hazard TV has no playable media items")
            selectable = candidates
            if (
                self._settings.hazard_channel.avoid_immediate_repeat
                and len(candidates) > 1
                and self._last_media_id is not None
            ):
                selectable = [item for item in candidates if item.id != self._last_media_id]
            media = self._random.choice(selectable)
            if media.id is None:
                raise HazardSelectionError(f"Selected media has no database id: {media.title}")
            assets = repository.list_assets(media.id)
        self._last_media_id = media.id
        return media, assets

    def _programme_for(self, media: MediaItem) -> CurrentProgramme:
        if media.id is None:
            raise HazardSelectionError(f"Selected media has no database id: {media.title}")
        now = now_in_zone(self._settings.schedule.zoneinfo).replace(microsecond=0)
        entry = ScheduleEntry(
            id=None,
            channel_id=self._settings.hazard_channel.id,
            media_item_id=media.id,
            start_time=now,
            end_time=now + timedelta(seconds=max(1, int(media.duration_seconds))),
            start_offset_seconds=0,
            title=media.title,
            description="Random Hazard TV selection",
        )
        return CurrentProgramme(media=media, schedule_entry=entry, offset_seconds=0.0)
