import os, base64, uuid
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates

router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")


@router.get("/{id_reserva}/firmas", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query("SELECT * FROM firmas WHERE IdReserva = ?", [id_reserva])
    firma = rows[0] if rows else {}
    return templates.TemplateResponse("firmas.html", {
        "request":    request,
        "id_reserva": id_reserva,
        "firma":      firma,
        "ok":         request.query_params.get("ok"),
    })


@router.post("/{id_reserva}/firmas")
async def guardar(request: Request, id_reserva: int):
    form = dict(await request.form())
    id_op = request.session.get("id_operario", 0)

    acepta    = 1 if form.get("acepta_terminos") == "Y" else 0
    aclaracion = (form.get("aclaracion") or "").strip() or None
    firma_b64  = (form.get("firma_imagen") or "").strip()

    # Guardar imagen de firma como PNG en disco
    firma_path = None
    if firma_b64 and firma_b64.startswith("data:image"):
        try:
            header, data = firma_b64.split(",", 1)
            img_bytes = base64.b64decode(data)
            carpeta = os.path.join(UPLOAD_DIR, str(id_reserva))
            os.makedirs(carpeta, exist_ok=True)
            nombre = f"firma_{uuid.uuid4().hex[:8]}.png"
            with open(os.path.join(carpeta, nombre), "wb") as f:
                f.write(img_bytes)
            firma_path = f"/uploads/{id_reserva}/{nombre}"
        except Exception:
            firma_path = None

    existing = query("SELECT Id FROM firmas WHERE IdReserva = ?", [id_reserva])

    if existing:
        execute("""
            UPDATE firmas SET AceptaTerminos=?, FirmaImagen=?, Aclaracion=?, IdOperario=?
            WHERE IdReserva=?
        """, [acepta, firma_path, aclaracion, id_op, id_reserva])
    else:
        execute("""
            INSERT INTO firmas (IdReserva, AceptaTerminos, FirmaImagen, Aclaracion, IdOperario)
            VALUES (?,?,?,?,?)
        """, [id_reserva, acepta, firma_path, aclaracion, id_op])

    return RedirectResponse(f"/planilla/{id_reserva}?ok=firma", status_code=303)
