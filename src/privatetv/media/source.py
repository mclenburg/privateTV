from __future__ import annotations

from abc import ABC, abstractmethod

from privatetv.domain.models import MediaItem, StreamCommand


class MediaSource(ABC):
    """Source abstraction for local files, DVD structures and future providers."""

    @abstractmethod
    def scan(self) -> list[MediaItem]:
        raise NotImplementedError

    @abstractmethod
    def create_stream_command(self, item: MediaItem, offset_seconds: float) -> StreamCommand:
        raise NotImplementedError
