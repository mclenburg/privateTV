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
SUBSCRIBER_PUT_TIMEOUT_SECONDS = 0.25


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
        codec_args = self._codec_args()
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
                "-i",
                str(input_path),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                *codec_args,
                "-avoid_negative_ts",
                "make_zero",
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
        codec_args = self._codec_args()
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
                *codec_args,
                "-avoid_negative_ts",
                "make_zero",
                "-f",
                self._settings.streaming.output_container,
                "pipe:1",
            ),
            seek_tolerance_seconds=self._settings.streaming.accepted_seek_tolerance_seconds,
        )

    def _codec_args(self) -> tuple[str, ...]:
        if self._settings.streaming.prefer_stream_copy:
            return ("-c", "copy")
        if not self._settings.streaming.transcode_when_needed:
            return ("-c", "copy")
        return (
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-tune",
            "zerolatency",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-b:a",
            "160k",
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


class SharedLiveFfmpegStreamProvider(StreamProvider):
    """Shares one live FFmpeg process between all main-channel clients.

    This provider is intended for the linear PrivateTV main channel only. Every
    subscriber joins the same currently running MPEG-TS byte stream. Hazard TV
    deliberately keeps using ``PerClientFfmpegStreamProvider`` so each viewer can
    receive an independent random movie from the beginning.
    """

    def __init__(self, settings: AppSettings, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._settings = settings
        self._factory = FfmpegCommandFactory(settings)
        self._chunk_size = chunk_size
        self._lock = asyncio.Lock()
        self._session: _SharedFfmpegSession | None = None

    async def open_stream(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> AsyncIterator[bytes]:
        session = await self._get_or_create_session(programme, assets)
        async for chunk in session.subscribe():
            yield chunk

    async def _get_or_create_session(
        self,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
    ) -> "_SharedFfmpegSession":
        async with self._lock:
            key = _programme_key(programme)
            if self._session is None or not self._session.matches(key) or self._session.closed:
                if self._session is not None:
                    await self._session.close()
                self._session = _SharedFfmpegSession(
                    self._settings,
                    self._factory,
                    programme,
                    assets,
                    chunk_size=self._chunk_size,
                    on_closed=self._clear_session,
                )
            return self._session

    def _clear_session(self, session: "_SharedFfmpegSession") -> None:
        if self._session is session:
            self._session = None


class _SharedFfmpegSession:
    """Runtime fanout session for a single scheduled main-channel programme."""

    def __init__(
        self,
        settings: AppSettings,
        factory: FfmpegCommandFactory,
        programme: CurrentProgramme,
        assets: Sequence[MediaAsset],
        *,
        chunk_size: int,
        on_closed,
    ) -> None:
        self._settings = settings
        self._factory = factory
        self._programme = programme
        self._assets = tuple(assets)
        self._chunk_size = chunk_size
        self._on_closed = on_closed
        self._key = _programme_key(programme)
        self._subscribers: set[asyncio.Queue[bytes | None]] = set()
        self._lock = asyncio.Lock()
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._concat_file: Path | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def matches(self, key: tuple[object, ...]) -> bool:
        return self._key == key and not self._closed

    async def subscribe(self) -> AsyncIterator[bytes]:
        queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=32)
        async with self._lock:
            if self._closed:
                raise StreamPreparationError("Shared main-channel stream is already closed")
            self._subscribers.add(queue)
            await self._ensure_started()
        LOGGER.info(
            "Main channel subscriber joined shared stream title=%r subscribers=%s",
            self._programme.schedule_entry.title,
            len(self._subscribers),
        )
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            await self._unsubscribe(queue)

    async def close(self) -> None:
        async with self._lock:
            await self._close_locked()

    async def _ensure_started(self) -> None:
        if self._process is not None:
            return
        if self._programme.media.source_kind == SourceKind.DVD_STRUCTURE:
            self._concat_file = _write_concat_file(self._assets)
        command = self._factory.build(self._programme, self._assets, concat_file=self._concat_file)
        self._process = await asyncio.create_subprocess_exec(
            *command.argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        LOGGER.info(
            "Started shared FFmpeg main stream pid=%s title=%r offset=%.3fs tolerance=%ss",
            self._process.pid,
            self._programme.schedule_entry.title,
            self._programme.offset_seconds,
            command.seek_tolerance_seconds,
        )
        self._stderr_task = asyncio.create_task(_log_stderr(self._process))
        self._reader_task = asyncio.create_task(self._fanout_stdout())

    async def _fanout_stdout(self) -> None:
        process = self._process
        try:
            if process is None or process.stdout is None:
                raise StreamPreparationError("FFmpeg stdout pipe is not available")
            while True:
                chunk = await process.stdout.read(self._chunk_size)
                if not chunk:
                    break
                await self._publish(chunk)
        except asyncio.CancelledError:  # pragma: no cover - normal shutdown path
            raise
        except Exception:
            LOGGER.exception("Shared main-channel FFmpeg fanout failed")
        finally:
            await self._notify_end()
            await self.close()

    async def _publish(self, chunk: bytes) -> None:
        subscribers = tuple(self._subscribers)
        if not subscribers:
            return
        stalled: list[asyncio.Queue[bytes | None]] = []
        for queue in subscribers:
            if queue not in self._subscribers:
                continue
            try:
                await asyncio.wait_for(queue.put(chunk), timeout=SUBSCRIBER_PUT_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                stalled.append(queue)
            except RuntimeError:
                stalled.append(queue)
        for queue in stalled:
            await self._evict_subscriber(queue, reason="subscriber queue stalled")

    async def _notify_end(self) -> None:
        subscribers = tuple(self._subscribers)
        for queue in subscribers:
            _close_subscriber_queue(queue)

    async def _evict_subscriber(self, queue: asyncio.Queue[bytes | None], *, reason: str) -> None:
        async with self._lock:
            if queue not in self._subscribers:
                return
            self._subscribers.discard(queue)
            _close_subscriber_queue(queue)
            subscriber_count = len(self._subscribers)
            LOGGER.warning(
                "Evicted stalled main-channel subscriber title=%r reason=%s subscribers=%s",
                self._programme.schedule_entry.title,
                reason,
                subscriber_count,
            )
            if subscriber_count == 0:
                await self._close_locked()

    async def _unsubscribe(self, queue: asyncio.Queue[bytes | None]) -> None:
        async with self._lock:
            removed = queue in self._subscribers
            self._subscribers.discard(queue)
            subscriber_count = len(self._subscribers)
            if not removed:
                return
            LOGGER.info(
                "Main channel subscriber left shared stream title=%r subscribers=%s",
                self._programme.schedule_entry.title,
                subscriber_count,
            )
            if subscriber_count == 0:
                await self._close_locked()

    async def _close_locked(self) -> None:
        if self._closed:
            return
        self._closed = True
        reader_task = self._reader_task
        self._reader_task = None
        if reader_task is not None and reader_task is not asyncio.current_task():
            # Do not await the reader task while holding the session lock. A
            # cancelled reader runs its own cleanup path and would otherwise try
            # to re-enter close(), deadlocking the final subscriber disconnect.
            reader_task.cancel()
        process = self._process
        self._process = None
        if process is not None:
            await _terminate_process(process)
        stderr_task = self._stderr_task
        self._stderr_task = None
        if stderr_task is not None:
            await _finish_stderr_task(stderr_task)
        if self._concat_file is not None:
            self._concat_file.unlink(missing_ok=True)
            self._concat_file = None
        self._on_closed(self)


def _close_subscriber_queue(queue: asyncio.Queue[bytes | None]) -> None:
    try:
        queue.put_nowait(None)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        queue.put_nowait(None)
    except asyncio.QueueFull:  # pragma: no cover - defensive fallback
        pass


def _programme_key(programme: CurrentProgramme) -> tuple[object, ...]:
    entry = programme.schedule_entry
    return (
        entry.channel_id,
        entry.id,
        entry.media_item_id,
        entry.start_time.isoformat(),
        entry.end_time.isoformat(),
        entry.start_offset_seconds,
    )


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
