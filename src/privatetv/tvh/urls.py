from __future__ import annotations

from privatetv.config import AppSettings


def public_url(settings: AppSettings, path: str) -> str:
    """Return a stable public URL for a PrivateTV HTTP endpoint."""
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{settings.server.public_base_url}{normalized_path}"


def stream_url(settings: AppSettings) -> str:
    return public_url(settings, "/stream/main.ts")


def hazard_stream_url(settings: AppSettings) -> str:
    return public_url(settings, "/stream/hazard.ts")


def playlist_url(settings: AppSettings) -> str:
    return public_url(settings, "/playlist.m3u")


def xmltv_url(settings: AppSettings) -> str:
    return public_url(settings, "/xmltv.xml")
