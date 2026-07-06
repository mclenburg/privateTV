from __future__ import annotations

import hashlib
import locale
import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.tags import tags_for_media_item

LOGGER = logging.getLogger(__name__)

PROMO_MEDIA_TYPE = "generated_promo"
PROMO_SOURCE_PREFIX = "generated://privatetv/promo/"


@dataclass(frozen=True, slots=True)
class PromoRequest:
    kind: str
    target: MediaItem
    air_time: datetime | None
    duration_seconds: int


class PromoGenerator:
    def __init__(self, connection, settings: AppSettings) -> None:
        self._connection = connection
        self._settings = settings
        self._repository = MediaRepository(connection)

    def create(self, request: PromoRequest) -> MediaItem | None:
        if not _is_promotable(request.target, self._settings):
            return None
        assets = self._repository.list_assets(int(request.target.id)) if request.target.id is not None else []
        source_path = assets[0].path if assets else _source_path_from_item(request.target)
        if source_path is None or not source_path.exists():
            LOGGER.warning("Cannot generate promo for %s: source media path missing", request.target.title)
            return None

        duration = max(
            self._settings.program_blocks.generated_promos.duration_min_seconds,
            min(request.duration_seconds, self._settings.program_blocks.generated_promos.duration_max_seconds),
        )
        variant = (
            self._settings.program_blocks.generated_promos.next_up
            if request.kind == "next_up"
            else self._settings.program_blocks.generated_promos.coming_soon
        )
        if not (self._settings.program_blocks.generated_promos.enabled and variant.enabled):
            return None

        label = variant.title_template.strip() or ("Als nächstes" if request.kind == "next_up" else "Coming soon")
        air = _format_air_time(request.air_time) if variant.include_air_time and request.air_time is not None else ""
        digest = _promo_digest(request.kind, request.target, request.air_time, duration, label, air)
        output_path = promo_clip_path(self._settings) / f"{digest}.mp4"
        if not _ensure_promo_file(output_path, source_path, request.target, duration, label, air, self._settings):
            return None

        title = f"{label}: {request.target.title}" if label else request.target.title
        description = air if air else f"PrivateTV generated promo for {request.target.title}"
        item = MediaItem(
            id=None,
            source_kind=SourceKind.GENERATED,
            source_uri=f"{PROMO_SOURCE_PREFIX}{digest}",
            source_root=output_path.parent,
            title=title,
            media_type=PROMO_MEDIA_TYPE,
            duration_seconds=float(duration),
            enabled=True,
            container="mp4",
            video_codec="h264",
            audio_codec="aac",
            file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
            mtime=int(output_path.stat().st_mtime) if output_path.exists() else None,
            scan_status=ScanStatus.OK,
            scan_error=None,
        )
        asset = MediaAsset(
            id=None,
            media_item_id=0,
            asset_order=1,
            path=output_path,
            role="primary",
            file_size_bytes=output_path.stat().st_size if output_path.exists() else None,
        )
        media_item_id = self._repository.upsert_media_item(item, [asset])
        self._repository.replace_media_tags(media_item_id, tags_for_media_item(item))
        return MediaItem(
            id=media_item_id,
            source_kind=item.source_kind,
            source_uri=item.source_uri,
            source_root=item.source_root,
            title=item.title,
            media_type=item.media_type,
            duration_seconds=item.duration_seconds,
            enabled=item.enabled,
            container=item.container,
            video_codec=item.video_codec,
            audio_codec=item.audio_codec,
            file_size_bytes=item.file_size_bytes,
            mtime=item.mtime,
            scan_status=item.scan_status,
            scan_error=item.scan_error,
            tags=("filler", "generated", "promo", "generated_promo"),
        )


def promo_clip_path(settings: AppSettings) -> Path:
    base = settings.database.path.parent if settings.database.path.name != ":memory:" else Path("/tmp/privatetv")
    return base / "generated" / "promos"


def _ensure_promo_file(output_path: Path, source_path: Path, target: MediaItem, duration: int, label: str, air: str, settings: AppSettings) -> bool:
    if output_path.exists() and output_path.stat().st_size > 0:
        return True
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = _build_ffmpeg_promo_command(output_path, source_path, target, duration, label, air, settings)
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        LOGGER.warning("Could not generate PrivateTV promo clip at %s: %s", output_path, stderr)
        output_path.unlink(missing_ok=True)
        return False
    return output_path.exists() and output_path.stat().st_size > 0


def _build_ffmpeg_promo_command(output_path: Path, source_path: Path, target: MediaItem, duration: int, label: str, air: str, settings: AppSettings) -> tuple[str, ...]:
    font = _find_font()
    font_arg = f"fontfile={font}:" if font else ""
    start = _clip_start_seconds(target.duration_seconds, duration)
    title = _escape_drawtext(target.title)
    label_text = _escape_drawtext(label)
    air_text = _escape_drawtext(air)
    vf_parts = ["scale=1280:-2,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black"]
    vf_parts.append(f"drawbox=x=0:y=ih-190:w=iw:h=190:color=black@0.55:t=fill")
    vf_parts.append(f"drawtext={font_arg}text={label_text}:x=60:y=h-165:fontsize=42:fontcolor=white")
    vf_parts.append(f"drawtext={font_arg}text={title}:x=60:y=h-108:fontsize=48:fontcolor=white")
    if air_text:
        vf_parts.append(f"drawtext={font_arg}text={air_text}:x=60:y=h-48:fontsize=36:fontcolor=white")
    return (
        str(settings.streaming.ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source_path),
        "-t",
        str(duration),
        "-vf",
        ",".join(vf_parts),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-ar",
        "48000",
        "-shortest",
        str(output_path),
    )


def _clip_start_seconds(duration: float, clip_duration: int) -> float:
    if duration <= clip_duration + 5:
        return 0.0
    # Avoid black lead-in/credits; for long movies use a point around one third.
    return max(0.0, min(duration * 0.33, duration - clip_duration - 2))


def _source_path_from_item(item: MediaItem) -> Path | None:
    if item.source_uri.startswith("file://"):
        from urllib.parse import unquote, urlparse
        return Path(unquote(urlparse(item.source_uri).path))
    return None


def _is_promotable(item: MediaItem, settings: AppSettings) -> bool:
    denied = set(settings.program_blocks.generated_promos.promotable_denied_tags)
    tags = set(item.tags)
    if item.id is None or not item.enabled:
        return False
    if item.source_kind == SourceKind.GENERATED:
        return False
    if item.media_type in {"filler", "trailer", "bumper", "commercial", "advertisement", "dvd_preview", "generated_countdown", "generated_promo"}:
        return False
    if tags.intersection(denied):
        return False
    return item.duration_seconds >= settings.program_blocks.generated_promos.promotable_min_duration_seconds


def _promo_digest(kind: str, target: MediaItem, air_time: datetime | None, duration: int, label: str, air: str) -> str:
    raw = "|".join(
        [
            kind,
            str(target.id or 0),
            target.source_uri,
            air_time.isoformat() if air_time else "",
            str(duration),
            label,
            air,
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _format_air_time(moment: datetime) -> str:
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass
    return moment.strftime("%A %H:%M")


def _find_font() -> str | None:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _escape_drawtext(value: str) -> str:
    """Escape text for an unquoted FFmpeg drawtext text= value."""
    escaped = value.replace("\\", "\\\\")
    for character in (":", ",", ";", "'"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped
