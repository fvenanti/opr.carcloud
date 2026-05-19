import os
import shutil
import subprocess
import tempfile
import smtplib
import logging
from copy import deepcopy
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from datetime import datetime

from docx import Document
from docx.shared import Inches

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query
from shared_templates import templates

log = logging.getLogger(__name__)
router = APIRouter()

TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..",
    "GenerarPDF Task - 2_BodyTemplate_20230920_224146.docx"
)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
def contrato_pdf_path(id_reserva: int) -> str:
    return os.path.join(UPLOAD_DIR, str(id_reserva), f"contrato_{id_reserva}.pdf")


def contrato_enviado(id_reserva: int) -> bool:
    return os.path.isfile(contrato_pdf_path(id_reserva))


SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "info@abarentacar.com.ar"
SMTP_PASS = os.environ.get("SMTP_PASSWORD", "")

_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ── Helpers de formato ────────────────────────────────────────────────────────

def _fmt_date(val) -> str:
    if not val:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if len(s) >= 10 and s[4] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            pass
    return s


def _fmt_time(val) -> str:
    if not val:
        return ""
    s = str(val).strip()
    return s[:5] if len(s) >= 5 else s


def _yn(val) -> str:
    return "SI" if val in (1, True, "1", "Y", "y") else "NO"


def _disk_path(url_path: str) -> str:
    """Convierte /uploads/... a ruta real en disco."""
    if not url_path:
        return ""
    rel = url_path.lstrip("/")
    if rel.startswith("uploads/"):
        rel = rel[len("uploads/"):]
    return os.path.join(UPLOAD_DIR, rel)


# ── Construcción del contexto ─────────────────────────────────────────────────

def _build_context(id_reserva: int) -> dict:
    ctx: dict = {}

    # Reserva
    res = query("""
        SELECT MATRICULA, Apellido, Nombre,
            [Fecha Salida]      AS FechaSalida,
            [Horario Salida]    AS HorarioSalida,
            [Lugar Salida]      AS LugarSalida,
            Tarifa,
            [Monedas.Descripcion] AS MonedaDesc,
            [Días]              AS Dias,
            Km,
            [Km adicional]      AS KmAdicional,
            FranquiciaChoque,
            FranquiciaVuelco,
            abonada             AS TotalAbonado
        FROM dbo.vw_AppSheet_Reservas WHERE IdReserva = ?
    """, [id_reserva])
    if res:
        r = res[0]
        ctx.update({
            "MATRICULA":           r.get("MATRICULA") or "",
            "Horario Salida":      _fmt_time(r.get("HorarioSalida")),
            "Fecha Salida":        _fmt_date(r.get("FechaSalida")),
            "Lugar Salida":        r.get("LugarSalida") or "",
            "Tarifa":              str(r.get("Tarifa") or ""),
            "Monedas.Descripcion": r.get("MonedaDesc") or "",
            "Días":                str(r.get("Dias") or ""),
            "Km":                  str(r.get("Km") or ""),
            "Km adicional":        str(r.get("KmAdicional") or ""),
            "FranquiciaChoque":    str(r.get("FranquiciaChoque") or ""),
            "FranquiciaVuelco":    str(r.get("FranquiciaVuelco") or ""),
            "Total Abonado":       str(r.get("TotalAbonado") or ""),
        })

    # Totales desde movimientos
    mov = query("""
        SELECT TOP 1
            [Total Alquiler]  AS TotalAlquiler,
            [Total Pendiente] AS TotalPendiente
        FROM dbo.vw_AppSheet_Movimientos WHERE IdReserva = ?
    """, [id_reserva])
    if mov:
        ctx["Total Alquiler"]  = str(mov[0].get("TotalAlquiler") or "")
        ctx["Total Pendiente"] = str(mov[0].get("TotalPendiente") or "")

    # Vehículo
    if ctx.get("MATRICULA"):
        veh = query("""
            SELECT Marca, Modelo, COMBUSTIBLE, CuartoTanque, Espera
            FROM dbo.vw_AppSheet_Vehiculos WHERE MATRICULA = ?
        """, [ctx["MATRICULA"]])
        if veh:
            v = veh[0]
            ctx.update({
                "MARCA":          v.get("Marca") or "",
                "MODELO":         v.get("Modelo") or "",
                "COMBUSTIBLE":    v.get("COMBUSTIBLE") or "",
                "CUARTODETANQUE": str(v.get("CuartoTanque") or ""),
                "Espera":         str(v.get("Espera") or ""),
            })

    # Conductor principal
    cond = query("SELECT * FROM conductores WHERE IdReserva = ?", [id_reserva])
    if cond:
        c = cond[0]
        ctx.update({
            "Apellido":             c.get("Apellido") or "",
            "Nombre":               c.get("Nombre") or "",
            "Fecha de Nacimiento":  _fmt_date(c.get("FechaNacimiento")),
            "TIPO DOCUMENTO":       c.get("DniTipo") or "DNI",
            "DNI":                  c.get("DniNumero") or "",
            "Teléfono":             c.get("Telefono") or "",
            "Domicilio Particular": c.get("Domicilio") or "",
            "Mail":                 c.get("Mail") or "",
            "Numero de Licencia":   c.get("NumeroLicencia") or "",
            "Vencimiento":          _fmt_date(c.get("VencimientoLicencia")),
            "Emitida por":          c.get("EmitidaPor") or "",
            "Categoría":            c.get("Categoria") or "",
            "_client_email":        c.get("Mail") or "",
            "_client_name":         f"{c.get('Nombre') or ''} {c.get('Apellido') or ''}".strip(),
        })

    # Adicionales
    adic = query("SELECT * FROM adicionales WHERE IdReserva = ?", [id_reserva])
    if adic:
        a = adic[0]
        ctx.update({
            "Hora Devolucion":           _fmt_time(a.get("HoraDevolucion")),
            "Fecha Devolucion":          _fmt_date(a.get("FechaDevolucion")),
            "Lugar Devolucion":          a.get("LugarDevolucion") or "",
            "Conductor Adicional 1":     a.get("Conductor1") or "",
            "Numero de Licencia 1":      a.get("Licencia1") or "",
            "Vencimiento 1":             _fmt_date(a.get("Vencimiento1")),
            "Emitida por 1":             a.get("EmitidaPor1") or "",
            "Categoria 1":               a.get("Categoria1") or "",
            "Conductor Adicional 2":     a.get("Conductor2") or "",
            "Numero de Licencia 2":      a.get("Licencia2") or "",
            "Vencimiento 2":             _fmt_date(a.get("Vencimiento2")),
            "Emitida por 2":             a.get("EmitidaPor2") or "",
            "Categoria 2":               a.get("Categoria2") or "",
            "Numero Tarjeta de Credito": a.get("NumTarjetaGarantia") or "",
            "Vencimiento Tarjeta":       _fmt_date(a.get("VencimientoTarjeta")),
            "Importe Efectivo":          str(a.get("GarantiaEfectivo") or ""),
            "Moneda":                    a.get("GarantiaMoneda") or "",
        })

    # Entrega del vehículo
    ent = query("SELECT * FROM entregas WHERE IdReserva = ?", [id_reserva])
    if ent:
        e = ent[0]
        ctx.update({
            "Km salida":     str(e.get("KmSalida") or ""),
            "Nafta salida":  str(e.get("NaftaSalida") or ""),
            "AUXILIO":       _yn(e.get("Auxilio")),
            "Silla Bebe":    str(e.get("SillaBebe") or 0),
            "Cadenas":       _yn(e.get("Cadenas")),
            "GPS":           _yn(e.get("GPS")),
            "Barras":        _yn(e.get("Barras")),
            "Permiso Chile": _yn(e.get("PermisoChile")),
            "Kit Seg":       _yn(e.get("KitSeg")),
            "_foto_frente_izq":  _disk_path(e.get("FotoFrenteIzq") or ""),
            "_foto_frente_der":  _disk_path(e.get("FotoFrenteDer") or ""),
            "_foto_trasera_izq": _disk_path(e.get("FotoTraseraIzq") or ""),
            "_foto_trasera_der": _disk_path(e.get("FotoTraseraDer") or ""),
            "_foto_auxilio":     _disk_path(e.get("FotoAuxilio") or ""),
        })

    # Firma
    firma = query("SELECT * FROM firmas WHERE IdReserva = ?", [id_reserva])
    if firma:
        f = firma[0]
        ctx["_firma_path"] = _disk_path(f.get("FirmaImagen") or "")
        ctx["Aclaracion"]  = f.get("Aclaracion") or ""
        ctx["Lugar"]       = ctx.get("Lugar Salida", "")
        ctx["Fecha"]       = datetime.now().strftime("%d/%m/%Y")

    # Pagos
    pagos = query("""
        SELECT FechaPago, Importe, Moneda, TipoPago, TipoCambio, Concepto
        FROM pagos WHERE IdReserva = ? ORDER BY FechaPago, Id
    """, [id_reserva])
    ctx["_pagos"] = pagos

    return ctx


# ── Manipulación del DOCX ─────────────────────────────────────────────────────

def _elem_full_text(elem) -> str:
    return "".join((t.text or "") for t in elem.iter(f"{_NS}t"))


def _replace_in_para(para_elem, mapping: dict):
    """Reemplaza <<[clave]>> en todos los <w:t> de un párrafo, concatenando runs."""
    t_elems = list(para_elem.iter(f"{_NS}t"))
    if not t_elems:
        return
    full = "".join(t.text or "" for t in t_elems)
    if "<<" not in full:
        return
    for key, val in mapping.items():
        full = full.replace(f"<<[{key}]>>", str(val) if val is not None else "")
    t_elems[0].text = full
    for t in t_elems[1:]:
        t.text = ""


def _replace_in_elem(elem, mapping: dict):
    """Reemplaza placeholders en todos los párrafos de un elemento XML."""
    for para in elem.iter(f"{_NS}p"):
        _replace_in_para(para, mapping)


def _expand_pagos_loop(doc, pagos_list: list):
    """Expande <<Start: [...]>>...<<End>> en tablas para la lista de pagos."""
    pago_fields = {
        "Fecha de pago":  lambda p: _fmt_date(p.get("FechaPago")),
        "Importe":        lambda p: str(p.get("Importe") or ""),
        "Moneda":         lambda p: p.get("Moneda") or "",
        "Tipo de pago":   lambda p: p.get("TipoPago") or "",
        "Tipo de Cambio": lambda p: str(p.get("TipoCambio") or ""),
        "Concepto":       lambda p: p.get("Concepto") or "",
    }

    for table in doc.tables:
        start_idx = end_idx = None
        for i, row in enumerate(table.rows):
            text = _elem_full_text(row._tr)
            if "<<Start:" in text and start_idx is None:
                start_idx = i
            elif "<<End>>" in text and start_idx is not None:
                end_idx = i
                break

        if start_idx is None or end_idx is None:
            continue

        tbl = table._tbl
        start_tr = table.rows[start_idx]._tr
        tmpl_trs  = [table.rows[i]._tr for i in range(start_idx + 1, end_idx)]
        end_tr    = table.rows[end_idx]._tr

        # Insertar una fila por pago (antes del marcador <<End>>)
        for pago in pagos_list:
            pago_map = {k: fn(pago) for k, fn in pago_fields.items()}
            for tmpl_tr in tmpl_trs:
                new_tr = deepcopy(tmpl_tr)
                _replace_in_elem(new_tr, pago_map)
                end_tr.addprevious(new_tr)

        # Eliminar marcadores y fila template
        tbl.remove(start_tr)
        for tr in tmpl_trs:
            tbl.remove(tr)
        tbl.remove(end_tr)


def _insert_firma(doc, firma_path: str):
    """Reemplaza <<[FIRMA]>> con la imagen de firma."""
    if not firma_path or not os.path.isfile(firma_path):
        return

    def _try_paras(paragraphs):
        for para in paragraphs:
            text = "".join(r.text for r in para.runs)
            if "<<[FIRMA]>>" not in text:
                continue
            for run in para.runs:
                run.text = ""
            try:
                para.add_run().add_picture(firma_path, width=Inches(2.5))
            except Exception as e:
                log.warning("No se pudo insertar imagen de firma: %s", e)
                para.add_run().text = "[firma]"
            return True
        return False

    if _try_paras(doc.paragraphs):
        return
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if _try_paras(cell.paragraphs):
                    return


def _fill_docx(ctx: dict, output_path: str):
    doc = Document(TEMPLATE_PATH)
    simple = {k: v for k, v in ctx.items() if not k.startswith("_")}

    _expand_pagos_loop(doc, ctx.get("_pagos", []))

    for para in doc.paragraphs:
        _replace_in_para(para._p, simple)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    _replace_in_para(para._p, simple)

    _insert_firma(doc, ctx.get("_firma_path", ""))
    doc.save(output_path)


def _to_pdf(docx_path: str) -> str:
    out_dir = os.path.dirname(docx_path)
    env = os.environ.copy()
    env["HOME"] = out_dir  # evita conflictos de perfil LibreOffice
    result = subprocess.run(
        ["libreoffice", "--headless", "--norestore",
         "--convert-to", "pdf", "--outdir", out_dir, docx_path],
        capture_output=True, text=True, timeout=90, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice error: {result.stderr}")
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    if not os.path.isfile(pdf):
        raise RuntimeError(f"PDF no encontrado tras conversión: {pdf}")
    return pdf


# ── Envío por email ───────────────────────────────────────────────────────────

def _send_email(to_email: str, pdf_path: str, id_reserva: int):
    msg = MIMEMultipart()
    msg["From"]    = f"ABA Rent a Car <{SMTP_USER}>"
    msg["To"]      = to_email
    msg["Subject"] = f"Contrato de Alquiler - Reserva {id_reserva}"

    msg.attach(MIMEText(
        f"Estimado/a,\n\n"
        f"Adjunto encontrará el contrato de alquiler correspondiente a la reserva N° {id_reserva}.\n\n"
        f"Gracias por elegir ABA Rent a Car.\n\n"
        f"ABA Rent a Car\ninfo@abarentacar.com.ar",
        "plain"
    ))

    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition",
                    f'attachment; filename="Contrato_{id_reserva}.pdf"')
    msg.attach(part)

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
        srv.login(SMTP_USER, SMTP_PASS)
        srv.sendmail(SMTP_USER, to_email, msg.as_string())


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{id_reserva}/enviar-contrato", response_class=HTMLResponse)
async def confirmar(request: Request, id_reserva: int):
    cond = query(
        "SELECT Mail, Nombre, Apellido FROM conductores WHERE IdReserva = ?",
        [id_reserva]
    )
    client_email = client_name = ""
    if cond:
        client_email = cond[0].get("Mail") or ""
        client_name  = f"{cond[0].get('Nombre') or ''} {cond[0].get('Apellido') or ''}".strip()

    return templates.TemplateResponse("enviar_contrato.html", {
        "request":           request,
        "id_reserva":        id_reserva,
        "client_email":      client_email,
        "client_name":       client_name,
        "contrato_enviado":  contrato_enviado(id_reserva),
        "ok":                request.query_params.get("ok"),
        "error":             request.query_params.get("error"),
    })


@router.post("/{id_reserva}/enviar-contrato")
async def enviar(request: Request, id_reserva: int):
    # Bloquear doble envío
    if contrato_enviado(id_reserva):
        return RedirectResponse(
            f"/planilla/{id_reserva}/enviar-contrato?error=ya_enviado",
            status_code=303
        )

    form = dict(await request.form())
    to_email = (form.get("email") or "").strip()

    if not to_email:
        return RedirectResponse(
            f"/planilla/{id_reserva}/enviar-contrato?error=email_vacio",
            status_code=303
        )

    try:
        ctx = _build_context(id_reserva)
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = os.path.join(tmpdir, f"contrato_{id_reserva}.docx")
            _fill_docx(ctx, docx_path)
            pdf_path = _to_pdf(docx_path)
            _send_email(to_email, pdf_path, id_reserva)

            # Guardar copia permanente
            dest = contrato_pdf_path(id_reserva)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(pdf_path, dest)

        return RedirectResponse(
            f"/planilla/{id_reserva}?ok=contrato_enviado",
            status_code=303
        )

    except Exception as e:
        log.error("Error enviando contrato %d: %s", id_reserva, e, exc_info=True)
        return RedirectResponse(
            f"/planilla/{id_reserva}/enviar-contrato?error=fallo",
            status_code=303
        )
