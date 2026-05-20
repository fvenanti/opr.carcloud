from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from utils import hoy_arg

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_TODOS = f"""
SELECT
    v.MATRICULA,
    v.Marca,
    v.Modelo,
    v.[Estado_Vehículo]  AS Estado,
    v.Sucursal,
    v.COMBUSTIBLE        AS Combustible,
    v.UBICACION          AS Ubicacion,
    v.Categoría          AS Categoria,
    r.IdReserva,
    r.[Sucursales.Sucursal]                                                         AS SucursalReserva,
    ISNULL(r.Apellido,'') + CASE WHEN r.Nombre IS NOT NULL THEN ', ' + r.Nombre ELSE '' END AS Cliente
FROM dbo.vw_AppSheet_Vehiculos v
OUTER APPLY (
    SELECT TOP 1
        IdReserva,
        [Sucursales.Sucursal],
        Apellido,
        Nombre
    FROM dbo.vw_AppSheet_Reservas
    WHERE MATRICULA = v.MATRICULA
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
      AND CAST(? AS DATE)
          BETWEEN CAST([Fecha Salida] AS DATE) AND CAST([Fecha Entrada] AS DATE)
) r
ORDER BY v.Sucursal, v.MATRICULA
"""


def _agrupar(vehiculos: list[dict]) -> tuple[list, list, list]:
    alquilados, taller, disponibles = [], [], []
    for v in vehiculos:
        if v.get("IdReserva") is not None:
            if "taller" in (v.get("SucursalReserva") or "").lower():
                taller.append(v)
            else:
                alquilados.append(v)
        else:
            disponibles.append(v)
    return alquilados, taller, disponibles


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    vehiculos = query(_SQL_TODOS, [hoy_arg().isoformat()])
    alquilados, taller, disponibles = _agrupar(vehiculos)
    return templates.TemplateResponse("vehiculos_lista.html", {
        "request":     request,
        "alquilados":  alquilados,
        "taller":      taller,
        "disponibles": disponibles,
        "active_tab":  "vehiculos",
    })
