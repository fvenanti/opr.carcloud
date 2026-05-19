import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from routers import auth, hojas_ruta, planilla, conductor, adicionales, pagos, entregas, firmas, recepcion, contrato
import uvicorn

app = FastAPI(title="CarCloud OPR", version="1.0")

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
