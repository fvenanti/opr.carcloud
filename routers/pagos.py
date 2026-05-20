from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates
from utils import hoy_arg

router = APIRouter()


@router.get("/{id_reserva}/pagos", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    pagos = query(
        "SELECT * FROM pagos WHERE IdReserva = ? ORDER BY FechaPago DESC, Id DESC",
        [id_reserva],
    )
    # Total pendiente desde la vista de CarCloud (tomar el primero de la reserva)
    pendiente_rows = query(
        "SELECT TOP 1 [Total Pendiente] AS TotalPendiente FROM dbo.vw_AppSheet_Movimientos WHERE IdReserva = ?",
        [id_reserva],
    )
    total_pendiente = pendiente_rows[0]["TotalPendiente"] if pendiente_rows else None

    tipos_pago = query(
        "SELECT [Id_Tipo Pago] AS id, [Descripción] AS nombre FROM dbo.[Tipos Pago] ORDER BY [Id_Tipo Pago]"
    )
    conceptos = query(
        "SELECT Id_Concepto AS id, Concepto AS nombre FROM dbo.Conceptos ORDER BY Id_Concepto"
    )

    return templates.TemplateResponse("pagos.html", {
        "request":         request,
        "id_reserva":      id_reserva,
        "pagos":           pagos,
        "total_pendiente": total_pendiente,
        "tipos_pago":      tipos_pago,
        "conceptos":       conceptos,
        "hoy":             hoy_arg().isoformat(),
        "ok":              request.query_params.get("ok"),
    })


@router.post("/{id_reserva}/pagos")
async def agregar(request: Request, id_reserva: int):
    form = dict(await request.form())
    id_op = request.session.get("id_operario", 0)

    def val(k): return (form.get(k) or "").strip() or None
    def dec(k):
        v = (form.get(k) or "0").strip().replace(",", ".")
        try:    return float(v)
        except: return 0.0

    execute("""
        INSERT INTO pagos
            (IdReserva, FechaPago, Importe, Moneda, TipoPago,
             TipoCambio, Concepto, Observaciones, IdOperario)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, [
        id_reserva,
        val("fecha_pago") or hoy_arg().isoformat(),
        dec("importe"),
        val("moneda") or "PESO",
        val("tipo_pago") or "Efectivo",
        dec("tipo_cambio") or 1.0,
        val("concepto") or "Alquiler",
        val("observaciones"),
        id_op,
    ])

    return RedirectResponse(f"/planilla/{id_reserva}/pagos?ok=agregado", status_code=303)


@router.post("/{id_reserva}/pagos/{id_pago}/eliminar")
async def eliminar(id_reserva: int, id_pago: int):
    execute("DELETE FROM pagos WHERE Id = ? AND IdReserva = ?", [id_pago, id_reserva])
    return RedirectResponse(f"/planilla/{id_reserva}/pagos?ok=eliminado", status_code=303)
