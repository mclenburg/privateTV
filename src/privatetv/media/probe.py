from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from privatetv.domain.errors import PrivateTvError


class ProbeError(PrivateTvError):
    """Raised when ffprobe cannot read usable metadata from a media file."""


SUSPICIOUS_SHORT_DURATION_SECONDS = 60.0
SUSPICIOUS_MIN_FILE_SIZE_BYTES = 50 * 1024 * 1024


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

        payload = self._run_json_probe(
            [
                str(self._ffprobe_path),
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            path=path,
            timeout=30,
        )
        result = probe_result_from_payload(path, payload)
        packet_duration = self._packet_count_duration_if_useful(path, result)
        if packet_duration is None:
            return result
        return ProbeResult(
            path=result.path,
            duration_seconds=packet_duration,
            container=result.container,
            video_codec=result.video_codec,
            audio_codec=result.audio_codec,
            file_size_bytes=result.file_size_bytes,
            mtime=result.mtime,
        )

    def _run_json_probe(self, command: list[str], *, path: Path, timeout: int) -> dict:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "unknown ffprobe error"
            raise ProbeError(f"ffprobe failed for {path}: {message}")

        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ProbeError(f"ffprobe returned invalid JSON for {path}") from exc

    def _packet_count_duration_if_useful(self, path: Path, result: ProbeResult) -> float | None:
        if result.duration_seconds >= SUSPICIOUS_SHORT_DURATION_SECONDS:
            return None
        if result.file_size_bytes < SUSPICIOUS_MIN_FILE_SIZE_BYTES:
            return None
        if result.video_codec is None:
            return None
        try:
            payload = self._run_json_probe(
                [
                    str(self._ffprobe_path),
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-count_packets",
                    "-print_format",
                    "json",
                    "-show_entries",
                    "stream=nb_read_packets,r_frame_rate,avg_frame_rate",
                    str(path),
                ],
                path=path,
                timeout=180,
            )
        except (ProbeError, subprocess.TimeoutExpired):
            return None
        packet_duration = packet_count_duration_from_payload(payload)
        if packet_duration is None:
            return None
        if packet_duration <= max(result.duration_seconds, SUSPICIOUS_SHORT_DURATION_SECONDS):
            return None
        return packet_duration


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


def packet_count_duration_from_payload(payload: dict) -> float | None:
    streams = payload.get("streams") or []
    for stream in streams:
        packets = _positive_int(stream.get("nb_read_packets"))
        if packets is None:
            continue
        fps = _rate_to_float(stream.get("avg_frame_rate")) or _rate_to_float(stream.get("r_frame_rate"))
        if fps is None or fps <= 0:
            continue
        return packets / fps
    return None


def _positive_int(value: object) -> int | None:
    try:
        number = int(str(value))
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _rate_to_float(value: object) -> float | None:
    if value in (None, "", "0/0"):
        return None
    text = str(value)
    try:
        if "/" in text:
            rate = Fraction(text)
            return float(rate) if rate.denominator else None
        return float(text)
    except (ValueError, ZeroDivisionError):
        return None
