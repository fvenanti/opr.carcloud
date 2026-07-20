import re
from zoneinfo import ZoneInfo
from datetime import datetime, date, timedelta

_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Patente Mercosur guardada sin la "A" inicial: 'C 570 LM' == AC570LM
_PATENTE_SIN_A = re.compile(r"^[A-Za-z] \d{3} [A-Za-z]{2}$")


def matricula_display(matricula) -> str:
    """Patente como se muestra al usuario.

    El sistema legacy guarda las patentes Mercosur sin la "A" inicial, así que
    hay que reponerla. Las patentes viejas ('NLO 253') ya vienen completas y no
    llevan prefijo.
    """
    m = (matricula or "").strip()
    return "A" + m if _PATENTE_SIN_A.match(m) else m


def ahora_arg() -> datetime:
    return datetime.now(_TZ)


def hoy_arg() -> date:
    return ahora_arg().date()


def rango_hojas_ruta() -> tuple[str, str]:
    """Devuelve (desde, hasta) en isoformat, igual que la lista de hojas de ruta."""
    hoy = hoy_arg()
    return (hoy - timedelta(days=5)).isoformat(), (hoy + timedelta(days=15)).isoformat()
