from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, UTC

from aiohttp import web


@dataclass(slots=True)
class TvheadendProbeState:
    """Runtime state for the tvheadend upstream connection probe."""

    active_connections: int = 0
    total_connections: int = 0
    max_concurrent_connections: int = 0
    events: list[str] = field(default_factory=list)

    def opened(self, peer: str) -> None:
        self.active_connections += 1
        self.total_connections += 1
        self.max_concurrent_connections = max(
            self.max_concurrent_connections,
            self.active_connections,
        )
        self.events.append(f"{datetime.now(UTC).isoformat()} open {peer}")

    def closed(self, peer: str) -> None:
        self.active_connections = max(0, self.active_connections - 1)
        self.events.append(f"{datetime.now(UTC).isoformat()} close {peer}")

    def as_dict(self) -> dict[str, object]:
        return {
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "max_concurrent_connections": self.max_concurrent_connections,
            "events": list(self.events[-50:]),
        }


class TvheadendProbeServer:
    """Small manual probe server for tvheadend IPTV upstream behavior.

    It exposes a minimal M3U and a long-running MPEG-TS-like byte stream. The
    operator adds the M3U URL to tvheadend, opens the channel from multiple
    clients, and then checks whether tvheadend opened one or multiple upstream
    connections to PrivateTV.
    """

    def __init__(self, *, host: str = "127.0.0.1", port: int = 9998) -> None:
        self.host = host
        self.port = port
        self.state = TvheadendProbeState()

    def create_app(self) -> web.Application:
        app = web.Application()
        app["state"] = self.state
        app.router.add_get("/probe.m3u", self._m3u)
        app.router.add_get("/probe.ts", self._stream)
        app.router.add_get("/status", self._status)
        return app

    async def run(self) -> None:
        runner = web.AppRunner(self.create_app())
        await runner.setup()
        site = web.TCPSite(runner, host=self.host, port=self.port)
        await site.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await runner.cleanup()

    async def _m3u(self, request: web.Request) -> web.Response:
        base_url = f"http://{request.host}"
        body = (
            "#EXTM3U\n"
            "#EXTINF:-1 tvg-id=\"privatetv-upstream-probe\" "
            "tvg-name=\"PrivateTV Upstream Probe\",PrivateTV Upstream Probe\n"
            f"{base_url}/probe.ts\n"
        )
        return web.Response(text=body, content_type="audio/x-mpegurl")

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response(self.state.as_dict())

    async def _stream(self, request: web.Request) -> web.StreamResponse:
        peer = request.remote or "unknown"
        self.state.opened(peer)
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={"Content-Type": "video/MP2T", "Cache-Control": "no-store"},
        )
        await response.prepare(request)
        try:
            packet = bytes([0x47]) + b"PrivateTV upstream probe".ljust(187, b".")
            while True:
                await response.write(packet * 8)
                await asyncio.sleep(0.25)
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            raise
        finally:
            self.state.closed(peer)
        return response
