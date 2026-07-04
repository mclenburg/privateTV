from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from privatetv.config import AppSettings
from privatetv.domain.models import MediaAsset


@dataclass(frozen=True, slots=True)
class DvdConcatCandidate:
    """One FFmpeg candidate command for DVD VOB concatenation."""

    name: str
    command: tuple[str, ...]
    temp_file: Path | None = None


@dataclass(frozen=True, slots=True)
class DvdConcatAttempt:
    """Observed result of running one concat candidate."""

    name: str
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool


@dataclass(frozen=True, slots=True)
class DvdConcatSpikeResult:
    """Spike result containing command candidates and optional execution results."""

    candidates: tuple[DvdConcatCandidate, ...]
    attempts: tuple[DvdConcatAttempt, ...]

    def as_text(self) -> str:
        lines = ["PrivateTV DVD concat spike", "==========================", ""]
        lines.append("Candidate commands:")
        for candidate in self.candidates:
            lines.append(f"- {candidate.name}: {' '.join(candidate.command)}")
        if not self.attempts:
            lines.append("")
            lines.append("Commands were built but not executed.")
            return "\n".join(lines) + "\n"
        lines.append("")
        lines.append("Execution results:")
        for attempt in self.attempts:
            status = "timeout" if attempt.timed_out else f"exit {attempt.returncode}"
            lines.append(f"- {attempt.name}: {status}")
            if attempt.stderr.strip():
                lines.append(f"  stderr: {attempt.stderr.strip()[:500]}")
        return "\n".join(lines) + "\n"


class DvdConcatSpikeRunner:
    """Builds and optionally runs DVD concat spike commands.

    The intent is not to hide DVD timestamp quirks. The spike makes the chosen
    V1.0 command explicit and compares it with the concat protocol so real DVD
    samples can be tested before tvheadend acceptance.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build_candidates(
        self,
        assets: tuple[MediaAsset, ...],
        *,
        offset_seconds: float = 0.0,
        seconds_to_read: int = 15,
    ) -> tuple[DvdConcatCandidate, ...]:
        ordered = tuple(sorted(assets, key=lambda item: item.asset_order))
        if not ordered:
            raise ValueError("DVD concat spike needs at least one media asset")
        demuxer_file = _write_ffconcat(ordered)
        return (
            DvdConcatCandidate(
                name="concat-demuxer-genpts",
                temp_file=demuxer_file,
                command=(
                    str(self._settings.streaming.ffmpeg_path),
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-ss",
                    _format_seconds(offset_seconds),
                    "-fflags",
                    "+genpts",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(demuxer_file),
                    "-t",
                    str(seconds_to_read),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c",
                    "copy",
                    "-f",
                    self._settings.streaming.output_container,
                    "-y",
                    "/dev/null",
                ),
            ),
            DvdConcatCandidate(
                name="concat-protocol",
                command=(
                    str(self._settings.streaming.ffmpeg_path),
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-ss",
                    _format_seconds(offset_seconds),
                    "-i",
                    _concat_protocol_uri(ordered),
                    "-t",
                    str(seconds_to_read),
                    "-map",
                    "0:v:0",
                    "-map",
                    "0:a:0?",
                    "-c",
                    "copy",
                    "-f",
                    self._settings.streaming.output_container,
                    "-y",
                    "/dev/null",
                ),
            ),
        )

    def run(
        self,
        assets: tuple[MediaAsset, ...],
        *,
        offset_seconds: float = 0.0,
        seconds_to_read: int = 15,
        timeout_seconds: int = 30,
        execute: bool = False,
    ) -> DvdConcatSpikeResult:
        candidates = self.build_candidates(
            assets,
            offset_seconds=offset_seconds,
            seconds_to_read=seconds_to_read,
        )
        if not execute:
            return DvdConcatSpikeResult(candidates=candidates, attempts=())
        attempts: list[DvdConcatAttempt] = []
        try:
            for candidate in candidates:
                attempts.append(_run_candidate(candidate, timeout_seconds=timeout_seconds))
            return DvdConcatSpikeResult(candidates=candidates, attempts=tuple(attempts))
        finally:
            for candidate in candidates:
                if candidate.temp_file is not None:
                    candidate.temp_file.unlink(missing_ok=True)


def _write_ffconcat(assets: tuple[MediaAsset, ...]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="privatetv-spike-dvd-",
        suffix=".ffconcat",
        delete=False,
    )
    with handle:
        handle.write("ffconcat version 1.0\n")
        for asset in assets:
            escaped = str(asset.path).replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
    return Path(handle.name)


def _concat_protocol_uri(assets: tuple[MediaAsset, ...]) -> str:
    return "concat:" + "|".join(quote(str(asset.path), safe="/") for asset in assets)


def _run_candidate(candidate: DvdConcatCandidate, *, timeout_seconds: int) -> DvdConcatAttempt:
    try:
        completed = subprocess.run(
            candidate.command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return DvdConcatAttempt(
            name=candidate.name,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            timed_out=False,
        )
    except subprocess.TimeoutExpired as exc:
        return DvdConcatAttempt(
            name=candidate.name,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            timed_out=True,
        )


def _format_seconds(value: float) -> str:
    return f"{max(0.0, value):.3f}"
