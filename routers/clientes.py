from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates

router = APIRouter()

_SQL_BUSCAR = """
SELECT TOP 60
    IdCliente,
    DNI,
    Apellido,
    Nombre,
    Mail,
    [Teléfono]              AS Telefono,
    [Licencia de Conducir Nro] AS Licencia
FROM dbo.vw_AppSheet_Clientes
WHERE
    Apellido LIKE ?
    OR Nombre LIKE ?
    OR CAST(DNI AS VARCHAR) LIKE ?
ORDER BY Apellido, Nombre
"""


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request, q: str = ""):
    clientes = []
    if q.strip():
        patron = f"%{q.strip()}%"
        clientes = query(_SQL_BUSCAR, [patron, patron, patron])
    return templates.TemplateResponse("clientes_lista.html", {
        "request":    request,
        "clientes":   clientes,
        "q":          q,
        "active_tab": "clientes",
    })
