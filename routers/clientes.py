from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from utils import rango_hojas_ruta

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_RANGO = f"""
SELECT DISTINCT
    c.IdCliente,
    c.DNI,
    c.Apellido,
    c.Nombre,
    c.Mail,
    c.[Teléfono]               AS Telefono,
    c.[Licencia de Conducir Nro] AS Licencia
FROM dbo.vw_AppSheet_Clientes c
INNER JOIN dbo.vw_AppSheet_Reservas r ON r.IdCliente = c.IdCliente
WHERE r.[Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
  AND (
    CAST(r.[Fecha Salida] AS DATE)  BETWEEN ? AND ?
    OR CAST(r.[Fecha Entrada] AS DATE) BETWEEN ? AND ?
  )
ORDER BY c.Apellido, c.Nombre
"""

_SQL_BUSCAR = f"""
SELECT DISTINCT
    c.IdCliente,
    c.DNI,
    c.Apellido,
    c.Nombre,
    c.Mail,
    c.[Teléfono]               AS Telefono,
    c.[Licencia de Conducir Nro] AS Licencia
FROM dbo.vw_AppSheet_Clientes c
INNER JOIN dbo.vw_AppSheet_Reservas r ON r.IdCliente = c.IdCliente
WHERE r.[Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
  AND (
    CAST(r.[Fecha Salida] AS DATE)  BETWEEN ? AND ?
    OR CAST(r.[Fecha Entrada] AS DATE) BETWEEN ? AND ?
  )
  AND (
    c.Apellido LIKE ?
    OR c.Nombre LIKE ?
    OR CAST(c.DNI AS VARCHAR) LIKE ?
  )
ORDER BY c.Apellido, c.Nombre
"""


_SQL_POR_ID = """
SELECT
    c.IdCliente,
    c.DNI,
    c.Apellido,
    c.Nombre,
    c.Mail,
    c.[Teléfono]               AS Telefono,
    c.[Licencia de Conducir Nro] AS Licencia
FROM dbo.vw_AppSheet_Clientes c
WHERE c.IdCliente = ?
"""

@router.get("/", response_class=HTMLResponse)
async def lista(request: Request, q: str = "", id_cliente: int = 0):
    desde, hasta = rango_hojas_ruta()
    if id_cliente:
        clientes = query(_SQL_POR_ID, [id_cliente])
    elif q.strip():
        patron = f"%{q.strip()}%"
        clientes = query(_SQL_BUSCAR, [desde, hasta, desde, hasta, patron, patron, patron])
    else:
        clientes = query(_SQL_RANGO, [desde, hasta, desde, hasta])

    return templates.TemplateResponse("clientes_lista.html", {
        "request":    request,
        "clientes":   clientes,
        "q":          q,
        "active_tab": "clientes",
    })
