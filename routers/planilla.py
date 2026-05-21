from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from routers.finalizar import reserva_finalizada

router = APIRouter()

_SQL_RESERVA = """
SELECT
    r.IdReserva,
    r.IdCliente,
    r.NombreReserva,
    r.Contrato,
    r.Empresa,
    r.MATRICULA,
    ISNULL(r.Apellido,'') + CASE WHEN r.Nombre IS NOT NULL THEN ', ' + r.Nombre ELSE '' END AS NombreCliente,
    r.[Fecha Salida]            AS FechaSalida,
    r.[Horario Salida]          AS HorarioSalida,
    r.[Lugar Salida]            AS LugarSalida,
    r.[Sucursales.Sucursal]     AS SucursalSalida,
    r.[Fecha Entrada]           AS FechaEntrada,
    r.[Horario Entrada]         AS HorarioEntrada,
    r.[Lugar Entrada]           AS LugarEntrada,
    r.[Sucursales_1.Sucursal]   AS SucursalEntrada,
    r.Tarifa,
    r.[Días]                    AS Dias,
    r.Km,
    r.[Km adicional]            AS KmAdicional,
    r.[Monedas.Descripcion]     AS Moneda,
    r.FranquiciaChoque,
    r.FranquiciaVuelco,
    r.[Status_Reserva.Descripcion] AS EstadoReserva,
    r.[Estado Pago]             AS EstadoPago,
    r.abonada                   AS Abonada,
    r.Adicionales,
    r.Observaciones,
    r.[Observaciones 2]         AS Observaciones2,
    c.[Teléfono]                AS TelefonoCliente
FROM dbo.vw_AppSheet_Reservas r
LEFT JOIN dbo.vw_AppSheet_Clientes c ON c.IdCliente = r.IdCliente
WHERE r.IdReserva = ?
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
        from utils import hoy_arg
        hoy = hoy_arg()
        fs = reserva.get("FechaSalida")
        fe = reserva.get("FechaEntrada")
        if fs and (hasattr(fs, "date") and fs.date() == hoy or fs == hoy):
            tipo = "OUT"
        elif fe and (hasattr(fe, "date") and fe.date() == hoy or fe == hoy):
            tipo = "IN"
        else:
            tipo = "OUT"

    # Datos de cada sección OPR (una sola query por sección)
    _cond  = query("SELECT * FROM conductores  WHERE IdReserva=?", [id_reserva])
    _adic  = query("SELECT * FROM adicionales  WHERE IdReserva=?", [id_reserva])
    _pagos = query("SELECT * FROM pagos        WHERE IdReserva=? ORDER BY FechaPago, Id", [id_reserva])
    _ent   = query("SELECT * FROM entregas     WHERE IdReserva=?", [id_reserva])
    _rec   = query("SELECT * FROM recepciones  WHERE IdReserva=?", [id_reserva])
    _firma = query("SELECT * FROM firmas       WHERE IdReserva=?", [id_reserva])

    tiene_conductor   = bool(_cond)
    tiene_adicionales = bool(_adic)
    tiene_pagos       = bool(_pagos)
    tiene_entrega     = bool(_ent)
    tiene_recepcion   = bool(_rec)
    tiene_firma       = bool(_firma)

    estado = reserva.get("EstadoReserva") or ""
    mostrar_out = tipo == "OUT" and "Confirmada" in estado
    mostrar_in  = tipo == "IN"  and estado == "Efectiva"

    contrato_listo = (
        mostrar_out
        and tiene_conductor
        and tiene_adicionales
        and tiene_entrega
        and tiene_firma
    )
    try:
        _ec = query("SELECT COUNT(*) AS n FROM opr.mails_enviados WHERE IdReserva = ?", [id_reserva])
        envios_count = _ec[0]["n"] if _ec else 0
    except Exception:
        envios_count = 0

    tiene_finalizacion = reserva_finalizada(id_reserva)

    _vuelo = query("SELECT VueloSalida, VueloEntrada FROM dbo.alquileres WHERE IdReserva = ?", [id_reserva])
    vuelo_salida  = (_vuelo[0].get("VueloSalida")  or "").strip() if _vuelo else ""
    vuelo_entrada = (_vuelo[0].get("VueloEntrada") or "").strip() if _vuelo else ""
    vuelo_numero  = vuelo_salida if tipo == "OUT" else vuelo_entrada

    return templates.TemplateResponse("planilla.html", {
        "request":             request,
        "reserva":             reserva,
        "tipo":                tipo,
        "mostrar_out":         mostrar_out,
        "mostrar_in":          mostrar_in,
        "tiene_conductor":     tiene_conductor,
        "tiene_adicionales":   tiene_adicionales,
        "tiene_pagos":         tiene_pagos,
        "tiene_entrega":       tiene_entrega,
        "tiene_recepcion":     tiene_recepcion,
        "tiene_firma":         tiene_firma,
        "contrato_listo":      contrato_listo,
        "tiene_finalizacion":  tiene_finalizacion,
        "envios_count":        envios_count,
        "conductor_data":      _cond[0]  if _cond  else None,
        "adicional_data":      _adic[0]  if _adic  else None,
        "pagos_data":          _pagos,
        "entrega_data":        _ent[0]   if _ent   else None,
        "recepcion_data":      _rec[0]   if _rec   else None,
        "firma_data":          _firma[0] if _firma  else None,
        "vuelo_numero":        vuelo_numero,
        "ok":                  request.query_params.get("ok"),
        "active_tab":          "hojas",
    })
