from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from privatetv.config import AppSettings


@dataclass(frozen=True, slots=True)
class SeekSpikeReport:
    """Documents the accepted seek behavior for the current FFmpeg strategy."""

    ffmpeg_path: Path
    offset_seconds: float
    accepted_tolerance_seconds: int
    stream_copy: bool
    command: tuple[str, ...]
    note: str

    def as_text(self) -> str:
        command = " ".join(self.command)
        return (
            "PrivateTV seek spike\n"
            "====================\n"
            f"FFmpeg:              {self.ffmpeg_path}\n"
            f"Requested offset:    {self.offset_seconds:.3f}s\n"
            f"Stream copy:         {'yes' if self.stream_copy else 'no'}\n"
            f"Accepted tolerance:  {self.accepted_tolerance_seconds}s\n"
            f"Command shape:       {command}\n\n"
            f"Result policy:       {self.note}\n"
        )


def build_seek_spike_report(settings: AppSettings, *, offset_seconds: float = 120.0) -> SeekSpikeReport:
    """Return the documented seek policy for V1.0.

    PrivateTV intentionally uses ``-ss`` before ``-i`` together with stream copy.
    That is fast and cheap on Raspberry Pi hardware, but it is keyframe-based for
    many containers. V1.0 treats the configured tolerance as accepted behavior,
    not as an implementation defect.
    """

    command = (
        str(settings.streaming.ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "warning",
        "-ss",
        f"{max(0.0, offset_seconds):.3f}",
        "-re",
        "-i",
        "<media-file>",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-c",
        "copy",
        "-f",
        settings.streaming.output_container,
        "pipe:1",
    )
    note = (
        "V1.0 accepts keyframe-aligned startup when stream-copy seeking is used. "
        "If real media regularly exceeds the configured tolerance, a later patch "
        "must add a slower accurate-seek or transcode profile."
    )
    return SeekSpikeReport(
        ffmpeg_path=settings.streaming.ffmpeg_path,
        offset_seconds=max(0.0, offset_seconds),
        accepted_tolerance_seconds=settings.streaming.accepted_seek_tolerance_seconds,
        stream_copy=settings.streaming.prefer_stream_copy,
        command=command,
        note=note,
    )
