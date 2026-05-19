from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates
from datetime import datetime

router = APIRouter()


def _fmt_date(val) -> str:
    if not val:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    return str(val).strip()


def _fmt_time(val) -> str:
    if not val:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%H:%M")
    s = str(val).strip()
    # HH:MM:SS → HH:MM
    if len(s) >= 5:
        return s[:5]
    return s


def _reserva_prefill(id_reserva: int) -> dict:
    rows = query("""
        SELECT
            [Fecha Entrada]   AS FechaEntrada,
            [Horario Entrada] AS HorarioEntrada,
            [Lugar Entrada]   AS LugarEntrada
        FROM dbo.vw_AppSheet_Reservas
        WHERE IdReserva = ?
    """, [id_reserva])
    if not rows:
        return {}
    r = rows[0]
    return {
        "FechaDevolucion": _fmt_date(r.get("FechaEntrada")),
        "HoraDevolucion":  _fmt_time(r.get("HorarioEntrada")),
        "LugarDevolucion": r.get("LugarEntrada") or "",
    }


@router.get("/{id_reserva}/adicionales", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query("SELECT * FROM adicionales WHERE IdReserva = ?", [id_reserva])
    if rows:
        adicional = rows[0]
        prefill   = {}
    else:
        adicional = {}
        prefill   = _reserva_prefill(id_reserva)
    return templates.TemplateResponse("adicionales.html", {
        "request":    request,
        "id_reserva": id_reserva,
        "adicional":  adicional,
        "prefill":    prefill,
        "ok":         request.query_params.get("ok"),
    })


@router.post("/{id_reserva}/adicionales")
async def guardar(request: Request, id_reserva: int):
    form = dict(await request.form())
    id_op = request.session.get("id_operario", 0)

    existing = query("SELECT Id FROM adicionales WHERE IdReserva = ?", [id_reserva])

    def val(k): return (form.get(k) or "").strip() or None
    def dec(k):
        v = (form.get(k) or "").strip().replace(",", ".")
        try:    return float(v)
        except: return None

    if existing:
        execute("""
            UPDATE adicionales SET
                FechaDevolucion=?, HoraDevolucion=?, LugarDevolucion=?,
                DomicilioProvisorio=?,
                Conductor1=?, Licencia1=?, Vencimiento1=?, EmitidaPor1=?, Categoria1=?,
                Conductor2=?, Licencia2=?, Vencimiento2=?, EmitidaPor2=?, Categoria2=?,
                NumTarjetaGarantia=?, VencimientoTarjeta=?, CodSeguridad=?,
                GarantiaEfectivo=?, GarantiaMoneda=?, IdOperario=?
            WHERE IdReserva=?
        """, [
            val("fecha_devolucion"), val("hora_devolucion"), val("lugar_devolucion"),
            val("domicilio_provisorio"),
            val("conductor1"), val("licencia1"), val("vencimiento1"),
            val("emitida_por1"), val("categoria1"),
            val("conductor2"), val("licencia2"), val("vencimiento2"),
            val("emitida_por2"), val("categoria2"),
            val("num_tarjeta"), val("vencimiento_tarjeta"), val("cod_seguridad"),
            dec("garantia_efectivo"), val("garantia_moneda"),
            id_op, id_reserva,
        ])
    else:
        execute("""
            INSERT INTO adicionales
                (IdReserva, FechaDevolucion, HoraDevolucion, LugarDevolucion,
                 DomicilioProvisorio,
                 Conductor1, Licencia1, Vencimiento1, EmitidaPor1, Categoria1,
                 Conductor2, Licencia2, Vencimiento2, EmitidaPor2, Categoria2,
                 NumTarjetaGarantia, VencimientoTarjeta, CodSeguridad,
                 GarantiaEfectivo, GarantiaMoneda, IdOperario)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            id_reserva, val("fecha_devolucion"), val("hora_devolucion"),
            val("lugar_devolucion"), val("domicilio_provisorio"),
            val("conductor1"), val("licencia1"), val("vencimiento1"),
            val("emitida_por1"), val("categoria1"),
            val("conductor2"), val("licencia2"), val("vencimiento2"),
            val("emitida_por2"), val("categoria2"),
            val("num_tarjeta"), val("vencimiento_tarjeta"), val("cod_seguridad"),
            dec("garantia_efectivo"), val("garantia_moneda"),
            id_op,
        ])

    return RedirectResponse(f"/planilla/{id_reserva}?ok=adicionales", status_code=303)
