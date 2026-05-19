import os, secrets, httpx, logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from database import query
from shared_templates import templates

log = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v3/userinfo"
SCOPES = "openid email profile"

def _client_id():     return os.environ.get("GOOGLE_CLIENT_ID", "")
def _client_secret(): return os.environ.get("GOOGLE_CLIENT_SECRET", "")

def _redirect_uri(request: Request) -> str:
    hardcoded = os.environ.get("REDIRECT_URI", "")
    if hardcoded:
        return hardcoded
    proto = request.headers.get("x-forwarded-proto", "http")
    host  = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    return f"{proto}://{host}/auth/callback"


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_email"):
        return RedirectResponse("/hojas-ruta")
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error":   request.query_params.get("error"),
        "email":   request.query_params.get("email", ""),
    })


@router.get("/auth/google")
async def auth_google(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    params = {
        "client_id":     _client_id(),
        "redirect_uri":  _redirect_uri(request),
        "response_type": "code",
        "scope":         SCOPES,
        "state":         state,
        "access_type":   "online",
        "prompt":        "select_account",
    }
    url = GOOGLE_AUTH_URL + "?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/auth/callback")
async def auth_callback(request: Request):
    state_recibido = request.query_params.get("state", "")
    state_guardado = request.session.pop("oauth_state", None)
    if not state_guardado or state_recibido != state_guardado:
        return RedirectResponse("/login?error=state_invalido")

    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/login?error=sin_codigo")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code":          code,
            "client_id":     _client_id(),
            "client_secret": _client_secret(),
            "redirect_uri":  _redirect_uri(request),
            "grant_type":    "authorization_code",
        })

    if token_resp.status_code != 200:
        log.error("TOKEN FAIL %s — redirect_uri=%s — body=%s",
                  token_resp.status_code, _redirect_uri(request), token_resp.text)
        return RedirectResponse("/login?error=token_fallido")

    access_token = token_resp.json().get("access_token")

    async with httpx.AsyncClient() as client:
        info_resp = await client.get(
            GOOGLE_USERINFO,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if info_resp.status_code != 200:
        return RedirectResponse("/login?error=userinfo_fallido")

    info  = info_resp.json()
    email = (info.get("email") or "").lower().strip()

    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "").lower().strip()

    if email == ADMIN_EMAIL:
        request.session["user_email"]  = email
        request.session["user_nombre"] = info.get("name") or email
        request.session["user_id"]     = 0
        request.session["id_operario"] = 0
        next_url = request.session.pop("next_url", "/hojas-ruta")
        if not next_url or next_url in ("/", "/login") or next_url.startswith("/static"):
            next_url = "/hojas-ruta"
        return RedirectResponse(next_url)

    # Verificar que el email esté en opr.operarios (default schema = opr)
    rows = query(
        "SELECT Id, IdOperario, Activo FROM operarios WHERE Mail = ? AND Activo = 1",
        [email],
    )
    if not rows:
        return RedirectResponse(f"/login?error=no_autorizado&email={email}")

    op = rows[0]

    # Obtener nombre del operario desde dbo.tbl_operario
    nombre_rows = query(
        "SELECT Nombre FROM dbo.tbl_operario WHERE Id = ?",
        [op["IdOperario"]],
    )
    nombre = nombre_rows[0]["Nombre"] if nombre_rows else (info.get("name") or email)

    request.session["user_email"]    = email
    request.session["user_nombre"]   = nombre
    request.session["user_id"]       = int(op["Id"])
    request.session["id_operario"]   = int(op["IdOperario"])

    next_url = request.session.pop("next_url", "/hojas-ruta")
    if not next_url or next_url in ("/", "/login") or next_url.startswith("/static"):
        next_url = "/hojas-ruta"
    return RedirectResponse(next_url)


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
