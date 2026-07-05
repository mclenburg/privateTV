from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from urllib.parse import urlparse, unquote

from privatetv.config import AppSettings
from privatetv.domain.errors import PrivateTvError
from privatetv.domain.models import CurrentProgramme, MediaAsset, SourceKind, StreamCommand
from privatetv.streaming.provider import StreamProvider

LOGGER = logging.getLogger(__name__)
DEFAULT_CHUNK_SIZE = 64 * 1024


class StreamPreparationError(PrivateTvError):
    """Raised when PrivateTV cannot prepare an FFmpeg stream command."""


class FfmpegCommandFactory:
    """Builds FFmpeg command lines for PrivateTV media sources."""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
        *,
        concat_file: Path | None = None,
    ) -> StreamCommand:
        if programme.media.source_kind in {SourceKind.LOCAL_FILE, SourceKind.GENERATED}:
            return self._build_local_file_command(programme, assets)
        if programme.media.source_kind == SourceKind.DVD_STRUCTURE:
            if concat_file is None:
                raise StreamPreparationError("DVD streams require a concat file")
            return self._build_dvd_concat_command(programme, concat_file)
        raise StreamPreparationError(f"Unsupported stream source: {programme.media.source_kind}")

    def _build_local_file_command(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> StreamCommand:
        input_path = _primary_asset_path(programme, assets)
        return StreamCommand(
            argv=(
                str(self._settings.streaming.ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "warning",
                "-ss",
                _format_seconds(programme.offset_seconds),
                "-re",
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-f",
                self._settings.streaming.output_container,
                "pipe:1",
            ),
            seek_tolerance_seconds=self._settings.streaming.accepted_seek_tolerance_seconds,
        )

    def _build_dvd_concat_command(
        self,
        programme: CurrentProgramme,
        concat_file: Path,
    ) -> StreamCommand:
        return StreamCommand(
            argv=(
                str(self._settings.streaming.ffmpeg_path),
                "-hide_banner",
                "-loglevel",
                "warning",
                "-ss",
                _format_seconds(programme.offset_seconds),
                "-re",
                "-fflags",
                "+genpts",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c",
                "copy",
                "-f",
                self._settings.streaming.output_container,
                "pipe:1",
            ),
            seek_tolerance_seconds=self._settings.streaming.accepted_seek_tolerance_seconds,
        )


class PerClientFfmpegStreamProvider(StreamProvider):
    """Starts one FFmpeg process per connected HTTP client."""

    def __init__(self, settings: AppSettings, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._settings = settings
        self._factory = FfmpegCommandFactory(settings)
        self._chunk_size = chunk_size

    async def open_stream(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> AsyncIterator[bytes]:
        concat_file: Path | None = None
        if programme.media.source_kind == SourceKind.DVD_STRUCTURE:
            concat_file = _write_concat_file(assets)
        try:
            command = self._factory.build(programme, assets, concat_file=concat_file)
            process = await asyncio.create_subprocess_exec(
                *command.argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            LOGGER.info(
                "Started FFmpeg stream pid=%s title=%r offset=%.3fs tolerance=%ss",
                process.pid,
                programme.schedule_entry.title,
                programme.offset_seconds,
                command.seek_tolerance_seconds,
            )
            stderr_task = asyncio.create_task(_log_stderr(process))
            try:
                if process.stdout is None:
                    raise StreamPreparationError("FFmpeg stdout pipe is not available")
                while True:
                    chunk = await process.stdout.read(self._chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                await _terminate_process(process)
                await _finish_stderr_task(stderr_task)
        finally:
            if concat_file is not None:
                concat_file.unlink(missing_ok=True)


def _primary_asset_path(programme: CurrentProgramme, assets: Sequence[MediaAsset]) -> Path:
    for asset in sorted(assets, key=lambda item: item.asset_order):
        if asset.role == "primary":
            return _existing_path(asset.path)
    if assets:
        return _existing_path(sorted(assets, key=lambda item: item.asset_order)[0].path)
    parsed = urlparse(programme.media.source_uri)
    if parsed.scheme == "file":
        return _existing_path(Path(unquote(parsed.path)))
    raise StreamPreparationError(f"No streamable asset found for {programme.media.source_uri}")


def _existing_path(path: Path) -> Path:
    if not path.exists():
        raise StreamPreparationError(f"Media asset does not exist: {path}")
    if not path.is_file():
        raise StreamPreparationError(f"Media asset is not a regular file: {path}")
    return path


def _escape_ffconcat_path(path: Path) -> str:
    # FFmpeg ffconcat files use backslash escaping inside single quoted paths.
    return str(path).replace("\\", "\\\\").replace("'", "\\'")


def _write_concat_file(assets: Sequence[MediaAsset]) -> Path:
    if not assets:
        raise StreamPreparationError("DVD stream has no VOB assets")
    ordered = sorted(assets, key=lambda item: item.asset_order)
    missing = [str(asset.path) for asset in ordered if not asset.path.exists()]
    if missing:
        raise StreamPreparationError(f"DVD stream has missing VOB assets: {', '.join(missing[:3])}")
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="privatetv-dvd-",
        suffix=".ffconcat",
        delete=False,
    )
    with handle:
        handle.write("ffconcat version 1.0\n")
        for asset in ordered:
            handle.write(f"file '{_escape_ffconcat_path(asset.path)}'\n")
    return Path(handle.name)


def _format_seconds(value: float) -> str:
    return f"{max(0.0, value):.3f}"


async def _log_stderr(process: asyncio.subprocess.Process) -> None:
    if process.stderr is None:
        return
    while True:
        line = await process.stderr.readline()
        if not line:
            break
        LOGGER.warning("ffmpeg[%s]: %s", process.pid, line.decode("utf-8", errors="replace").rstrip())


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        await process.wait()
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
    except TimeoutError:
        LOGGER.warning("FFmpeg pid=%s did not terminate in time; killing", process.pid)
        process.kill()
        await process.wait()


async def _finish_stderr_task(task: asyncio.Task[None]) -> None:
    try:
        await task
    except asyncio.CancelledError:  # pragma: no cover - defensive
        raise
    except Exception:  # pragma: no cover - logging helper must never break streaming cleanup
        LOGGER.exception("Failed to finish FFmpeg stderr logger")
