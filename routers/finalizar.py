import os, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from database import query
from utils import ahora_arg

log = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
SMTP_HOST  = "smtp.gmail.com"
SMTP_PORT  = 465
SMTP_USER  = "info@abarentacar.com.ar"
SMTP_PASS  = os.environ.get("SMTP_PASSWORD", "")
DEST_EMAIL = "fvenanti@gmail.com"


def flag_path(id_reserva: int) -> str:
    return os.path.join(UPLOAD_DIR, str(id_reserva), "finalizado.flag")


def reserva_finalizada(id_reserva: int) -> bool:
    return os.path.isfile(flag_path(id_reserva))


def _html_email(nombre: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0">
 <tr><td align="center" style="padding:20px 0;">
  <table width="600" cellpadding="0" cellspacing="0" style="background:white;">

   <!-- Logo -->
   <tr><td align="center" style="padding:30px 0 20px;">
    <img src="https://opr.aba.benvert.com.ar/static/logo.png" alt="ABA Rent a Car" width="150" style="display:block;margin:0 auto;">
   </td></tr>

   <!-- Subtitle -->
   <tr><td align="center" style="padding:0 40px 20px;">
    <p style="font-size:18px;color:#333;text-align:center;margin:0;line-height:1.5;">
     Agencia de <strong>alquiler de autos</strong>, 4x4 y Vans ubicada<br>en San Carlos de Bariloche
    </p>
   </td></tr>

   <!-- Separator -->
   <tr><td style="padding:0 40px;">
    <hr style="border:none;border-top:2px solid #4a7c59;margin:0 0 25px;">
   </td></tr>

   <!-- Body -->
   <tr><td style="padding:0 40px 35px;">
    <p style="color:#4a7c59;font-size:15px;line-height:1.7;margin:0 0 18px;">
     Buenos días {nombre}. Esperamos que hayas tenido una agradable estadía.
     Te agradecemos el habernos elegido para acompañar tu experiencia, y esperamos
     que vuelvas a contar con nosotros en un próximo viaje.
    </p>
    <p style="color:#4a7c59;font-size:15px;margin:0 0 10px;">Muchas gracias!</p>
    <p style="color:#4a7c59;font-size:15px;margin:0 0 10px;">Saludos cordiales</p>
    <p style="color:#4a7c59;font-size:15px;margin:0;">El Equipo de ABA.</p>
   </td></tr>

   <!-- Footer oscuro -->
   <tr><td style="background:#3a5a40;padding:30px 40px;text-align:center;">
    <p style="color:white;font-size:16px;font-weight:bold;margin:0 0 15px;">¿TENÉS ALGUNA DUDA? CONSULTANOS:</p>
    <p style="color:#ccc;font-size:13px;margin:6px 0;">CENTRAL: <a href="tel:+5429444431413" style="color:#7fc97f;text-decoration:none;">+54 294 443 1413</a></p>
    <p style="color:#ccc;font-size:13px;margin:6px 0;">WHATSAPP: <a href="tel:+5492944394706" style="color:#7fc97f;text-decoration:none;">+54 9 294 439 4706</a></p>
    <p style="color:#ccc;font-size:13px;margin:6px 0;">E-MAIL: <a href="mailto:info@abarentacar.com.ar" style="color:#7fc97f;text-decoration:none;">info@abarentacar.com.ar</a></p>
    <p style="margin:22px 0 0;">
     <a href="https://www.abarentacar.com.ar"
        style="background:white;color:#3a5a40;padding:11px 28px;border-radius:25px;text-decoration:none;font-weight:bold;font-size:13px;">
      VISITÁ NUESTRO SITIO WEB
     </a>
    </p>
   </td></tr>

   <!-- Footer bottom -->
   <tr><td align="center" style="padding:18px 40px;background:#f0f0f0;">
    <p style="color:#888;font-size:11px;margin:0;">ABA Rent a Car</p>
    <p style="color:#888;font-size:11px;margin:5px 0;">
     Este e-mail ha sido enviado desde
     <a href="mailto:info@abarentacar.com.ar" style="color:#4a7c59;">info@abarentacar.com.ar</a>
    </p>
    <p style="color:#888;font-size:11px;margin:0;">Copyright &copy; 2015-2018 ABA CAR S.R.L., All Rights Reserved.</p>
   </td></tr>

  </table>
 </td></tr>
</table>
</body>
</html>"""


@router.get("/{id_reserva}/finalizar-reserva")
async def finalizar(request: Request, id_reserva: int):
    rows = query("SELECT Nombre FROM conductores WHERE IdReserva = ?", [id_reserva])
    nombre = (rows[0]["Nombre"] or "Cliente") if rows else "Cliente"

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = f"ABA Rent a Car <{SMTP_USER}>"
        msg["To"]      = DEST_EMAIL
        msg["Subject"] = f"Contrato finalizado - Reserva {id_reserva}"
        msg.attach(MIMEText(_html_email(nombre), "html", "utf-8"))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as srv:
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, DEST_EMAIL, msg.as_string())

        fp = flag_path(id_reserva)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write(ahora_arg().isoformat())

        return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&ok=finalizado", status_code=303)
    except Exception as e:
        log.error("Error finalizando reserva %d: %s", id_reserva, e, exc_info=True)
        return RedirectResponse(f"/planilla/{id_reserva}?tipo=IN&error=finalizar_fallo", status_code=303)
