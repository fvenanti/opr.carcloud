from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from datetime import date, timedelta

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_FECHAS = f"""
SELECT fecha, COUNT(*) AS cantidad
FROM (
    SELECT CAST([Fecha Salida] AS DATE) AS fecha
    FROM dbo.vw_AppSheet_Reservas
    WHERE CAST([Fecha Salida] AS DATE) >= ?
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
    UNION ALL
    SELECT CAST([Fecha Entrada] AS DATE) AS fecha
    FROM dbo.vw_AppSheet_Reservas
    WHERE CAST([Fecha Entrada] AS DATE) >= ?
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
) t
GROUP BY fecha
ORDER BY fecha
"""

_SQL_DIA = f"""
SELECT
    IdReserva,
    MATRICULA                AS Matricula,
    Contrato,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS NombreCliente,
    [Lugar Salida]           AS Lugar,
    [Horario Salida]         AS HoraMovimiento,
    [Sucursales.Sucursal]    AS Sucursal,
    Adicionales,
    [Status_Reserva.Descripcion] AS EstadoReserva,
    'OUT'                    AS TipoMovimiento
FROM dbo.vw_AppSheet_Reservas
WHERE CAST([Fecha Salida] AS DATE) = ?
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}

UNION ALL

SELECT
    IdReserva,
    MATRICULA                AS Matricula,
    Contrato,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS NombreCliente,
    [Lugar Entrada]          AS Lugar,
    [Horario Entrada]        AS HoraMovimiento,
    [Sucursales_1.Sucursal]  AS Sucursal,
    Adicionales,
    [Status_Reserva.Descripcion] AS EstadoReserva,
    'IN'                     AS TipoMovimiento
FROM dbo.vw_AppSheet_Reservas
WHERE CAST([Fecha Entrada] AS DATE) = ?
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}

ORDER BY Sucursal, HoraMovimiento
"""


def _agrupar_por_sucursal(movimientos: list[dict]) -> dict:
    grupos = {}
    for m in movimientos:
        s = m.get("Sucursal") or "Sin sucursal"
        grupos.setdefault(s, []).append(m)
    return grupos


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    hoy = date.today()
    desde = hoy - timedelta(days=5)
    fechas = query(_SQL_FECHAS, [desde.isoformat(), desde.isoformat()])
    return templates.TemplateResponse("hojas_ruta_lista.html", {
        "request": request,
        "fechas":  fechas,
        "active_tab": "hojas",
    })


@router.get("/{fecha}", response_class=HTMLResponse)
async def dia(request: Request, fecha: str):
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        return HTMLResponse("Fecha inválida", status_code=400)

    f = fecha
    movimientos = query(_SQL_DIA, [f, f])

    # Enriquecer con estado OPR
    ids = [m["IdReserva"] for m in movimientos]
    ids_out = [m["IdReserva"] for m in movimientos if m["TipoMovimiento"] == "OUT"]
    ids_in  = [m["IdReserva"] for m in movimientos if m["TipoMovimiento"] == "IN"]
    procesados = set()
    if ids_out:
        ph = ",".join("?" * len(ids_out))
        rows = query(f"SELECT IdReserva FROM entregas WHERE IdReserva IN ({ph})", ids_out)
        procesados |= {r["IdReserva"] for r in rows}
    if ids_in:
        ph = ",".join("?" * len(ids_in))
        rows = query(f"SELECT IdReserva FROM recepciones WHERE IdReserva IN ({ph})", ids_in)
        procesados |= {r["IdReserva"] for r in rows}

    for m in movimientos:
        m["Procesado"] = m["IdReserva"] in procesados

    grupos = _agrupar_por_sucursal(movimientos)

    return templates.TemplateResponse("hojas_ruta_dia.html", {
        "request":  request,
        "fecha":    d,
        "grupos":   grupos,
        "active_tab": "hojas",
    })
