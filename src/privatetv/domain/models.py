from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class SourceKind(StrEnum):
    LOCAL_FILE = "local_file"
    DVD_STRUCTURE = "dvd_structure"
    STREAMING_SERVICE = "streaming_service"
    GENERATED = "generated"


class ScanStatus(StrEnum):
    OK = "ok"
    MISSING = "missing"
    UNSUPPORTED = "unsupported"
    PROBE_FAILED = "probe_failed"


@dataclass(frozen=True, slots=True)
class MediaItem:
    id: int | None
    source_kind: SourceKind
    source_uri: str
    source_root: Path | None
    title: str
    media_type: str
    duration_seconds: float
    enabled: bool = True
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    file_size_bytes: int | None = None
    mtime: int | None = None
    scan_status: ScanStatus = ScanStatus.OK
    scan_error: str | None = None


@dataclass(frozen=True, slots=True)
class MediaAsset:
    id: int | None
    media_item_id: int
    asset_order: int
    path: Path
    role: str
    file_size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    id: int | None
    channel_id: str
    media_item_id: int
    start_time: datetime
    end_time: datetime
    start_offset_seconds: float
    title: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentProgramme:
    media: MediaItem
    schedule_entry: ScheduleEntry
    offset_seconds: float


@dataclass(frozen=True, slots=True)
class StreamCommand:
    argv: tuple[str, ...]
    seek_tolerance_seconds: int
