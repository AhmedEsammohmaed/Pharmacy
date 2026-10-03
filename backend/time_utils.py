from datetime import date, datetime
from zoneinfo import ZoneInfo

from backend.config import get_settings


def business_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().business_timezone)


def business_today() -> date:
    return datetime.now(business_timezone()).date()
