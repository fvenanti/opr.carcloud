import os, uuid, aiofiles
from fastapi import APIRouter, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query, execute
from shared_templates import templates

router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")

FOTOS = {
    "foto_frente_izq": "FotoFrenteIzq",
    "foto_frente_der": "FotoFrenteDer",
    "foto_trasera_izq": "FotoTraseraIzq",
    "foto_trasera_der": "FotoTraseraDer",
    "foto_auxilio":    "FotoAuxilio",
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


@router.get("/{id_reserva}/recepcion", response_class=HTMLResponse)
async def ver(request: Request, id_reserva: int):
    rows = query("SELECT * FROM recepciones WHERE IdReserva = ?", [id_reserva])
    recepcion = rows[0] if rows else {}

    res = query("""
        SELECT [Km Salida] AS KmSalida, [Nafta Salida] AS NaftaSalida,
               Km, [Km adicional] AS KmAdicional, [Monedas.Descripcion] AS Moneda,
               [Sucursales.Sucursal] AS SucursalSalida,
               [Sucursales_1.Sucursal] AS SucursalEntrada
        FROM dbo.vw_AppSheet_Reservas WHERE IdReserva = ?
    """, [id_reserva])
    def _int(v):
        try: return int(v or 0)
        except (ValueError, TypeError): return 0
    def _float(v):
        try: return float(v or 0)
        except (ValueError, TypeError): return 0.0
    km_salida      = _int(res[0]["KmSalida"])      if res else 0
    nafta_salida   = res[0]["NaftaSalida"]          if res else None
    km_libre       = str(res[0]["Km"] or "").upper() == "LIBRES" if res else False
    km_disponible  = _int(res[0]["Km"])             if res else 0
    km_adicional   = _float(res[0]["KmAdicional"])  if res else 0.0
    moneda         = (res[0]["Moneda"] or "Pesos")     if res else "Pesos"
    es_taller      = False
    if res:
        ss = (res[0].get("SucursalSalida")  or "").lower()
        se = (res[0].get("SucursalEntrada") or "").lower()
        es_taller = "taller" in ss or "taller" in se

    if recepcion.get("IdOperario"):
        op = query("SELECT Nombre FROM dbo.tbl_operario WHERE Id = ?", [recepcion["IdOperario"]])
        nombre_op = op[0]["Nombre"] if op else request.session.get("user_nombre", "")
    else:
        nombre_op = request.session.get("user_nombre", "")
    return templates.TemplateResponse("recepcion.html", {
        "request":       request,
        "id_reserva":    id_reserva,
        "recepcion":     recepcion,
        "nombre_op":     nombre_op,
        "km_salida":     km_salida,
        "nafta_salida":  nafta_salida,
        "km_disponible": km_disponible,
        "km_adicional":  km_adicional,
        "moneda":        moneda,
        "km_libre":      km_libre,
        "es_taller":     es_taller,
        "ok":            request.query_params.get("ok"),
    })


@router.post("/{id_reserva}/recepcion")
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

    def val(k):
        return (form.get(k) or "").strip() or None

    def num(k):
        try: return int((form.get(k) or "0").strip())
        except: return 0

    uploads = {
        "foto_frente_izq":  foto_frente_izq,
        "foto_frente_der":  foto_frente_der,
        "foto_trasera_izq": foto_trasera_izq,
        "foto_trasera_der": foto_trasera_der,
        "foto_auxilio":     foto_auxilio,
    }

    existing = query(
        "SELECT Id, FotoFrenteIzq, FotoFrenteDer, FotoTraseraIzq, FotoTraseraDer, FotoAuxilio FROM recepciones WHERE IdReserva = ?",
        [id_reserva],
    )

    foto_paths = {}
    for key, file in uploads.items():
        col = FOTOS[key]
        path = await _guardar_foto(file, id_reserva, key)
        if path:
            foto_paths[col] = path
        elif existing:
            foto_paths[col] = existing[0].get(col)

    if existing:
        execute("""
            UPDATE recepciones SET
                KmEntrada=?, NaftaEntrada=?,
                FotoFrenteIzq=?, FotoFrenteDer=?,
                FotoTraseraIzq=?, FotoTraseraDer=?,
                FotoAuxilio=?, Observaciones=?
            WHERE IdReserva=?
        """, [
            num("km_entrada"), num("nafta_entrada"),
            foto_paths.get("FotoFrenteIzq"), foto_paths.get("FotoFrenteDer"),
            foto_paths.get("FotoTraseraIzq"), foto_paths.get("FotoTraseraDer"),
            foto_paths.get("FotoAuxilio"), val("observaciones"), id_reserva,
        ])
    else:
        execute("""
            INSERT INTO recepciones
                (IdReserva, IdOperario, KmEntrada, NaftaEntrada,
                 FotoFrenteIzq, FotoFrenteDer, FotoTraseraIzq, FotoTraseraDer,
                 FotoAuxilio, Observaciones)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, [
            id_reserva, id_op,
            num("km_entrada"), num("nafta_entrada"),
            foto_paths.get("FotoFrenteIzq"), foto_paths.get("FotoFrenteDer"),
            foto_paths.get("FotoTraseraIzq"), foto_paths.get("FotoTraseraDer"),
            foto_paths.get("FotoAuxilio"), val("observaciones"),
        ])

    return RedirectResponse(f"/planilla/{id_reserva}?ok=recepcion", status_code=303)


@router.post("/{id_reserva}/recepcion/eliminar")
async def eliminar(id_reserva: int):
    execute("DELETE FROM recepciones WHERE IdReserva = ?", [id_reserva])
    return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&ok=eliminado", status_code=303)
