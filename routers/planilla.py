from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from routers.contrato import contrato_enviado

router = APIRouter()

_SQL_RESERVA = """
SELECT
    IdReserva,
    IdCliente,
    NombreReserva,
    Contrato,
    Empresa,
    MATRICULA,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS NombreCliente,
    [Fecha Salida]            AS FechaSalida,
    [Horario Salida]          AS HorarioSalida,
    [Lugar Salida]            AS LugarSalida,
    [Sucursales.Sucursal]     AS SucursalSalida,
    [Fecha Entrada]           AS FechaEntrada,
    [Horario Entrada]         AS HorarioEntrada,
    [Lugar Entrada]           AS LugarEntrada,
    [Sucursales_1.Sucursal]   AS SucursalEntrada,
    Tarifa,
    [Días]                    AS Dias,
    Km,
    [Km adicional]            AS KmAdicional,
    [Monedas.Descripcion]     AS Moneda,
    FranquiciaChoque,
    FranquiciaVuelco,
    [Status_Reserva.Descripcion] AS EstadoReserva,
    [Estado Pago]             AS EstadoPago,
    abonada                   AS Abonada,
    Adicionales,
    Observaciones
FROM dbo.vw_AppSheet_Reservas
WHERE IdReserva = ?
"""


@router.get("/{id_reserva}", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query(_SQL_RESERVA, [id_reserva])
    if not rows:
        return HTMLResponse("<h1>Reserva no encontrada</h1>", status_code=404)

    reserva = rows[0]

    # Tipo de movimiento: viene de la hoja de ruta o se detecta por fecha
    tipo = request.query_params.get("tipo", "").upper()
    if tipo not in ("IN", "OUT"):
        from datetime import date
        hoy = date.today()
        fs = reserva.get("FechaSalida")
        fe = reserva.get("FechaEntrada")
        if fs and (hasattr(fs, "date") and fs.date() == hoy or fs == hoy):
            tipo = "OUT"
        elif fe and (hasattr(fe, "date") and fe.date() == hoy or fe == hoy):
            tipo = "IN"
        else:
            tipo = "OUT"

    # Estado de cada sección OPR
    tiene_conductor   = bool(query("SELECT 1 FROM conductores  WHERE IdReserva=?", [id_reserva]))
    tiene_adicionales = bool(query("SELECT 1 FROM adicionales  WHERE IdReserva=?", [id_reserva]))
    tiene_pagos       = bool(query("SELECT 1 FROM pagos        WHERE IdReserva=?", [id_reserva]))
    tiene_entrega     = bool(query("SELECT 1 FROM entregas     WHERE IdReserva=?", [id_reserva]))
    tiene_recepcion   = bool(query("SELECT 1 FROM recepciones  WHERE IdReserva=?", [id_reserva]))
    tiene_firma       = bool(query("SELECT 1 FROM firmas       WHERE IdReserva=?", [id_reserva]))

    contrato_listo = (
        tipo == "OUT"
        and tiene_conductor
        and tiene_adicionales
        and tiene_entrega
        and tiene_firma
    )
    ya_enviado = contrato_listo and contrato_enviado(id_reserva)

    return templates.TemplateResponse("planilla.html", {
        "request":           request,
        "reserva":           reserva,
        "tipo":              tipo,
        "tiene_conductor":   tiene_conductor,
        "tiene_adicionales": tiene_adicionales,
        "tiene_pagos":       tiene_pagos,
        "tiene_entrega":     tiene_entrega,
        "tiene_recepcion":   tiene_recepcion,
        "tiene_firma":       tiene_firma,
        "contrato_listo":    contrato_listo,
        "ya_enviado":        ya_enviado,
        "ok":                request.query_params.get("ok"),
        "active_tab":        "hojas",
    })
