from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates

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
    CASE WHEN EXISTS (
        SELECT 1 FROM dbo.vw_AppSheet_Reservas r
        WHERE r.MATRICULA = v.MATRICULA
          AND r.[Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
          AND CAST(GETDATE() AS DATE)
              BETWEEN CAST(r.[Fecha Salida] AS DATE) AND CAST(r.[Fecha Entrada] AS DATE)
    ) THEN 1 ELSE 0 END AS TieneReservaHoy
FROM dbo.vw_AppSheet_Vehiculos v
ORDER BY v.Sucursal, v.MATRICULA
"""


def _agrupar(vehiculos: list[dict]) -> tuple[list, list, list]:
    alquilados, taller, disponibles = [], [], []
    for v in vehiculos:
        if v.get("TieneReservaHoy"):
            if "taller" in (v.get("Sucursal") or "").lower():
                taller.append(v)
            else:
                alquilados.append(v)
        else:
            disponibles.append(v)
    return alquilados, taller, disponibles


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    vehiculos = query(_SQL_TODOS)
    alquilados, taller, disponibles = _agrupar(vehiculos)
    return templates.TemplateResponse("vehiculos_lista.html", {
        "request":     request,
        "alquilados":  alquilados,
        "taller":      taller,
        "disponibles": disponibles,
        "active_tab":  "vehiculos",
    })
