import os
from collections import defaultdict
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from datetime import date, timedelta
from utils import hoy_arg
from routers.finalizar import flag_path

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_FECHAS = f"""
SELECT fecha, COUNT(*) AS cantidad
FROM (
    SELECT CAST([Fecha Salida] AS DATE) AS fecha
    FROM dbo.vw_AppSheet_Reservas
    WHERE CAST([Fecha Salida] AS DATE) BETWEEN ? AND ?
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
    UNION ALL
    SELECT CAST([Fecha Entrada] AS DATE) AS fecha
    FROM dbo.vw_AppSheet_Reservas
    WHERE CAST([Fecha Entrada] AS DATE) BETWEEN ? AND ?
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
) t
GROUP BY fecha
ORDER BY fecha
"""

_SQL_MOV_RANGO = f"""
SELECT
    IdReserva,
    [Status_Reserva.Descripcion] AS EstadoReserva,
    'OUT'                         AS TipoMovimiento,
    CAST([Fecha Salida] AS DATE)  AS FechaMovimiento
FROM dbo.vw_AppSheet_Reservas
WHERE CAST([Fecha Salida] AS DATE) BETWEEN ? AND ?
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
UNION ALL
SELECT
    IdReserva,
    [Status_Reserva.Descripcion],
    'IN',
    CAST([Fecha Entrada] AS DATE)
FROM dbo.vw_AppSheet_Reservas
WHERE CAST([Fecha Entrada] AS DATE) BETWEEN ? AND ?
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
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


def _to_date(v):
    return v.date() if hasattr(v, "date") else v


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    hoy = hoy_arg()
    desde = hoy - timedelta(days=5)
    hasta = hoy + timedelta(days=15)
    fechas = query(_SQL_FECHAS, [desde.isoformat(), hasta.isoformat(),
                                 desde.isoformat(), hasta.isoformat()])

    # Calcular procesados por día para el rango pasado + hoy
    mov = query(_SQL_MOV_RANGO, [desde.isoformat(), hoy.isoformat(),
                                  desde.isoformat(), hoy.isoformat()])

    _estados_out = {"efectiva", "finalizada", "finalizado"}
    _estados_in  = {"finalizada", "finalizado"}
    ids_out = [m["IdReserva"] for m in mov if m["TipoMovimiento"] == "OUT"]
    ids_in  = [m["IdReserva"] for m in mov if m["TipoMovimiento"] == "IN"]
    proc_set = set()

    mail_ids = set()
    if ids_out:
        ph = ",".join("?" * len(ids_out))
        rows = query(f"SELECT IdReserva FROM opr.mails_enviados WHERE IdReserva IN ({ph})", ids_out)
        mail_ids = {r["IdReserva"] for r in rows}

    for m in mov:
        id_r  = m["IdReserva"]
        tipo  = m["TipoMovimiento"]
        estado = (m.get("EstadoReserva") or "").strip().lower()
        if tipo == "OUT":
            if id_r in mail_ids or estado in _estados_out:
                proc_set.add((id_r, "OUT"))
        else:
            if os.path.isfile(flag_path(id_r)) or estado in _estados_in:
                proc_set.add((id_r, "IN"))

    dia_proc = defaultdict(int)
    for m in mov:
        if (m["IdReserva"], m["TipoMovimiento"]) in proc_set:
            dia_proc[_to_date(m["FechaMovimiento"])] += 1

    for fila in fechas:
        fd = _to_date(fila["fecha"])
        fila["procesados"] = dia_proc[fd] if fd <= hoy else None

    return templates.TemplateResponse("hojas_ruta_lista.html", {
        "request":    request,
        "fechas":     fechas,
        "hoy":        hoy,
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
    ids_out = [m["IdReserva"] for m in movimientos if m["TipoMovimiento"] == "OUT"]
    procesados = set()

    _estados_out = {"efectiva", "finalizada", "finalizado"}
    _estados_in  = {"finalizada", "finalizado"}

    mail_ids = set()
    if ids_out:
        ph = ",".join("?" * len(ids_out))
        rows = query(f"SELECT IdReserva FROM opr.mails_enviados WHERE IdReserva IN ({ph})", ids_out)
        mail_ids = {r["IdReserva"] for r in rows}

    for m in movimientos:
        id_r  = m["IdReserva"]
        tipo  = m["TipoMovimiento"]
        estado = (m.get("EstadoReserva") or "").strip().lower()
        if tipo == "OUT":
            if id_r in mail_ids or estado in _estados_out:
                procesados.add((id_r, "OUT"))
        else:
            if os.path.isfile(flag_path(id_r)) or estado in _estados_in:
                procesados.add((id_r, "IN"))

    for m in movimientos:
        m["Procesado"] = (m["IdReserva"], m["TipoMovimiento"]) in procesados

    grupos = _agrupar_por_sucursal(movimientos)

    return templates.TemplateResponse("hojas_ruta_dia.html", {
        "request":  request,
        "fecha":    d,
        "grupos":   grupos,
        "active_tab": "hojas",
    })
