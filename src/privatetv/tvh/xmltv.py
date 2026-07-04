from __future__ import annotations

from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

from privatetv.config import AppSettings
from privatetv.domain.models import ScheduleEntry
from privatetv.util.time import to_xmltv_time


def render_empty_xmltv(settings: AppSettings) -> str:
    return render_xmltv(settings, [])


def render_xmltv(settings: AppSettings, entries: list[ScheduleEntry]) -> str:
    """Render an XMLTV document for the configured PrivateTV channel."""
    tv = Element(
        "tv",
        {
            "generator-info-name": "PrivateTV",
            "generator-info-url": settings.server.public_base_url,
        },
    )
    channel = SubElement(tv, "channel", {"id": settings.channel.id})
    display_name = SubElement(channel, "display-name", {"lang": settings.channel.language})
    display_name.text = settings.channel.name
    if settings.channel.icon:
        SubElement(channel, "icon", {"src": settings.channel.icon})

    for entry in sorted(entries, key=lambda item: (item.start_time, item.id or 0)):
        _validate_entry(settings, entry)
        duration_seconds = max(0, int((entry.end_time - entry.start_time).total_seconds()))
        programme = SubElement(
            tv,
            "programme",
            {
                "start": to_xmltv_time(entry.start_time, settings.schedule.zoneinfo),
                "stop": to_xmltv_time(entry.end_time, settings.schedule.zoneinfo),
                "channel": entry.channel_id,
            },
        )
        title = SubElement(programme, "title", {"lang": settings.channel.language})
        title.text = entry.title
        if entry.description:
            desc = SubElement(programme, "desc", {"lang": settings.channel.language})
            desc.text = entry.description
        SubElement(programme, "category", {"lang": "en"}).text = "Movie"
        SubElement(programme, "length", {"units": "seconds"}).text = str(duration_seconds)

    return _serialize_pretty_xml(tv)


def _validate_entry(settings: AppSettings, entry: ScheduleEntry) -> None:
    if entry.channel_id != settings.channel.id:
        raise ValueError(
            f"Schedule entry channel {entry.channel_id!r} does not match configured channel "
            f"{settings.channel.id!r}"
        )
    if entry.start_time.tzinfo is None or entry.end_time.tzinfo is None:
        raise ValueError("XMLTV programme times must be timezone-aware")
    if entry.end_time <= entry.start_time:
        raise ValueError("XMLTV programme end time must be after start time")


def _serialize_pretty_xml(element: Element) -> str:
    rough = tostring(element, encoding="utf-8", short_empty_elements=True)
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="UTF-8")
    return pretty.decode("utf-8")
