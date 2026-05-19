import os, uuid, aiofiles
from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates

router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")

FOTOS = ["frente_izq", "frente_der", "trasera_izq", "trasera_der", "auxilio"]
FOTO_COLS = {
    "frente_izq":  "FotoFrenteIzq",
    "frente_der":  "FotoFrenteDer",
    "trasera_izq": "FotoTraseraIzq",
    "trasera_der": "FotoTraseraDer",
    "auxilio":     "FotoAuxilio",
}


async def _guardar_foto(file: UploadFile, id_reserva: int, key: str) -> str | None:
    if not file or not file.filename:
        return None
    ext = os.path.splitext(file.filename)[-1].lower() or ".jpg"
    nombre = f"{id_reserva}_{key}_{uuid.uuid4().hex[:8]}{ext}"
    carpeta = os.path.join(UPLOAD_DIR, str(id_reserva))
    os.makedirs(carpeta, exist_ok=True)
    ruta = os.path.join(carpeta, nombre)
    async with aiofiles.open(ruta, "wb") as f:
        await f.write(await file.read())
    return f"/uploads/{id_reserva}/{nombre}"


@router.get("/{id_reserva}/entregas", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query("SELECT * FROM entregas WHERE IdReserva = ?", [id_reserva])
    entrega = rows[0] if rows else {}
    nombre_op = request.session.get("user_nombre", "")
    return templates.TemplateResponse("entregas.html", {
        "request":    request,
        "id_reserva": id_reserva,
        "entrega":    entrega,
        "nombre_op":  nombre_op,
        "ok":         request.query_params.get("ok"),
    })


@router.post("/{id_reserva}/entregas")
async def guardar(
    request: Request,
    id_reserva: int,
    foto_frente_izq:  UploadFile = File(None),
    foto_frente_der:  UploadFile = File(None),
    foto_trasera_izq: UploadFile = File(None),
    foto_trasera_der: UploadFile = File(None),
    foto_auxilio:     UploadFile = File(None),
):
    form = dict(await request.form())
    id_op = request.session.get("id_operario", 0)

    def val(k):  return (form.get(k) or "").strip() or None
    def boo(k):  return 1 if form.get(k) in ("Y", "1", "true", "on") else 0
    def num(k):
        try: return int((form.get(k) or "0").strip())
        except: return 0

    uploads = {
        "frente_izq":  foto_frente_izq,
        "frente_der":  foto_frente_der,
        "trasera_izq": foto_trasera_izq,
        "trasera_der": foto_trasera_der,
        "auxilio":     foto_auxilio,
    }

    existing = query("SELECT Id, FotoFrenteIzq, FotoFrenteDer, FotoTraseraIzq, FotoTraseraDer, FotoAuxilio FROM entregas WHERE IdReserva = ?", [id_reserva])

    foto_paths = {}
    for key, file in uploads.items():
        path = await _guardar_foto(file, id_reserva, key)
        if path:
            foto_paths[FOTO_COLS[key]] = path
        elif existing:
            foto_paths[FOTO_COLS[key]] = existing[0].get(FOTO_COLS[key])

    if existing:
        execute("""
            UPDATE entregas SET
                KmSalida=?, NaftaSalida=?, KmEntrada=?, NaftaEntrada=?,
                Auxilio=?, SillaBebe=?,
                Cadenas=?, GPS=?, Barras=?, PermisoChile=?, KitSeg=?,
                Video=?,
                FotoFrenteIzq=?, FotoFrenteDer=?, FotoTraseraIzq=?,
                FotoTraseraDer=?, FotoAuxilio=?, Observaciones=?, IdOperario=?
            WHERE IdReserva=?
        """, [
            num("km_salida"), num("nafta_salida"),
            num("km_entrada") or None, num("nafta_entrada") or None,
            boo("auxilio"), num("silla_bebe"),
            boo("cadenas"), boo("gps"), boo("barras"),
            boo("permiso_chile"), boo("kit_seg"),
            boo("video"),
            foto_paths.get("FotoFrenteIzq"), foto_paths.get("FotoFrenteDer"),
            foto_paths.get("FotoTraseraIzq"), foto_paths.get("FotoTraseraDer"),
            foto_paths.get("FotoAuxilio"),
            val("observaciones"), id_op, id_reserva,
        ])
    else:
        execute("""
            INSERT INTO entregas
                (IdReserva, IdOperario, KmSalida, NaftaSalida, KmEntrada, NaftaEntrada,
                 Auxilio, SillaBebe, Cadenas, GPS, Barras, PermisoChile, KitSeg, Video,
                 FotoFrenteIzq, FotoFrenteDer, FotoTraseraIzq,
                 FotoTraseraDer, FotoAuxilio, Observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, [
            id_reserva, id_op,
            num("km_salida"), num("nafta_salida"),
            num("km_entrada") or None, num("nafta_entrada") or None,
            boo("auxilio"), num("silla_bebe"),
            boo("cadenas"), boo("gps"), boo("barras"),
            boo("permiso_chile"), boo("kit_seg"),
            boo("video"),
            foto_paths.get("FotoFrenteIzq"), foto_paths.get("FotoFrenteDer"),
            foto_paths.get("FotoTraseraIzq"), foto_paths.get("FotoTraseraDer"),
            foto_paths.get("FotoAuxilio"), val("observaciones"),
        ])

    return RedirectResponse(f"/planilla/{id_reserva}?ok=entrega", status_code=303)
