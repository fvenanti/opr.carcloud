import re
import pyodbc
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates
from datetime import datetime

router = APIRouter()

# Mapea nombre de columna en la BD → label legible para mostrar al operador
_COL_LABELS = {
    "Nombre":              "Nombre",
    "Apellido":            "Apellido",
    "DniTipo":             "DNI Tipo",
    "DniNumero":           "DNI Número",
    "Telefono":            "Teléfono",
    "Domicilio":           "Domicilio",
    "Mail":                "Mail",
    "NumeroLicencia":      "Número de Licencia",
    "EmitidaPor":          "Emitida por",
    "Categoria":           "Categoría",
}


def _parse_truncation(err: Exception) -> str | None:
    """Devuelve un mensaje amigable si el error es de truncamiento, si no None."""
    msg = str(err)
    if "would be truncated" not in msg:
        return None
    col_match = re.search(r"column '([^']+)'", msg)
    val_match = re.search(r"Truncated value:\s*'([^']*)'", msg)
    col = col_match.group(1) if col_match else "un campo"
    label = _COL_LABELS.get(col, col)
    val = val_match.group(1) if val_match else ""
    extra = f' Valor: "{val}".' if val else ""
    return f'El campo "{label}" es demasiado largo.{extra} Acortalo y volvé a guardar.'


def _fmt_date(val) -> str:
    if not val:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    # DD/MM/YYYY → YYYY-MM-DD
    if len(s) == 10 and s[2] == "/" and s[5] == "/":
        try:
            return datetime.strptime(s, "%d/%m/%Y").strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def _cliente_prefill(id_reserva: int) -> dict:
    res = query(
        "SELECT IdCliente FROM dbo.vw_AppSheet_Reservas WHERE IdReserva = ?",
        [id_reserva],
    )
    if not res:
        return {}
    id_cliente = res[0]["IdCliente"]
    cli = query(
        "SELECT * FROM dbo.vw_AppSheet_Clientes WHERE IdCliente = ?",
        [id_cliente],
    )
    if not cli:
        return {}
    c = cli[0]
    return {
        "Nombre":             c.get("Nombre") or "",
        "Apellido":           c.get("Apellido") or "",
        "FechaNacimiento":    _fmt_date(c.get("Fecha de Nacimiento")),
        "DniTipo":            c.get("TIPO DOCUMENTO") or "DNI",
        "DniNumero":          c.get("DNI") or "",
        "Telefono":           c.get("Teléfono") or "",
        "Domicilio":          c.get("Domicilio permanente") or "",
        "Mail":               c.get("Mail") or "",
        "NumeroLicencia":     c.get("Licencia de Conducir Nro") or "",
        "VencimientoLicencia": _fmt_date(c.get("Vencimiento")),
        "EmitidaPor":         c.get("EMITIDA POR") or "",
        "Categoria":          c.get("CAT") or "",
    }


def _render(request: Request, id_reserva: int, conductor: dict, prefill: dict, error: str | None = None):
    return templates.TemplateResponse("conductor.html", {
        "request":    request,
        "id_reserva": id_reserva,
        "conductor":  conductor,
        "prefill":    prefill,
        "error":      error,
        "ok":         request.query_params.get("ok"),
    })


@router.get("/{id_reserva}/conductor", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query(
        "SELECT * FROM conductores WHERE IdReserva = ?",
        [id_reserva],
    )
    if rows:
        conductor = rows[0]
        prefill   = {}
    else:
        conductor = {}
        prefill   = _cliente_prefill(id_reserva)
    return _render(request, id_reserva, conductor, prefill)


@router.post("/{id_reserva}/conductor")
async def guardar(request: Request, id_reserva: int):
    form = dict(await request.form())
    id_op = request.session.get("id_operario", 0)

    existing = query("SELECT Id FROM conductores WHERE IdReserva = ?", [id_reserva])

    def val(k): return (form.get(k) or "").strip() or None
    def dt(k):  return val(k)  # DATE fields: HTML date input gives YYYY-MM-DD

    try:
        if existing:
            execute("""
                UPDATE conductores SET
                    Nombre=?, Apellido=?, FechaNacimiento=?, DniTipo=?, DniNumero=?,
                    Telefono=?, Domicilio=?, Mail=?, NumeroLicencia=?,
                    VencimientoLicencia=?, EmitidaPor=?, Categoria=?, IdOperario=?
                WHERE IdReserva=?
            """, [
                val("nombre"), val("apellido"), dt("fecha_nacimiento"),
                val("dni_tipo"), val("dni_numero"), val("telefono"),
                val("domicilio"), val("mail"), val("numero_licencia"),
                dt("vencimiento_licencia"), val("emitida_por"), val("categoria"),
                id_op, id_reserva,
            ])
        else:
            execute("""
                INSERT INTO conductores
                    (IdReserva, Nombre, Apellido, FechaNacimiento, DniTipo, DniNumero,
                     Telefono, Domicilio, Mail, NumeroLicencia, VencimientoLicencia,
                     EmitidaPor, Categoria, IdOperario)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                id_reserva, val("nombre"), val("apellido"), dt("fecha_nacimiento"),
                val("dni_tipo"), val("dni_numero"), val("telefono"),
                val("domicilio"), val("mail"), val("numero_licencia"),
                dt("vencimiento_licencia"), val("emitida_por"), val("categoria"),
                id_op,
            ])
    except pyodbc.ProgrammingError as e:
        msg = _parse_truncation(e)
        if not msg:
            raise
        # Re-render con los valores que escribió el operador y mensaje claro
        conductor_form = {
            "Nombre":              form.get("nombre", ""),
            "Apellido":            form.get("apellido", ""),
            "FechaNacimiento":     form.get("fecha_nacimiento", ""),
            "DniTipo":             form.get("dni_tipo", "") or "DNI",
            "DniNumero":           form.get("dni_numero", ""),
            "Telefono":            form.get("telefono", ""),
            "Domicilio":           form.get("domicilio", ""),
            "Mail":                form.get("mail", ""),
            "NumeroLicencia":      form.get("numero_licencia", ""),
            "VencimientoLicencia": form.get("vencimiento_licencia", ""),
            "EmitidaPor":          form.get("emitida_por", ""),
            "Categoria":           form.get("categoria", ""),
        }
        return _render(request, id_reserva, conductor_form, {}, error=msg)

    return RedirectResponse(f"/planilla/{id_reserva}?ok=conductor", status_code=303)
