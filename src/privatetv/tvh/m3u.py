from __future__ import annotations

from dataclasses import dataclass

from privatetv.config import AppSettings
from privatetv.tvh.urls import (
    channel_logo_url,
    hazard_logo_url,
    hazard_stream_url,
    stream_url,
    xmltv_url,
)


@dataclass(frozen=True, slots=True)
class PlaylistChannel:
    id: str
    name: str
    group_title: str
    url: str
    icon: str = ""


def render_m3u(settings: AppSettings) -> str:
    """Render the tvheadend IPTV channel playlist.

    PrivateTV's main channel has a stable URL and XMLTV EPG. Hazard TV is an
    optional future channel without XMLTV schedule; when enabled it is listed in
    the same M3U but handled by a separate stream endpoint.
    """
    lines = [f'#EXTM3U url-tvg="{_escape_m3u_attribute(xmltv_url(settings))}"']
    for channel in _playlist_channels(settings):
        lines.extend(_render_channel(channel))
    lines.append("")
    return "\n".join(lines)


def _playlist_channels(settings: AppSettings) -> tuple[PlaylistChannel, ...]:
    main = PlaylistChannel(
        id=settings.channel.id,
        name=settings.channel.name,
        group_title=settings.channel.group_title,
        icon=settings.channel.icon or channel_logo_url(settings),
        url=stream_url(settings),
    )
    if not settings.hazard_channel.enabled:
        return (main,)
    hazard = PlaylistChannel(
        id=settings.hazard_channel.id,
        name=settings.hazard_channel.name,
        group_title=settings.hazard_channel.group_title,
        icon=settings.hazard_channel.icon or hazard_logo_url(settings),
        url=hazard_stream_url(settings),
    )
    return (main, hazard)


def _render_channel(channel: PlaylistChannel) -> list[str]:
    attributes = {
        "tvg-id": channel.id,
        "tvg-name": channel.name,
        "group-title": channel.group_title,
    }
    if channel.icon:
        attributes["tvg-logo"] = channel.icon

    extinf_attributes = " ".join(
        f'{name}="{_escape_m3u_attribute(value)}"' for name, value in attributes.items()
    )
    return [f"#EXTINF:-1 {extinf_attributes},{channel.name}", channel.url]


def _escape_m3u_attribute(value: str) -> str:
    return str(value).replace('"', "'")
