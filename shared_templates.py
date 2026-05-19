import os
from fastapi.templating import Jinja2Templates

BASE = os.path.dirname(__file__)
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))
