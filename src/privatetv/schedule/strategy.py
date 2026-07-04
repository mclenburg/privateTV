from __future__ import annotations

import random
from abc import ABC, abstractmethod

from privatetv.domain.errors import ConfigurationError
from privatetv.domain.models import MediaItem


class ScheduleStrategy(ABC):
    """Selects an ordered media sequence for schedule generation."""

    @abstractmethod
    def order(self, items: list[MediaItem]) -> list[MediaItem]:
        raise NotImplementedError


class AlphabeticalStrategy(ScheduleStrategy):
    """Stable debug strategy that orders titles alphabetically."""

    def order(self, items: list[MediaItem]) -> list[MediaItem]:
        return sorted(items, key=lambda item: (item.title.casefold(), item.source_uri))


class ShuffleNoRepeatStrategy(ScheduleStrategy):
    """Shuffle all items once before any title is repeated."""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def order(self, items: list[MediaItem]) -> list[MediaItem]:
        ordered = list(items)
        ordered.sort(key=lambda item: (item.title.casefold(), item.source_uri))
        self._random.shuffle(ordered)
        return ordered


def create_schedule_strategy(name: str, *, random_seed: int | None = None) -> ScheduleStrategy:
    normalized = name.strip().lower()
    if normalized == "alphabetical":
        return AlphabeticalStrategy()
    if normalized == "shuffle_no_repeat":
        return ShuffleNoRepeatStrategy(random_seed)
    if normalized == "time_blocks":
        raise ConfigurationError("schedule.strategy=time_blocks is reserved for a later release")
    raise ConfigurationError(f"Unsupported schedule strategy: {name}")
