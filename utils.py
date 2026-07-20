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


# Separadores usados cuando hay más de un teléfono en el mismo campo
_SEPARADORES = re.compile(r"\s*[/;,]\s*|\s+-\s+")


def _normalizar_telefono(candidato: str) -> str:
    """Devuelve el número en formato internacional (sólo dígitos) o "".

    Ante la duda devuelve "", porque un número mal armado abre un chat de
    WhatsApp con un desconocido y eso es peor que no ofrecer el botón.
    """
    internacional = "+" in candidato
    d = re.sub(r"\D", "", candidato)
    if not d:
        return ""

    # Ya trae código de país explícito
    if internacional:
        return d if 8 <= len(d) <= 15 and not d.startswith("0") else ""

    # Argentina con código de país pero sin el 9 de celular
    if d.startswith("549") and len(d) == 13:
        return d
    if d.startswith("54") and len(d) == 12:
        return "549" + d[2:]

    d = d.lstrip("0")

    # Formato nacional con el 15 intercalado: área (2-4 díg) + 15 + abonado
    if len(d) == 12:
        for a in (2, 3, 4):
            if d[a:a + 2] == "15":
                d = d[:a] + d[a + 2:]
                break

    # Área + abonado siempre suman 10 dígitos en Argentina
    return "549" + d if len(d) == 10 else ""


def whatsapp_link(telefono) -> str:
    """URL de wa.me para el teléfono, o "" si no se puede normalizar con certeza."""
    raw = (telefono or "").strip()
    if not raw:
        return ""
    for parte in _SEPARADORES.split(raw):
        num = _normalizar_telefono(parte)
        if num:
            return "https://wa.me/" + num
    return ""


def simbolo_moneda(moneda: str) -> str:
    m = (moneda or "").strip().lower()
    if "dolar" in m or "usd" in m or "dollar" in m:
        return "US$"
    return "$"


def fmt_num(val) -> str:
    """Número sin decimales y sin símbolo de moneda (cuando el template ya tiene el $)."""
    if val is None or val == "":
        return ""
    try:
        return f"{int(round(float(val))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(val)


def fmt_importe(val, moneda: str = "Pesos") -> str:
    """Formatea un importe sin decimales con símbolo de moneda. Ej: $ 483.360"""
    if val is None or val == "":
        return ""
    try:
        amount = int(round(float(val)))
        formatted = f"{amount:,}".replace(",", ".")   # formato argentino
        return f"{simbolo_moneda(moneda)} {formatted}"
    except (ValueError, TypeError):
        return str(val)


def ahora_arg() -> datetime:
    return datetime.now(_TZ)


def hoy_arg() -> date:
    return ahora_arg().date()


def rango_hojas_ruta() -> tuple[str, str]:
    """Devuelve (desde, hasta) en isoformat, igual que la lista de hojas de ruta."""
    hoy = hoy_arg()
    return (hoy - timedelta(days=5)).isoformat(), (hoy + timedelta(days=15)).isoformat()
