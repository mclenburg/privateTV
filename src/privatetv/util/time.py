from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

XMLTV_TIME_FORMAT = "%Y%m%d%H%M%S %z"


def now_in_zone(zone: ZoneInfo) -> datetime:
    return datetime.now(tz=zone)


def to_xmltv_time(value: datetime, zone: ZoneInfo) -> str:
    """Format a datetime for XMLTV with a dynamic timezone offset.

    Europe/Berlin is +0200 in summer and +0100 in winter. We therefore never
    hard-code the offset; the supplied ZoneInfo decides it for the concrete date.
    """
    return value.astimezone(zone).strftime(XMLTV_TIME_FORMAT)
