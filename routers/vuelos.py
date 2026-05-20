import os, time, logging
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from database import query

log = logging.getLogger(__name__)
router = APIRouter()

AERODATABOX_KEY = os.environ.get("AERODATABOX_KEY", "")
_CACHE: dict[tuple, tuple] = {}   # (numero, fecha) -> (timestamp, data)
_CACHE_TTL = 600                   # 10 min, igual que CarCloud


def _cached(numero: str, fecha: str):
    key = (numero.upper(), fecha)
    if key in _CACHE:
        ts, data = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return data, True
    return None, False


def _store(numero: str, fecha: str, data):
    _CACHE[(numero.upper(), fecha)] = (time.time(), data)


@router.get("/{id_reserva}/vuelo")
async def estado_vuelo(id_reserva: int, tipo: str = "OUT"):
    # Número de vuelo desde dbo.alquileres
    vuelo_rows = query(
        "SELECT VueloSalida, VueloEntrada FROM dbo.alquileres WHERE IdReserva = ?",
        [id_reserva],
    )
    if not vuelo_rows:
        return JSONResponse({"error": "Sin datos de vuelo"}, status_code=404)

    numero = (
        (vuelo_rows[0].get("VueloSalida") or "") if tipo == "OUT"
        else (vuelo_rows[0].get("VueloEntrada") or "")
    ).strip()
    if not numero:
        return JSONResponse({"error": "Sin número de vuelo cargado"}, status_code=404)

    # Fecha del movimiento desde la vista
    res_rows = query(
        "SELECT [Fecha Salida] AS FS, [Fecha Entrada] AS FE "
        "FROM dbo.vw_AppSheet_Reservas WHERE IdReserva = ?",
        [id_reserva],
    )
    fecha_dt = (res_rows[0]["FS"] if tipo == "OUT" else res_rows[0]["FE"]) if res_rows else None
    if fecha_dt and hasattr(fecha_dt, "date"):
        fecha = fecha_dt.date().isoformat()
    elif fecha_dt:
        fecha = str(fecha_dt)[:10]
    else:
        from utils import hoy_arg
        fecha = hoy_arg().isoformat()

    # Cache hit
    cached, hit = _cached(numero, fecha)
    if hit:
        return JSONResponse({"vuelo": numero, "fecha": fecha, "data": cached, "cached": True})

    if not AERODATABOX_KEY:
        return JSONResponse({"error": "API key no configurada"}, status_code=500)

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"https://aerodatabox.p.rapidapi.com/flights/number/{numero}/{fecha}",
                headers={
                    "X-RapidAPI-Key":  AERODATABOX_KEY,
                    "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com",
                },
            )
        arr = r.json()
        data = arr[0] if arr else None
        _store(numero, fecha, data)
        if not data:
            return JSONResponse({"error": "Vuelo no encontrado"}, status_code=404)
        return JSONResponse({"vuelo": numero, "fecha": fecha, "data": data})
    except Exception as e:
        log.error("AeroDataBox error para %s %s: %s", numero, fecha, e)
        return JSONResponse({"error": "Error al consultar AeroDataBox"}, status_code=500)
