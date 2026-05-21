import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from database import query, execute, execute_scalar
from shared_templates import templates
from utils import ahora_arg

log = logging.getLogger(__name__)
router = APIRouter()

_TIPOS  = ["Clásico", "Completo", "Detailing"]
_ORIGEN = ["Manual", "Post-reserva", "Turno programado"]

_CHECKS = {
    "CheckLiquidos": "Líquidos",
    "CheckAceite":   "Aceite",
    "CheckAC":       "Aire Acondicionado",
    "CheckCal":      "Calibrado de ruedas",
    "CheckLuces":    "Luces",
}


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    pendientes = query("""
        SELECT TOP 50
            l.Id, l.Patente, l.TipoLavado, l.Estado, l.Prioridad,
            l.FechaHoraCreacion, l.FechaHoraInicio,
            l.ResponsableCreacion,
            mo.Modelo, m.Marca
        FROM opr.lavados l
        LEFT JOIN dbo.Autos       a  ON a.MATRICULA = l.Patente
        LEFT JOIN dbo.tbl_Modelos mo ON mo.Id = a.IdModelo
        LEFT JOIN dbo.tbl_marcas  m  ON m.Id  = a.IdMarca
        WHERE l.Estado IN ('Pendiente', 'En proceso')
        ORDER BY ISNULL(l.Prioridad, 999), l.FechaHoraCreacion
    """)
    return templates.TemplateResponse("lavados_lista.html", {
        "request":    request,
        "pendientes": pendientes,
        "active_tab": "vehiculos",
    })


@router.get("/nuevo/{patente}", response_class=HTMLResponse)
async def form_nuevo(request: Request, patente: str):
    veh = query("""
        SELECT v.MATRICULA, mo.Modelo, m.Marca
        FROM dbo.vw_AppSheet_Vehiculos v
        LEFT JOIN dbo.Autos       a  ON a.MATRICULA = v.MATRICULA
        LEFT JOIN dbo.tbl_Modelos mo ON mo.Id = a.IdModelo
        LEFT JOIN dbo.tbl_marcas  m  ON m.Id  = a.IdMarca
        WHERE v.MATRICULA = ?
    """, [patente])
    return templates.TemplateResponse("lavado_form.html", {
        "request": request,
        "patente": patente,
        "veh":     veh[0] if veh else {},
        "tipos":   _TIPOS,
        "origenes": _ORIGEN,
    })


@router.post("/nuevo/{patente}")
async def crear(request: Request, patente: str):
    form = dict(await request.form())
    email_op = request.session.get("user_email", "")
    tipo    = form.get("tipo_lavado", "Clásico")
    origen  = form.get("origen", "Manual")

    nuevo_id = execute_scalar("""
        INSERT INTO opr.lavados (Patente, TipoLavado, Origen, ResponsableCreacion)
        OUTPUT INSERTED.Id
        VALUES (?, ?, ?, ?)
    """, [patente, tipo, origen, email_op])

    return RedirectResponse(f"/lavados/{nuevo_id}", status_code=303)


@router.get("/{id_lavado}", response_class=HTMLResponse)
async def detalle(request: Request, id_lavado: int):
    rows = query("SELECT * FROM opr.lavados WHERE Id = ?", [id_lavado])
    if not rows:
        return HTMLResponse("Lavado no encontrado", status_code=404)
    lavado = rows[0]
    checks_completados = sum(1 for k in _CHECKS if lavado.get(k))
    return templates.TemplateResponse("lavado_detalle.html", {
        "request":           request,
        "lavado":            lavado,
        "checks":            _CHECKS,
        "checks_completados": checks_completados,
        "total_checks":      len(_CHECKS),
    })


@router.post("/{id_lavado}/iniciar")
async def iniciar(id_lavado: int):
    execute("""
        UPDATE opr.lavados SET Estado = 'En proceso', FechaHoraInicio = GETDATE()
        WHERE Id = ? AND Estado = 'Pendiente'
    """, [id_lavado])
    return RedirectResponse(f"/lavados/{id_lavado}", status_code=303)


@router.post("/{id_lavado}/check")
async def toggle_check(id_lavado: int, request: Request):
    body = await request.json()
    campo = body.get("campo", "")
    valor = 1 if body.get("valor") else 0
    if campo not in _CHECKS:
        return JSONResponse({"error": "Campo inválido"}, status_code=400)
    execute(f"UPDATE opr.lavados SET {campo} = ? WHERE Id = ?", [valor, id_lavado])
    return JSONResponse({"campo": campo, "valor": valor})


@router.post("/{id_lavado}/finalizar")
async def finalizar(id_lavado: int):
    execute("""
        UPDATE opr.lavados SET Estado = 'Finalizado', FechaHoraFin = GETDATE()
        WHERE Id = ? AND Estado = 'En proceso'
    """, [id_lavado])
    return RedirectResponse(f"/vehiculos/", status_code=303)
