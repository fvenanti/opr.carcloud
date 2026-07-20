import os
from fastapi.templating import Jinja2Templates
from utils import matricula_display, whatsapp_link, fmt_importe

BASE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

# Uso en templates: {{ v.MATRICULA | matricula }}
templates.env.filters["matricula"] = matricula_display
# Devuelve "" si el número no se puede normalizar; el botón no se dibuja.
templates.env.filters["whatsapp"] = whatsapp_link
# Uso: {{ reserva.Tarifa | importe(reserva.Moneda) }} -> "$ 483.360"
templates.env.filters["importe"] = fmt_importe
