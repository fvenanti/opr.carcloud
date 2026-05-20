from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from datetime import date, timedelta

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_RECIENTES = f"""
SELECT TOP 80
    IdReserva,
    MATRICULA,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS Cliente,
    CAST([Fecha Salida] AS DATE)  AS FechaSalida,
    CAST([Fecha Entrada] AS DATE) AS FechaEntrada,
    [Status_Reserva.Descripcion]  AS Estado
FROM dbo.vw_AppSheet_Reservas
WHERE CAST([Fecha Salida] AS DATE) >= ?
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
ORDER BY [Fecha Salida] DESC
"""

_SQL_BUSCAR = f"""
SELECT TOP 60
    IdReserva,
    MATRICULA,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS Cliente,
    CAST([Fecha Salida] AS DATE)  AS FechaSalida,
    CAST([Fecha Entrada] AS DATE) AS FechaEntrada,
    [Status_Reserva.Descripcion]  AS Estado
FROM dbo.vw_AppSheet_Reservas
WHERE (
    CAST(IdReserva AS VARCHAR) = ?
    OR MATRICULA LIKE ?
    OR Apellido   LIKE ?
)
  AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
ORDER BY [Fecha Salida] DESC
"""

_ESTADO_BADGE = {
    "Efectiva":                  ("bg-green-100 text-green-700",  "Efectiva"),
    "Finalizada":                ("bg-gray-100 text-gray-500",    "Finalizada"),
    "Confirmada":                ("bg-blue-100 text-blue-700",    "Confirmada"),
    "Confirmada - Faltan datos": ("bg-amber-100 text-amber-700",  "Faltan datos"),
    "A confirmar":               ("bg-orange-100 text-orange-700","A confirmar"),
}


def _enriquecer(reservas: list[dict]) -> list[dict]:
    for r in reservas:
        estado = r.get("Estado") or ""
        cls, label = _ESTADO_BADGE.get(estado, ("bg-gray-100 text-gray-500", estado))
        r["EstadoBadgeClass"] = cls
        r["EstadoLabel"] = label
    return reservas


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request, q: str = ""):
    if q.strip():
        patron = f"%{q.strip()}%"
        reservas = query(_SQL_BUSCAR, [q.strip(), patron, patron])
    else:
        desde = (date.today() - timedelta(days=5)).isoformat()
        reservas = query(_SQL_RECIENTES, [desde])

    return templates.TemplateResponse("reservas_lista.html", {
        "request":    request,
        "reservas":   _enriquecer(reservas),
        "q":          q,
        "active_tab": "reservas",
    })
