import os, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from database import query, execute
from utils import ahora_arg
from routers.finalizar import flag_path

log = logging.getLogger(__name__)
router = APIRouter()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "info@abarentacar.com.ar"
SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")
DEST      = "info@abarentacar.com.ar"


def _send(subject: str, html: str):
    msg = MIMEMultipart("alternative")
    msg["From"]    = f"ABA Rent a Car OPR <{SMTP_USER}>"
    msg["To"]      = DEST
    msg["Subject"] = subject
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
        srv.login(SMTP_USER, SMTP_PASS)
        srv.sendmail(SMTP_USER, DEST, msg.as_string())


def _yn(val) -> str:
    return "Sí" if val else "No"


def _fila(label: str, valor) -> str:
    if valor is None or valor == "" or valor == 0 or valor is False:
        return ""
    return (
        f"<tr>"
        f"<td style='padding:6px 16px;color:#555;font-size:13px;border-bottom:1px solid #f0f0f0;'>{label}</td>"
        f"<td style='padding:6px 16px;font-size:13px;font-weight:600;color:#222;border-bottom:1px solid #f0f0f0;'>{valor}</td>"
        f"</tr>"
    )


def _email_base(titulo: str, subtitulo: str, matricula: str, id_reserva: int, tabla_filas: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
 <tr><td align="center" style="padding:20px 0;">
  <table width="600" cellpadding="0" cellspacing="0" style="background:white;">
   <tr><td align="center" style="padding:30px 0 20px;">
    <img src="https://opr.aba.benvert.com.ar/static/logo.png" alt="ABA Rent a Car" width="150" style="display:block;margin:0 auto;">
   </td></tr>
   <tr><td style="padding:0 40px 20px;">
    <hr style="border:none;border-top:2px solid #4a7c59;margin:0 0 20px;">
    <p style="font-size:20px;font-weight:bold;color:#222;margin:0 0 4px;">{titulo}</p>
    <p style="font-size:14px;color:#666;margin:0 0 20px;">{subtitulo}</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #eee;border-radius:8px;overflow:hidden;">
     {_fila("Matrícula", matricula)}
     {_fila("Reserva N°", id_reserva)}
     {tabla_filas}
    </table>
   </td></tr>
   <tr><td style="background:#3a5a40;padding:20px 40px;text-align:center;">
    <p style="color:white;font-size:13px;margin:0;">ABA Rent a Car — Sistema OPR</p>
   </td></tr>
  </table>
 </td></tr>
</table>
</body></html>"""


@router.get("/{id_reserva}/enviar-taller")
async def enviar_taller(request: Request, id_reserva: int):
    res = query("""
        SELECT r.MATRICULA, r.Contrato,
               r.[Sucursales.Sucursal] AS SucursalSalida,
               CAST(r.[Fecha Salida] AS DATE) AS FechaSalida
        FROM dbo.vw_AppSheet_Reservas r WHERE r.IdReserva = ?
    """, [id_reserva])
    if not res:
        return RedirectResponse(f"/planilla/{id_reserva}?tipo=OUT&error=no_reserva", status_code=303)
    rv = res[0]
    matricula = rv.get("MATRICULA") or ""

    ent = query("SELECT * FROM entregas WHERE IdReserva = ?", [id_reserva])
    if not ent:
        return RedirectResponse(f"/planilla/{id_reserva}?tipo=OUT&error=sin_entrega", status_code=303)
    e = ent[0]

    tabla = (
        _fila("Sucursal / Taller", rv.get("SucursalSalida")) +
        _fila("Fecha Salida", rv.get("FechaSalida")) +
        _fila("Km Salida", e.get("KmSalida")) +
        _fila("Nafta", e.get("NaftaSalida")) +
        _fila("Auxilio", _yn(e.get("Auxilio"))) +
        _fila("Silla Bebé", e.get("SillaBebe")) +
        _fila("Cadenas", _yn(e.get("Cadenas"))) +
        _fila("GPS", _yn(e.get("GPS"))) +
        _fila("Barras", _yn(e.get("Barras"))) +
        _fila("Permiso Chile", _yn(e.get("PermisoChile"))) +
        _fila("Kit Seguridad", _yn(e.get("KitSeg"))) +
        _fila("Observaciones", e.get("Observaciones"))
    )

    html = _email_base(
        f"Vehículo enviado a taller",
        f"El operador registró la salida del vehículo hacia el taller.",
        matricula, id_reserva, tabla
    )
    subject = f"[TALLER] {matricula} — Envío a taller | Reserva {id_reserva}"

    try:
        _send(subject, html)
    except Exception as ex:
        log.error("Error enviando mail taller OUT reserva %d: %s", id_reserva, ex)

    try:
        execute("""
            INSERT INTO opr.mails_enviados (IdReserva, Recipient, Nombre, FechaEnvio)
            VALUES (?, ?, 'Taller', CAST(GETDATE() AS DATE))
        """, [id_reserva, DEST])
    except Exception as ex:
        log.error("Error insertando mails_enviados taller reserva %d: %s", id_reserva, ex)

    return RedirectResponse(f"/planilla/{id_reserva}?tipo=OUT&ok=taller_enviado", status_code=303)


@router.get("/{id_reserva}/finalizar-taller")
async def finalizar_taller(id_reserva: int):
    res = query("""
        SELECT r.MATRICULA,
               r.[Sucursales_1.Sucursal] AS SucursalEntrada,
               CAST(r.[Fecha Entrada] AS DATE) AS FechaEntrada
        FROM dbo.vw_AppSheet_Reservas r WHERE r.IdReserva = ?
    """, [id_reserva])
    if not res:
        return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&error=no_reserva", status_code=303)
    rv = res[0]
    matricula = rv.get("MATRICULA") or ""

    rec = query("SELECT * FROM recepciones WHERE IdReserva = ?", [id_reserva])
    if not rec:
        return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&error=sin_recepcion", status_code=303)
    r_data = rec[0]

    tabla = (
        _fila("Sucursal / Taller", rv.get("SucursalEntrada")) +
        _fila("Fecha Entrada", rv.get("FechaEntrada")) +
        _fila("Km Entrada", r_data.get("KmEntrada")) +
        _fila("Nafta Entrada", r_data.get("NaftaEntrada")) +
        _fila("Observaciones", r_data.get("Observaciones"))
    )

    html = _email_base(
        f"Vehículo salió del taller",
        f"El operador registró la recepción del vehículo desde el taller.",
        matricula, id_reserva, tabla
    )
    subject = f"[TALLER] {matricula} — Salida de taller | Reserva {id_reserva}"

    try:
        _send(subject, html)
    except Exception as ex:
        log.error("Error enviando mail taller IN reserva %d: %s", id_reserva, ex)

    try:
        fp = flag_path(id_reserva)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(ahora_arg().isoformat())
    except Exception as ex:
        log.error("Error creando flag taller reserva %d: %s", id_reserva, ex)

    return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&ok=taller_finalizado", status_code=303)
