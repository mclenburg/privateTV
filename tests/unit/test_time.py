from datetime import datetime
from zoneinfo import ZoneInfo

from privatetv.util.time import to_xmltv_time


def test_xmltv_time_uses_summer_offset() -> None:
    zone = ZoneInfo("Europe/Berlin")
    value = datetime(2026, 7, 4, 20, 15, tzinfo=zone)

    assert to_xmltv_time(value, zone).endswith("+0200")


def test_xmltv_time_uses_winter_offset() -> None:
    zone = ZoneInfo("Europe/Berlin")
    value = datetime(2026, 12, 4, 20, 15, tzinfo=zone)

    assert to_xmltv_time(value, zone).endswith("+0100")
