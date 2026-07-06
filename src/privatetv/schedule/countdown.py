from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from privatetv.config import AppSettings
from privatetv.db.media_repository import MediaRepository
from privatetv.domain.models import MediaAsset, MediaItem, ScanStatus, SourceKind
from privatetv.media.tags import tags_for_media_item

LOGGER = logging.getLogger(__name__)
COUNTDOWN_DURATION_SECONDS = 60
COUNTDOWN_SOURCE_URI = "generated://privatetv/countdown-60"


def ensure_generated_countdown_media(connection, settings: AppSettings) -> int | None:
    """Ensure the optional generated 60s countdown exists in the media catalog.

    The scheduler may use a suffix of this 60 second asset for shorter countdowns
    by setting a schedule start offset. If generation fails, scheduling continues
    without countdown entries.
    """
    if not (
        settings.program_blocks.enabled
        and settings.program_blocks.generated_countdown.enabled
        and settings.program_blocks.generated_countdown.max_duration_seconds > 0
    ):
        return None

    output_path = countdown_clip_path(settings)
    if not _ensure_countdown_file(output_path, settings):
        return None

    title = settings.program_blocks.generated_countdown.title.strip() or "Gleich geht's weiter"
    item = MediaItem(
        id=None,
        source_kind=SourceKind.GENERATED,
        source_uri=COUNTDOWN_SOURCE_URI,
        source_root=output_path.parent,
        title=title,
        media_type="generated_countdown",
        duration_seconds=float(COUNTDOWN_DURATION_SECONDS),
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
    repository = MediaRepository(connection)
    media_item_id = repository.upsert_media_item(item, [asset])
    repository.replace_media_tags(media_item_id, tags_for_media_item(item))
    return media_item_id


def countdown_clip_path(settings: AppSettings) -> Path:
    base = settings.database.path.parent if settings.database.path.name != ":memory:" else Path("/tmp/privatetv")
    return base / "generated" / "countdowns" / "countdown_60.mp4"


def _ensure_countdown_file(output_path: Path, settings: AppSettings) -> bool:
    if output_path.exists() and output_path.stat().st_size > 0:
        return True
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = _build_ffmpeg_countdown_command(output_path, settings)
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        stderr = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        LOGGER.warning("Could not generate PrivateTV countdown clip at %s: %s", output_path, stderr)
        output_path.unlink(missing_ok=True)
        return False
    return output_path.exists() and output_path.stat().st_size > 0


def _build_ffmpeg_countdown_command(output_path: Path, settings: AppSettings) -> tuple[str, ...]:
    # Keep this self-contained: generated clip, no external media files required.
    # It is intentionally 60s long; shorter countdowns seek into this asset.
    font = _find_font()
    title = _escape_drawtext(settings.program_blocks.generated_countdown.title or "Gleich geht's weiter")
    font_arg = f"fontfile={font}:" if font else ""
    countdown_text = r"%{eif\\:60-t\\:d}"
    vf = (
        f"drawtext={font_arg}text={title}:x=(w-tw)/2:y=h*0.25:fontsize=54:fontcolor=white,"
        f"drawtext={font_arg}text={countdown_text}:x=(w-tw)/2:y=(h-th)/2:fontsize=150:fontcolor=white,"
        f"drawtext={font_arg}text={_escape_drawtext('PrivateTV')}:x=(w-tw)/2:y=h*0.72:fontsize=42:fontcolor=white"
    )
    return (
        str(settings.streaming.ffmpeg_path),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1280x720:r=25:d={COUNTDOWN_DURATION_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        str(COUNTDOWN_DURATION_SECONDS),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    )


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
    """Escape text for an unquoted FFmpeg drawtext text= value.

    Do not wrap the value in single quotes. A title such as "Gleich geht's
    weiter" would otherwise leak into the following filter on FFmpeg's
    filtergraph parser and break the countdown expression.
    """
    escaped = value.replace("\\", "\\\\")
    for character in (":", ",", ";", "'"):
        escaped = escaped.replace(character, f"\\{character}")
    return escaped
