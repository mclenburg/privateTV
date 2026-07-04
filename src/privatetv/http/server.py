from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import timedelta
from http import HTTPStatus
from importlib import resources
from pathlib import Path

from aiohttp import web

from privatetv.config import AppSettings
from privatetv.db import MediaRepository, ScheduleRepository, connect_database, initialize_database
from privatetv.domain.errors import NoCurrentProgrammeError, StreamLimitExceededError
from privatetv.domain.models import CurrentProgramme, MediaAsset, ScanStatus, SourceKind
from privatetv.hazard import HazardRandomStreamProvider, HazardSelectionError
from privatetv.http.keys import (
    CONFIG_PATH_KEY,
    HAZARD_PROVIDER_KEY,
    RUNTIME_KEY,
    SETTINGS_KEY,
    STREAM_PROVIDER_KEY,
    STREAM_STATE_KEY,
)
from privatetv.schedule import ScheduleMaintainer, resolve_current_programme
from privatetv.streaming import PerClientFfmpegStreamProvider, StreamProvider
from privatetv.streaming.ffmpeg import StreamPreparationError
from privatetv.tvh import render_empty_xmltv, render_m3u, render_xmltv
from privatetv.util.time import now_in_zone
from privatetv.web.config_ui import add_media_directory, browse_directories, save_config, show_config

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamState:
    """Runtime HTTP stream state shared by all PrivateTV channels."""

    max_parallel_streams: int
    active_streams: int = 0
    _semaphore: object = field(init=False, repr=False)

    def __post_init__(self) -> None:
        import asyncio

        self._semaphore = asyncio.Semaphore(self.max_parallel_streams)

    async def acquire(self) -> None:
        semaphore = self._semaphore
        if semaphore.locked():
            raise StreamLimitExceededError("Maximum number of parallel streams reached")
        await semaphore.acquire()
        self.active_streams += 1

    def release(self) -> None:
        semaphore = self._semaphore
        self.active_streams = max(0, self.active_streams - 1)
        semaphore.release()


def create_app(
    settings: AppSettings,
    stream_provider: StreamProvider | None = None,
    hazard_provider: HazardRandomStreamProvider | None = None,
    config_path: object | None = None,
) -> web.Application:
    """Create the aiohttp application used by the PrivateTV service."""
    app = web.Application()
    provider = stream_provider or PerClientFfmpegStreamProvider(settings)
    app[RUNTIME_KEY] = {
        "settings": settings,
        "stream_state": StreamState(settings.streaming.max_parallel_streams),
        "stream_provider": provider,
        "hazard_provider": hazard_provider or HazardRandomStreamProvider(settings, provider),
    }
    # Keep initial legacy app keys for tests/extensions that may still inspect the app mapping.
    # Runtime updates mutate app[RUNTIME_KEY] instead of the started aiohttp app mapping.
    app[SETTINGS_KEY] = settings
    app[STREAM_STATE_KEY] = app[RUNTIME_KEY]["stream_state"]
    app[STREAM_PROVIDER_KEY] = provider
    app[HAZARD_PROVIDER_KEY] = app[RUNTIME_KEY]["hazard_provider"]
    if config_path is not None:
        app[CONFIG_PATH_KEY] = Path(config_path)
    app.on_startup.append(_initialize_database)

    app.router.add_get("/health", health)
    app.router.add_get("/playlist.m3u", playlist)
    app.router.add_get("/xmltv.xml", xmltv)
    app.router.add_get("/logos/privatetv.png", privatetv_logo)
    app.router.add_get("/logos/hazardtv.png", hazardtv_logo)
    app.router.add_get("/stream/main.ts", stream)
    app.router.add_get("/stream/hazard.ts", hazard_stream)
    app.router.add_get("/config", show_config)
    app.router.add_post("/config", save_config)
    app.router.add_get("/config/browse", browse_directories)
    app.router.add_post("/config/media-directories/add", add_media_directory)
    app.router.add_get("/api", index)
    app.router.add_get("/", show_config)
    return app


async def _initialize_database(app: web.Application) -> None:
    settings = _settings(app)
    initialize_database(settings.database.path)
    now = now_in_zone(settings.schedule.zoneinfo).replace(microsecond=0)
    with connect_database(settings.database.path) as connection:
        result = ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
    LOGGER.info(
        "PrivateTV HTTP service initialized database at %s; schedule_until=%s; entries_added=%s",
        settings.database.path,
        result.schedule_until_after.isoformat() if result.schedule_until_after else None,
        result.inserted_entries,
    )


async def index(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    payload = {
        "service": "PrivateTV",
        "channel": {
            "id": settings.channel.id,
            "name": settings.channel.name,
        },
        "hazard_channel": {
            "enabled": settings.hazard_channel.enabled,
            "id": settings.hazard_channel.id,
            "name": settings.hazard_channel.name,
        },
        "endpoints": {
            "health": "/health",
            "playlist": "/playlist.m3u",
            "xmltv": "/xmltv.xml",
            "stream": "/stream/main.ts",
            "hazard_stream": "/stream/hazard.ts",
            "channel_logo": "/logos/privatetv.png",
            "hazard_logo": "/logos/hazardtv.png",
        },
    }
    return web.json_response(payload)


async def health(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    state = _stream_state(request.app)
    now = now_in_zone(settings.schedule.zoneinfo).replace(microsecond=0)

    try:
        with connect_database(settings.database.path) as connection:
            repository = ScheduleRepository(connection)
            schedule_until = repository.get_schedule_end(settings.channel.id)
            current_entries = repository.list_entries_with_media(
                settings.channel.id,
                start_at=now - timedelta(days=1),
                end_at=now + timedelta(days=1),
            )
        current = resolve_current_programme(current_entries, now=now)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        LOGGER.exception("Health check failed")
        return web.json_response(
            {
                "status": "error",
                "service": "PrivateTV",
                "message": str(exc),
            },
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    required_until = now + timedelta(days=settings.schedule.minimum_days_ahead)
    target_until = now + timedelta(days=settings.schedule.days_ahead)
    schedule_days_remaining = (
        max(0.0, (schedule_until - now).total_seconds() / 86400) if schedule_until else 0.0
    )
    schedule_needs_extension = schedule_until is None or schedule_until < required_until

    status = "ok"
    if schedule_needs_extension:
        status = "degraded"

    payload = {
        "status": status,
        "service": "PrivateTV",
        "channel_id": settings.channel.id,
        "channel_name": settings.channel.name,
        "hazard_channel_enabled": settings.hazard_channel.enabled,
        "now": now.isoformat(),
        "active_streams": state.active_streams,
        "max_parallel_streams": state.max_parallel_streams,
        "schedule_until": schedule_until.isoformat() if schedule_until else None,
        "schedule_required_until": required_until.isoformat(),
        "schedule_target_until": target_until.isoformat(),
        "schedule_days_remaining": round(schedule_days_remaining, 3),
        "schedule_minimum_days_ahead": settings.schedule.minimum_days_ahead,
        "schedule_target_days_ahead": settings.schedule.days_ahead,
        "schedule_needs_extension": schedule_needs_extension,
        "current_programme": _current_programme_payload(current),
    }
    return web.json_response(payload, status=HTTPStatus.OK)


async def playlist(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    return web.Response(
        text=render_m3u(settings),
        content_type="audio/x-mpegurl",
        charset="utf-8",
        headers={"Cache-Control": "no-cache"},
    )


async def xmltv(request: web.Request) -> web.Response:
    settings = _settings(request.app)
    now = now_in_zone(settings.schedule.zoneinfo).replace(microsecond=0)
    end_at = now + timedelta(days=settings.schedule.days_ahead)

    with connect_database(settings.database.path) as connection:
        ScheduleMaintainer(settings).ensure_schedule(connection, now=now)
        entries = ScheduleRepository(connection).list_entries(
            settings.channel.id,
            start_at=now,
            end_at=end_at,
        )

    body = render_xmltv(settings, entries) if entries else render_empty_xmltv(settings)
    return web.Response(
        text=body,
        content_type="application/xml",
        charset="utf-8",
        headers={"Cache-Control": "no-cache"},
    )


async def privatetv_logo(request: web.Request) -> web.Response:
    return _builtin_logo_response("privatetv.png")


async def hazardtv_logo(request: web.Request) -> web.Response:
    return _builtin_logo_response("hazardtv.png")


def _builtin_logo_response(filename: str) -> web.Response:
    resource = resources.files("privatetv").joinpath(f"assets/logos/{filename}")
    if not resource.is_file():  # pragma: no cover - packaging/runtime guard
        raise web.HTTPNotFound(text=f"Built-in logo not found: {filename}")
    body = resource.read_bytes()
    return web.Response(
        body=body,
        content_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def hazard_stream(request: web.Request) -> web.StreamResponse:
    settings = _settings(request.app)
    if not settings.hazard_channel.enabled:
        return web.json_response(
            {
                "status": "hazard_disabled",
                "message": "Hazard TV is disabled in the configuration.",
            },
            status=HTTPStatus.NOT_FOUND,
        )

    if not _hazard_has_playable_media(settings):
        return web.json_response(
            {
                "status": "hazard_no_media",
                "message": "Hazard TV has no playable media items",
            },
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    state = _stream_state(request.app)
    try:
        await state.acquire()
    except StreamLimitExceededError as exc:
        return web.json_response(
            {"status": "stream_limit_exceeded", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    try:
        provider = _hazard_provider(request.app)
        return await _stream_iterator_response(
            request,
            provider.open_stream(),
            headers={
                "Content-Type": "video/MP2T",
                "Cache-Control": "no-cache",
                "X-PrivateTV-Channel": settings.hazard_channel.id,
                "X-PrivateTV-Random": "true",
            },
        )
    except HazardSelectionError as exc:
        return web.json_response(
            {"status": "hazard_no_media", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except StreamPreparationError as exc:
        return web.json_response(
            {"status": "stream_unavailable", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except Exception as exc:  # pragma: no cover - runtime safety guard
        LOGGER.exception("Failed to stream Hazard TV")
        return web.json_response(
            {"status": "stream_failed", "message": str(exc)},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    finally:
        state.release()


async def stream(request: web.Request) -> web.StreamResponse:
    settings = _settings(request.app)
    state = _stream_state(request.app)
    try:
        await state.acquire()
    except StreamLimitExceededError as exc:
        return web.json_response(
            {"status": "stream_limit_exceeded", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )

    try:
        programme, assets = _resolve_stream_target(settings)
        provider = _stream_provider(request.app)
        return await _stream_iterator_response(
            request,
            provider.open_stream(programme, assets),
            headers={
                "Content-Type": "video/MP2T",
                "Cache-Control": "no-cache",
                "X-PrivateTV-Title": programme.schedule_entry.title,
                "X-PrivateTV-Offset": f"{programme.offset_seconds:.3f}",
            },
        )
    except NoCurrentProgrammeError as exc:
        return web.json_response(
            {"status": "no_current_programme", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except StreamPreparationError as exc:
        return web.json_response(
            {"status": "stream_unavailable", "message": str(exc)},
            status=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    except Exception as exc:  # pragma: no cover - runtime safety guard
        LOGGER.exception("Failed to stream channel")
        return web.json_response(
            {"status": "stream_failed", "message": str(exc)},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    finally:
        state.release()


async def _stream_iterator_response(
    request: web.Request,
    iterator: AsyncIterator[bytes],
    *,
    headers: dict[str, str],
) -> web.StreamResponse:
    """Prepare a stream only after the provider produced the first chunk.

    This catches FFmpeg startup and media-selection errors before HTTP headers are
    sent. Once a streaming response is prepared, later client disconnects or
    process failures are logged by the provider and the connection is closed.
    """
    try:
        first_chunk = await anext(iterator)
    except StopAsyncIteration:
        return web.json_response(
            {"status": "stream_empty", "message": "Stream provider produced no data"},
            status=HTTPStatus.BAD_GATEWAY,
        )

    response = web.StreamResponse(status=HTTPStatus.OK, reason="OK", headers=headers)
    try:
        await response.prepare(request)
        await response.write(first_chunk)
        async for chunk in iterator:
            await response.write(chunk)
        await response.write_eof()
        return response
    finally:
        aclose = getattr(iterator, "aclose", None)
        if aclose is not None:
            await aclose()


def _resolve_stream_target(settings: AppSettings) -> tuple[CurrentProgramme, list[MediaAsset]]:
    now = now_in_zone(settings.schedule.zoneinfo).replace(microsecond=0)
    with connect_database(settings.database.path) as connection:
        schedule_repository = ScheduleRepository(connection)
        entries = schedule_repository.list_entries_with_media(
            settings.channel.id,
            start_at=now - timedelta(days=1),
            end_at=now + timedelta(days=1),
        )
        programme = resolve_current_programme(entries, now=now)
        if programme is None:
            raise NoCurrentProgrammeError("No schedule entry exists for the current time")
        if programme.media.id is None:
            raise NoCurrentProgrammeError("Current programme media has no database id")
        if not programme.media.enabled or programme.media.scan_status != ScanStatus.OK:
            raise NoCurrentProgrammeError("Current programme media is disabled or unavailable")
        if programme.media.source_kind not in {SourceKind.LOCAL_FILE, SourceKind.DVD_STRUCTURE}:
            raise NoCurrentProgrammeError(
                f"Current programme source is not streamable: {programme.media.source_kind}"
            )
        assets = MediaRepository(connection).list_assets(programme.media.id)
    _validate_stream_assets(programme, assets)
    return programme, assets


def _validate_stream_assets(programme: CurrentProgramme, assets: list[MediaAsset]) -> None:
    if not assets:
        raise NoCurrentProgrammeError(f"No streamable assets found for {programme.media.title}")
    missing = [str(asset.path) for asset in assets if not asset.path.exists()]
    if missing:
        raise NoCurrentProgrammeError(
            f"Current programme has missing media assets: {', '.join(missing[:3])}"
        )


def _hazard_has_playable_media(settings: AppSettings) -> bool:
    with connect_database(settings.database.path) as connection:
        return bool(MediaRepository(connection).list_playable_media_items())


def _runtime(app: web.Application) -> dict:
    return app[RUNTIME_KEY]


def _settings(app: web.Application) -> AppSettings:
    return _runtime(app)["settings"]


def _stream_state(app: web.Application) -> StreamState:
    return _runtime(app)["stream_state"]


def _stream_provider(app: web.Application) -> StreamProvider:
    return _runtime(app)["stream_provider"]


def _hazard_provider(app: web.Application) -> HazardRandomStreamProvider:
    return _runtime(app)["hazard_provider"]


def _current_programme_payload(programme: CurrentProgramme | None) -> dict | None:
    if programme is None:
        return None
    return {
        "title": programme.schedule_entry.title,
        "media_source": programme.media.source_uri,
        "offset_seconds": round(programme.offset_seconds, 3),
        "start_time": programme.schedule_entry.start_time.isoformat(),
        "end_time": programme.schedule_entry.end_time.isoformat(),
    }
