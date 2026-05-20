from zoneinfo import ZoneInfo
from datetime import datetime, date

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_arg() -> datetime:
    return datetime.now(_TZ)


def hoy_arg() -> date:
    return ahora_arg().date()
