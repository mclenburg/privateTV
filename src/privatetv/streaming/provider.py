from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from privatetv.domain.models import CurrentProgramme, MediaAsset


class StreamProvider(ABC):
    """Produces bytes for one TV channel stream.

    Implementations may start one FFmpeg process per client or later share a
    channel process between multiple clients. The HTTP layer must not know which
    strategy is active.
    """

    @abstractmethod
    async def open_stream(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> AsyncIterator[bytes]:
        raise NotImplementedError
