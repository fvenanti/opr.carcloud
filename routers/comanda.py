import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query

log = logging.getLogger(__name__)
router = APIRouter()

# ── Queries ────────────────────────────────────────────────────────────────────

_SQL_RESERVA = """
SELECT
    IdReserva,
    MATRICULA,
    ISNULL(Apellido,'') + CASE WHEN Nombre IS NOT NULL THEN ', ' + Nombre ELSE '' END AS Cliente,
    CAST([Fecha Salida] AS DATE)  AS FechaSalida,
    [Horario Salida]              AS HorarioSalida,
    [Lugar Salida]                AS LugarSalida,
    CAST([Fecha Entrada] AS DATE) AS FechaEntrada,
    [Horario Entrada]             AS HorarioEntrada,
    [Lugar Entrada]               AS LugarEntrada,
    Tarifa,
    [Días]                        AS Dias,
    Km,
    [Monedas.Descripcion]         AS Moneda
FROM dbo.vw_AppSheet_Reservas
WHERE IdReserva = ?
"""

_SQL_MOV = """
SELECT TOP 1
    [Total Alquiler]      AS TotalAlquiler,
    [Total Abonado]       AS TotalAbonado,
    [Total Pendiente]     AS TotalPendiente,
    [Monedas.Descripcion] AS Moneda
FROM dbo.vw_AppSheet_Movimientos
WHERE IdReserva = ?
"""

_SQL_ENTREGA   = "SELECT TOP 1 KmSalida,  NaftaSalida,  IdOperario FROM entregas    WHERE IdReserva = ?"
_SQL_RECEPCION = "SELECT TOP 1 KmEntrada, NaftaEntrada, IdOperario FROM recepciones  WHERE IdReserva = ?"
_SQL_PAGOS     = "SELECT Importe, Moneda, TipoPago, TipoCambio, Concepto FROM pagos WHERE IdReserva = ? ORDER BY FechaPago, Id"

# ── Formato ────────────────────────────────────────────────────────────────────

def _fmt_num(val) -> str:
    if val is None or val == "":
        return "—"
    try:
        return f"{int(round(float(val))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(val)


def _fmt_importe(val, moneda="Pesos") -> str:
    if val is None or val == "":
        return "—"
    try:
        symbol = "US$" if "dolar" in (moneda or "").lower() else "$"
        return f"{symbol} {int(round(float(val))):,}".replace(",", ".")
    except (ValueError, TypeError):
        return str(val)


def _fmt_fecha(val) -> str:
    if val is None:
        return "—"
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y")
    return str(val)


def _v(val) -> str:
    return str(val) if val else "—"

# ── HTML builder ───────────────────────────────────────────────────────────────

def _fila(label: str, value: str) -> str:
    return f'<tr><td class="lbl">{label}</td><td class="val">{value}</td></tr>'


def _seccion(titulo: str, filas: list[str]) -> str:
    rows = "\n".join(filas)
    return f"""
<div class="sec">
  <div class="sec-title">{titulo}</div>
  <table>{rows}</table>
</div>"""


def _build_html(tipo: str, r: dict, mov: dict, entrega: dict,
                recepcion: dict, pagos: list, operador: str = "") -> str:

    moneda = mov.get("Moneda") or r.get("Moneda") or "Pesos"

    secciones = []

    # Salida
    secciones.append(_seccion("SALIDA", [
        _fila("Fecha",   _fmt_fecha(r.get("FechaSalida"))),
        _fila("Horario", _v(r.get("HorarioSalida"))),
        _fila("Lugar",   _v(r.get("LugarSalida"))),
    ]))

    # Devolución
    secciones.append(_seccion("DEVOLUCIÓN", [
        _fila("Fecha",   _fmt_fecha(r.get("FechaEntrada"))),
        _fila("Horario", _v(r.get("HorarioEntrada"))),
        _fila("Lugar",   _v(r.get("LugarEntrada"))),
    ]))

    # Tarifas
    secciones.append(_seccion("TARIFAS", [
        _fila("Tarifa", _fmt_importe(r.get("Tarifa"), moneda)),
        _fila("Días",   _v(r.get("Dias"))),
        _fila("Km",     _v(r.get("Km"))),
    ]))

    # Totales
    secciones.append(_seccion("TOTALES", [
        _fila("Total reserva",   _fmt_importe(mov.get("TotalAlquiler"),  moneda)),
        _fila("Total abonado",   _fmt_importe(mov.get("TotalAbonado"),   moneda)),
        _fila("Total pendiente", _fmt_importe(mov.get("TotalPendiente"), moneda)),
    ]))

    # Km / Combustible
    if tipo == "SALIDA":
        nafta = entrega.get("NaftaSalida")
        secciones.append(_seccion("KM / COMBUSTIBLE", [
            _fila("Km salida",   _fmt_num(entrega.get("KmSalida"))),
            _fila("Comb. salida", f"{int(nafta)}%" if nafta is not None else "—"),
        ]))
    else:
        km_e = recepcion.get("KmEntrada")
        km_s = entrega.get("KmSalida")
        nafta = recepcion.get("NaftaEntrada")
        try:
            dif = _fmt_num(int(km_e) - int(km_s)) if km_e is not None and km_s is not None else "—"
        except (TypeError, ValueError):
            dif = "—"
        secciones.append(_seccion("KM / COMBUSTIBLE", [
            _fila("Km entrada",    _fmt_num(km_e)),
            _fila("Diferencia Km", dif),
            _fila("Comb. entrada", f"{int(nafta)}%" if nafta is not None else "—"),
        ]))

    # Pagos
    if pagos:
        filas_pagos = []
        for p in pagos:
            moneda_p = p.get("Moneda") or "Pesos"
            filas_pagos.append(_fila(
                p.get("TipoPago") or "",
                f'{_fmt_importe(p.get("Importe"), moneda_p)}'
                + (f' — {p["Concepto"]}' if p.get("Concepto") else "")
            ))
        secciones.append(_seccion("PAGOS", filas_pagos))

    cuerpo = "\n".join(secciones)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comanda {r['IdReserva']}</title>
<style>
  /* ── Pantalla ── */
  body {{
    font-family: 'Courier New', monospace;
    font-size: 12px;
    margin: 0;
    padding: 8px;
    background: #f5f5f5;
  }}
  .page {{
    background: white;
    width: 72mm;
    margin: 0 auto;
    padding: 6mm 4mm;
    box-shadow: 0 2px 8px rgba(0,0,0,.15);
  }}
  .toolbar {{
    display: flex;
    gap: 8px;
    width: 72mm;
    margin: 12px auto;
  }}
  .back-btn {{
    padding: 10px 14px;
    background: #e5e7eb;
    color: #111;
    font-size: 14px;
    font-weight: bold;
    text-align: center;
    border-radius: 8px;
    text-decoration: none;
    white-space: nowrap;
  }}
  .print-btn {{
    flex: 1;
    padding: 10px;
    background: #1d4ed8;
    color: white;
    font-size: 14px;
    font-weight: bold;
    text-align: center;
    border: none;
    border-radius: 8px;
    cursor: pointer;
  }}

  /* ── Contenido ── */
  .header {{ text-align: center; margin-bottom: 4mm; }}
  .header h1 {{ font-size: 15px; margin: 0 0 1mm; letter-spacing: 2px; }}
  .header h2 {{ font-size: 11px; margin: 0; font-weight: normal; }}
  .header .matricula {{ font-size: 18px; font-weight: bold; margin: 2mm 0 0; }}
  .hr {{ border: none; border-top: 1px dashed #555; margin: 3mm 0; }}
  .operador {{ font-size: 12px; font-weight: bold; color: #000; margin-top: 1mm; }}
  .sec {{ margin-bottom: 3mm; }}
  .sec-title {{ font-weight: bold; font-size: 10px; text-transform: uppercase;
                letter-spacing: 1px; margin-bottom: 1mm; border-bottom: 1px solid #000; }}
  table {{ width: 100%; border-collapse: collapse; }}
  .lbl {{ color: #444; width: 45%; padding: 0.5mm 0; vertical-align: top; }}
  .val {{ font-weight: bold; padding: 0.5mm 0; }}

  /* ── Impresión ── */
  @media print {{
    @page {{ size: 80mm auto; margin: 4mm; }}
    body {{ background: white !important; padding: 0; font-size: 22pt !important; color: #000 !important; }}
    .page {{ box-shadow: none; margin: 0; padding: 0; width: auto; }}
    .toolbar {{ display: none !important; }}
    * {{ color: #000 !important; }}
    .header h1 {{ font-size: 26pt !important; }}
    .header h2 {{ font-size: 20pt !important; }}
    .header .matricula {{ font-size: 32pt !important; }}
    .header div {{ font-size: 20pt !important; }}
    .operador {{ font-size: 22pt !important; font-weight: bold !important; }}
    .sec-title {{ font-size: 19pt !important; border-bottom: 2px solid #000 !important; }}
    .lbl {{ font-size: 22pt !important; padding: 2mm 0 !important; font-weight: bold !important; }}
    .val {{ font-size: 22pt !important; padding: 2mm 0 !important; font-weight: bold !important; }}
    .hr {{ margin: 3mm 0; border-top: 2px dashed #000 !important; }}
    .sec {{ margin-bottom: 6mm; }}
  }}
</style>
</head>
<body>
<div class="toolbar">
  <a class="back-btn" href="/planilla/{r['IdReserva']}?tipo={tipo[0]}">← Volver</a>
  <button class="print-btn" onclick="window.print()">🖨 Imprimir</button>
</div>
<div class="page">
  <div class="header">
    <h1>ABA RENT A CAR</h1>
    <h2>— {tipo} —</h2>
    <div class="matricula">{r.get('MATRICULA','')}</div>
    <div class="matricula">Reserva #{r['IdReserva']}</div>
    <div>{r.get('Cliente','')}</div>
    {f'<div class="operador">Op: {operador}</div>' if operador else ''}
  </div>
  <hr class="hr">
  {cuerpo}
</div>
</body>
</html>"""


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.get("/{id_reserva}/comanda")
async def comanda(request: Request, id_reserva: int, tipo: str = "OUT"):
    tipo = tipo.upper()

    rows = query(_SQL_RESERVA, [id_reserva])
    if not rows:
        return HTMLResponse("Reserva no encontrada", status_code=404)
    r = rows[0]

    mov_rows  = query(_SQL_MOV,       [id_reserva])
    ent_rows  = query(_SQL_ENTREGA,   [id_reserva])
    rec_rows  = query(_SQL_RECEPCION, [id_reserva])
    pago_rows = query(_SQL_PAGOS,     [id_reserva])

    mov       = mov_rows[0]  if mov_rows  else {}
    entrega   = ent_rows[0]  if ent_rows  else {}
    recepcion = rec_rows[0]  if rec_rows  else {}

    titulo = "ENTRADA" if tipo == "IN" else "SALIDA"
    id_op  = (recepcion if tipo == "IN" else entrega).get("IdOperario")
    if id_op:
        op_rows  = query("SELECT Nombre FROM dbo.tbl_operario WHERE Id = ?", [id_op])
        operador = op_rows[0]["Nombre"] if op_rows else (request.session.get("user_nombre") or "")
    else:
        operador = request.session.get("user_nombre") or ""

    html = _build_html(titulo, r, mov, entrega, recepcion, pago_rows, operador)
    return HTMLResponse(html)
