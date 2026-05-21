from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from database import query
from shared_templates import templates
from utils import hoy_arg
from datetime import datetime, date

router = APIRouter()

_CANCELADAS = "('Cancelada', 'Anulada', 'Cancelado', 'Anulado')"

_SQL_TODOS = f"""
SELECT
    v.MATRICULA,
    v.Marca,
    v.Modelo,
    v.[Estado_Vehículo]  AS Estado,
    v.Sucursal,
    v.COMBUSTIBLE        AS Combustible,
    v.UBICACION          AS Ubicacion,
    v.Categoría          AS Categoria,
    r.IdReserva,
    r.[Sucursales.Sucursal]  AS SucursalReserva,
    ISNULL(r.Apellido,'') + CASE WHEN r.Nombre IS NOT NULL THEN ', ' + r.Nombre ELSE '' END AS Cliente,
    nr.ProximaSalida,
    nr.ProximoHorario
FROM dbo.vw_AppSheet_Vehiculos v
OUTER APPLY (
    SELECT TOP 1
        IdReserva,
        [Sucursales.Sucursal],
        Apellido,
        Nombre
    FROM dbo.vw_AppSheet_Reservas
    WHERE MATRICULA = v.MATRICULA
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
      AND CAST(? AS DATE)
          BETWEEN CAST([Fecha Salida] AS DATE) AND CAST([Fecha Entrada] AS DATE)
) r
OUTER APPLY (
    SELECT TOP 1
        CAST([Fecha Salida] AS DATE)  AS ProximaSalida,
        [Horario Salida]              AS ProximoHorario
    FROM dbo.vw_AppSheet_Reservas
    WHERE MATRICULA = v.MATRICULA
      AND [Status_Reserva.Descripcion] NOT IN {_CANCELADAS}
      AND CAST([Fecha Salida] AS DATE) >= CAST(? AS DATE)
    ORDER BY [Fecha Salida]
) nr
ORDER BY v.Sucursal,
         ISNULL(CAST(nr.ProximaSalida AS NVARCHAR(20)), '9999-12-31'),
         v.MATRICULA
"""


def _fmt_fecha(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%d/%m")
    s = str(val)
    if len(s) >= 10 and s[4] == '-':
        return s[8:10] + "/" + s[5:7]
    return s[:10]


def _get_lavado_status(patentes: list[str]) -> dict:
    """Returns dict: MATRICULA -> {'estado': 'Limpio'|'Sucio'|'En lavado', 'id_activo': int|None}"""
    if not patentes:
        return {}

    lavado_rows = query("""
        SELECT
            Patente,
            MAX(CASE WHEN Estado = 'Finalizado' THEN FechaHoraFin END) AS UltimoLavado,
            MAX(CASE WHEN Estado IN ('Pendiente','En proceso') THEN 1 ELSE 0 END) AS TieneActivo,
            MAX(CASE WHEN Estado IN ('Pendiente','En proceso') THEN Id END) AS IdActivo
        FROM opr.lavados
        GROUP BY Patente
    """)
    lav_map = {(r['Patente'] or '').upper(): r for r in lavado_rows}

    rec_rows = query("""
        SELECT res.MATRICULA, MAX(r.FechaCreacion) AS UltimaRecepcion
        FROM recepciones r
        JOIN dbo.vw_AppSheet_Reservas res ON res.IdReserva = r.IdReserva
        WHERE res.MATRICULA IS NOT NULL
        GROUP BY res.MATRICULA
    """)
    rec_map = {r['MATRICULA'].upper(): r['UltimaRecepcion'] for r in rec_rows}

    result = {}
    for mat in patentes:
        key = (mat or '').upper()
        lav = lav_map.get(key)
        if lav and lav['TieneActivo']:
            result[key] = {'estado': 'En lavado', 'id_activo': lav['IdActivo']}
            continue
        ultimo = lav['UltimoLavado'] if lav else None
        ultima_rec = rec_map.get(key)
        if ultimo and (not ultima_rec or ultimo > ultima_rec):
            result[key] = {'estado': 'Limpio', 'id_activo': None}
        else:
            result[key] = {'estado': 'Sucio', 'id_activo': None}
    return result


def _agrupar(vehiculos: list[dict]) -> tuple[list, list, list]:
    alquilados, taller, disponibles = [], [], []
    for v in vehiculos:
        v['ProximaSalidaFmt'] = _fmt_fecha(v.get('ProximaSalida'))
        v['ProximoHorarioFmt'] = str(v.get('ProximoHorario') or '')[:5]
        if v.get("IdReserva") is not None:
            if "taller" in (v.get("SucursalReserva") or "").lower():
                taller.append(v)
            else:
                alquilados.append(v)
        else:
            disponibles.append(v)
    disponibles.sort(key=lambda x: str(x.get('ProximaSalida') or '9999-12-31'))
    return alquilados, taller, disponibles


@router.get("/", response_class=HTMLResponse)
async def lista(request: Request):
    hoy = hoy_arg()
    vehiculos = query(_SQL_TODOS, [hoy.isoformat(), hoy.isoformat()])
    alquilados, taller, disponibles = _agrupar(vehiculos)

    patentes = [v['MATRICULA'] for v in disponibles if v.get('MATRICULA')]
    lavado_status = _get_lavado_status(patentes)
    for v in disponibles:
        key = (v.get('MATRICULA') or '').upper()
        v['LavadoEstado'] = lavado_status.get(key, {}).get('estado', 'Sucio')
        v['LavadoIdActivo'] = lavado_status.get(key, {}).get('id_activo')

    return templates.TemplateResponse("vehiculos_lista.html", {
        "request":     request,
        "alquilados":  alquilados,
        "taller":      taller,
        "disponibles": disponibles,
        "active_tab":  "vehiculos",
    })
