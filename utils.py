from zoneinfo import ZoneInfo
from datetime import datetime, date, timedelta

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora_arg() -> datetime:
    return datetime.now(_TZ)


def hoy_arg() -> date:
    return ahora_arg().date()


def rango_hojas_ruta() -> tuple[str, str]:
    """Devuelve (desde, hasta) en isoformat, igual que la lista de hojas de ruta."""
    hoy = hoy_arg()
    return (hoy - timedelta(days=5)).isoformat(), (hoy + timedelta(days=15)).isoformat()
