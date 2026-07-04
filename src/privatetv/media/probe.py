from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from privatetv.domain.errors import PrivateTvError


class ProbeError(PrivateTvError):
    """Raised when ffprobe cannot read usable metadata from a media file."""


@dataclass(frozen=True, slots=True)
class ProbeResult:
    path: Path
    duration_seconds: float
    container: str | None
    video_codec: str | None
    audio_codec: str | None
    file_size_bytes: int
    mtime: int


class FfprobeMediaProbe:
    def __init__(self, ffprobe_path: Path) -> None:
        self._ffprobe_path = ffprobe_path

    def probe(self, path: Path) -> ProbeResult:
        if not path.exists():
            raise ProbeError(f"Media file does not exist: {path}")
        if not path.is_file():
            raise ProbeError(f"Media path is not a file: {path}")

        command = [
            str(self._ffprobe_path),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "unknown ffprobe error"
            raise ProbeError(f"ffprobe failed for {path}: {message}")

        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"ffprobe returned invalid JSON for {path}") from exc

        return probe_result_from_payload(path, payload)


def probe_result_from_payload(path: Path, payload: dict) -> ProbeResult:
    file_stat = path.stat()
    format_data = payload.get("format") or {}
    raw_duration = format_data.get("duration")
    if raw_duration is None:
        raise ProbeError(f"ffprobe returned no duration for {path}")

    try:
        duration_seconds = float(raw_duration)
    except (TypeError, ValueError) as exc:
        raise ProbeError(f"ffprobe returned invalid duration for {path}: {raw_duration}") from exc

    if duration_seconds <= 0:
        raise ProbeError(f"ffprobe returned non-positive duration for {path}: {duration_seconds}")

    streams = payload.get("streams") or []
    video_codec = _first_codec(streams, "video")
    audio_codec = _first_codec(streams, "audio")
    container = _first_container_name(format_data.get("format_name"))

    return ProbeResult(
        path=path,
        duration_seconds=duration_seconds,
        container=container,
        video_codec=video_codec,
        audio_codec=audio_codec,
        file_size_bytes=file_stat.st_size,
        mtime=int(file_stat.st_mtime),
    )


def _first_codec(streams: list[dict], codec_type: str) -> str | None:
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            codec_name = stream.get("codec_name")
            return str(codec_name) if codec_name else None
    return None


def _first_container_name(format_name: object) -> str | None:
    if not format_name:
        return None
    return str(format_name).split(",", maxsplit=1)[0]
