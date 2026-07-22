import os, re
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import pyodbc
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from routers import auth, hojas_ruta, planilla, conductor, adicionales, pagos, entregas, firmas, recepcion, contrato, comanda, finalizar, vehiculos, clientes, reservas, vuelos, lavados, taller
import uvicorn

app = FastAPI(title="CarCloud OPR", version="1.3")

BASE = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(hojas_ruta.router, prefix="/hojas-ruta", tags=["HojasRuta"])
app.include_router(planilla.router,   prefix="/planilla",   tags=["Planilla"])
app.include_router(conductor.router,  prefix="/planilla",   tags=["Conductor"])
app.include_router(adicionales.router, prefix="/planilla",  tags=["Adicionales"])
app.include_router(pagos.router,      prefix="/planilla",   tags=["Pagos"])
app.include_router(entregas.router,   prefix="/planilla",   tags=["Entregas"])
app.include_router(firmas.router,     prefix="/planilla",   tags=["Firmas"])
app.include_router(recepcion.router,  prefix="/planilla",   tags=["Recepcion"])
app.include_router(contrato.router,   prefix="/planilla",   tags=["Contrato"])
app.include_router(comanda.router,    prefix="/planilla",   tags=["Comanda"])
app.include_router(finalizar.router,  prefix="/planilla",   tags=["Finalizar"])
app.include_router(taller.router,     prefix="/planilla",   tags=["Taller"])
app.include_router(vuelos.router,     prefix="/planilla",   tags=["Vuelos"])
app.include_router(vehiculos.router,  prefix="/vehiculos",  tags=["Vehiculos"])
app.include_router(lavados.router,    prefix="/lavados",    tags=["Lavados"])
app.include_router(clientes.router,   prefix="/clientes",   tags=["Clientes"])
app.include_router(reservas.router,   prefix="/reservas",   tags=["Reservas"])

# ── Manejo global de errores de truncamiento de SQL Server ────────────────────
_COL_LABELS = {
    "Telefono": "Teléfono", "Mail": "Mail", "Domicilio": "Domicilio",
    "Nombre": "Nombre", "Apellido": "Apellido",
    "DniTipo": "DNI Tipo", "DniNumero": "DNI Número",
    "NumeroLicencia": "Número de Licencia", "EmitidaPor": "Emitida por",
    "Categoria": "Categoría", "Observaciones": "Observaciones",
    "Concepto": "Concepto", "TipoPago": "Tipo de Pago", "Moneda": "Moneda",
}

@app.exception_handler(pyodbc.ProgrammingError)
async def handle_pyodbc_error(request: Request, exc: pyodbc.ProgrammingError):
    msg = str(exc)
    if "would be truncated" not in msg:
        raise exc
    col_m = re.search(r"column '([^']+)'", msg)
    val_m = re.search(r"Truncated value:\s*'([^']*)'", msg)
    col   = col_m.group(1) if col_m else "un campo"
    label = _COL_LABELS.get(col, col)
    val   = (val_m.group(1) if val_m else "")
    extra = f'<br><span class="text-gray-500 text-sm">Valor: "{val}"</span>' if val else ""
    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Campo muy largo</title>
<script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center p-4">
<div class="bg-white rounded-2xl shadow-lg max-w-md w-full p-6 text-center">
  <div class="w-16 h-16 mx-auto bg-red-50 rounded-full flex items-center justify-center mb-4">
    <svg class="w-8 h-8 text-red-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
    </svg>
  </div>
  <h1 class="text-lg font-bold text-gray-900 mb-2">Campo demasiado largo</h1>
  <p class="text-gray-700 text-sm mb-1">El campo <strong>"{label}"</strong> excede el tamaño máximo permitido.</p>
  {extra}
  <p class="text-gray-600 text-sm mt-4">Volvé atrás, acortá ese campo y guardá de nuevo.</p>
  <button onclick="history.back()" class="mt-6 w-full bg-red-600 text-white font-semibold rounded-xl py-3 active:bg-red-700">
    Volver
  </button>
</div></body></html>"""
    return HTMLResponse(html, status_code=400)


@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/hojas-ruta")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse("/static/icon-192.png")

# ── Auth middleware ────────────────────────────────────────────────────────────
RUTAS_PUBLICAS = {"/login", "/auth/google", "/auth/callback", "/favicon.ico"}

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (path in RUTAS_PUBLICAS
                or path.startswith("/static")
                or path.startswith("/uploads")):
            return await call_next(request)
        if not request.session.get("user_email"):
            request.session["next_url"] = path
            return RedirectResponse("/login")
        return await call_next(request)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET", "dev-secret-cambiar"),
    https_only=False,
    max_age=86400 * 7,  # 7 días
)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8003))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
