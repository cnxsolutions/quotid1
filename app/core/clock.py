from datetime import date, datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")


def today() -> date:
    return datetime.now(PARIS).date()
