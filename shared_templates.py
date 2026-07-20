import os
from fastapi.templating import Jinja2Templates
from utils import matricula_display

BASE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))

# Uso en templates: {{ v.MATRICULA | matricula }}
templates.env.filters["matricula"] = matricula_display
