from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates

router = APIRouter()

_SQL_TODOS = """
SELECT
    MATRICULA,
    Marca,
    Modelo,
    [Estado_Vehículo]  AS Estado,
    Sucursal,
    COMBUSTIBLE        AS Combustible,
    UBICACION          AS Ubicacion,
    Categoría          AS Categoria
FROM dbo.vw_AppSheet_Vehiculos
ORDER BY Sucursal, MATRICULA
"""


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    vehiculos = query(_SQL_TODOS)
    return templates.TemplateResponse("vehiculos_lista.html", {
        "request":    request,
        "vehiculos":  vehiculos,
        "active_tab": "vehiculos",
    })
