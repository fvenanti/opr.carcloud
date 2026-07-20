# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es

**CarCloud OPR** — app de operaciones de campo de ABA Rent a Car (Bariloche). La usan los operarios desde el celular para procesar entregas y devoluciones de vehículos: hoja de ruta del día, planilla de reserva, fotos del vehículo, firma del cliente, generación y envío del contrato en PDF.

Es una PWA instalable (`static/manifest.json`), server-rendered, pensada mobile-first. El service worker es mínimo y **no cachea**: la app requiere conexión.

## Comandos

**No hay tests, linter ni formatter en el repo.** No inventes comandos de test; si necesitás verificar un cambio, corré la app o consultá prod.

### Deploy

Push a `dev` dispara el deploy automático (`.github/workflows/deploy.yml`): GitHub Actions entra por SSH a la EC2, hace `git pull --ff-only` y `docker compose up -d --build`. Tarda ~2 min.

```bash
git push origin dev                                          # deploy automático
gh workflow run deploy.yml --repo fvenanti/opr.carcloud      # deploy manual
gh run list --repo fvenanti/opr.carcloud --limit 3           # estado
gh run watch <run-id> --repo fvenanti/opr.carcloud           # seguir en vivo
```

**`dev` es la rama de producción.** No hay staging: lo que se pushea a `dev` va a los operarios.

### Operar la EC2

```bash
SSH="ssh -i ~/.ssh/ClaveCarCloudABACAR.pem ubuntu@98.88.118.221"

$SSH "docker logs carcloud-opr --tail 100"
$SSH "cd /home/ubuntu/opr && git log --oneline -1"     # qué commit corre en prod
$SSH "docker restart carcloud-opr"
```

El código en prod vive en `/home/ubuntu/opr`. La EC2 hostea varias apps más — **operá sólo sobre `carcloud-opr` y esa carpeta.**

### Correr en local

En la práctica no se hace. Requiere SQL Server accesible, ODBC Driver 18, LibreOffice y un `.env` con credenciales reales. El flujo de trabajo normal es editar y pushear a `dev`.

Si aun así hace falta: `python main.py` levanta uvicorn con reload en `:8003` (`PORT` lo cambia).

## Arquitectura

### Stack

FastAPI + Jinja2 server-rendered. Sin framework de frontend: Tailwind por CDN y JS vanilla inline en los templates. SQL Server por `pyodbc` con SQL crudo — no hay ORM ni migraciones.

### Base de datos: dos dominios

Este es el punto clave para no romper nada. La app convive con un sistema legacy (CarCloud) sobre la misma base:

| Dominio | Objetos | Trato |
|---|---|---|
| **Legacy CarCloud** (schema `dbo`) | `vw_AppSheet_Reservas`, `vw_AppSheet_Clientes`, `vw_AppSheet_Vehiculos`, `vw_AppSheet_Movimientos`, `tbl_operario`, `alquileres`, `Autos`, `tbl_marcas`, `tbl_Modelos`, `Conceptos` | **Sólo lectura**, salvo casos puntuales. Son la fuente de verdad de reservas, clientes y flota. |
| **Propio de OPR** | `conductores`, `adicionales`, `pagos`, `entregas`, `recepciones`, `firmas`, `opr.mails_enviados`, `opr.lavados` | Lectura y escritura libres. Todas se vinculan por `IdReserva`. |

Las columnas legacy tienen espacios y puntos en el nombre (`[Fecha Salida]`, `[Sucursales.Sucursal]`, `[Status_Reserva.Descripcion]`). Van entre corchetes y **siempre aliasadas** a un nombre limpio en el SELECT, porque los templates consumen el alias.

`database.py` expone `query()`, `execute()` y `execute_scalar()`. Abren y cierran conexión en cada llamada — no hay pool. Los params van siempre como lista posicional (`?`), nunca interpolados.

### El modelo OUT / IN

Todo gira alrededor de que una reserva genera **dos movimientos**: la salida del vehículo (`OUT`) y su devolución (`IN`). Las listas de hoja de ruta hacen `UNION ALL` sobre `[Fecha Salida]` y `[Fecha Entrada]` de la misma vista para producir ambos.

El tipo se pasa por query param (`?tipo=OUT`); si falta, `planilla.py` lo infiere comparando contra la fecha de hoy. Qué secciones se muestran depende del tipo **y** del estado de la reserva: `OUT` requiere estado "Confirmada", `IN` requiere "Efectiva".

### La planilla como hub

`/planilla/{id_reserva}` es el centro de la app. `routers/planilla.py` hace una query por sección para calcular flags `tiene_conductor`, `tiene_entrega`, `tiene_firma`, etc., y el template pinta el checklist de progreso.

Cada sección es **su propio router montado bajo el mismo prefijo `/planilla`** (ver `main.py`): `conductor`, `adicionales`, `pagos`, `entregas`, `firmas`, `recepcion`, `contrato`, `comanda`, `finalizar`, `taller`, `vuelos`. Todos siguen el mismo patrón: `GET` renderiza el form con lo que haya en la tabla, `POST` guarda y redirige a `/planilla/{id}?ok=...` con status 303.

**Para agregar una sección**: router nuevo + template + registrarlo en `main.py` + agregar su flag `tiene_X` en `planilla.py` y el bloque correspondiente en `templates/planilla.html`.

### Estado en disco, no sólo en DB

Ojo con esto, es fácil de pasar por alto. Parte del estado vive en el filesystem, bajo `uploads/{id_reserva}/`:

- **`finalizado.flag`** — marca que la reserva se finalizó. `finalizar.reserva_finalizada()` chequea que el archivo exista; las hojas de ruta lo usan para pintar el badge de "procesado" de los movimientos `IN`.
- **Fotos** de entrega y recepción, y la **firma** del cliente.
- **`contrato.pdf`** generado.

Consecuencia: **`uploads/` no se puede borrar ni recrear** — no es caché, es estado. Son ~2 GB en prod, está en `.gitignore` y no existe en los clones locales. Se monta como volumen en `docker-compose.yml`.

Para los movimientos `OUT`, el equivalente al flag es tener una fila en `opr.mails_enviados` (o que el estado de la reserva ya sea "Efectiva"/"Finalizada").

### Generación del contrato

`routers/contrato.py` es el módulo más pesado (~630 líneas). El pipeline:

1. `_build_context()` arma un dict con todos los datos de la reserva
2. `_fill_docx()` reemplaza placeholders en la plantilla DOCX del repo con `python-docx`, inserta fotos inline, la firma, y expande la tabla de pagos fila por fila
3. `_to_pdf()` convierte con **LibreOffice headless** — por eso el Dockerfile instala `libreoffice-writer` y la imagen pesa ~860 MB
4. `_send_email()` manda el PDF adjunto por SMTP (Gmail, `info@abarentacar.com.ar`) y registra el envío en `opr.mails_enviados`

La plantilla es el `.docx` en la raíz del repo. Si cambian los placeholders del documento, hay que actualizar `_process_text()` y `_FOTO_PARA_MAP` en paralelo.

### Auth

Google OAuth con sesión en cookie firmada. `AuthMiddleware` en `main.py` intercepta todo salvo `RUTAS_PUBLICAS`, `/static` y `/uploads`; sin sesión guarda el path en `next_url` y redirige a `/login`.

La autorización es una whitelist contra la base: el email de Google tiene que existir en `dbo.tbl_operario` con `Activo = 1`. El `ADMIN_EMAIL` del `.env` entra sin estar en la tabla, con `id_operario = 0`.

### Fotos

Se comprimen **en el cliente** antes de subir (`static/foto-resize.js`): lado mayor 1600px, JPEG calidad 0.85, y sólo si el archivo supera 1.5 MB. Reemplaza el `FileList` del input. Es lo que hace usable la carga desde el celular en el campo.

En el server se guardan con nombre `{id_reserva}_{key}_{uuid8}.ext` bajo `uploads/{id_reserva}/`, y en la tabla se persiste la URL pública (`/uploads/...`), no la ruta de disco.

## Convenciones

**Zona horaria** — nunca `datetime.now()` ni `date.today()` pelados. Usá `utils.ahora_arg()` y `utils.hoy_arg()`, que fijan `America/Argentina/Buenos_Aires`. El server corre en UTC y las hojas de ruta se rompen si se mezcla.

**Errores de truncamiento** — `main.py` tiene un `exception_handler` global para `pyodbc.ProgrammingError` que convierte los "would be truncated" de SQL Server en una página amigable que nombra el campo. Si agregás una columna de texto con límite, sumá su label a `_COL_LABELS`.

**Changelog** — `templates/base.html` tiene un "Historial de versiones" visible en el menú de usuario. Al agregar features al usuario, sumá la entrada ahí y mantené sincronizado el `version=` de `FastAPI(...)` en `main.py`. Son dos lugares y se desincronizan fácil.

**Idioma** — código, rutas, mensajes de UI y commits en español. Los nombres de tablas y columnas propias también.

**Redirect tras POST** — siempre 303 a `/planilla/{id}?ok=...`, nunca renderizar el resultado directo.

## Infraestructura

`docker-compose.yml` usa **`network_mode: host`**: el container escucha directo en el `:8003` del host, sin mapeo de puertos. Es así porque necesita llegar a SQL Server en `localhost:1433`. Por eso `docker ps` no muestra puertos publicados para `carcloud-opr`.

Nginx (`nginx/opr-aba-benvert`, instalado en la EC2) termina `opr.aba.benvert.com.ar` y proxea a `127.0.0.1:8003`, con `client_max_body_size 25M` para las fotos.

Config por `.env` en la raíz (gitignored, sólo existe en la EC2). Variables que lee el código: `DB_SERVER`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `REDIRECT_URI`, `ADMIN_EMAIL`, `SESSION_SECRET`, `SMTP_PASSWORD`, `UPLOAD_DIR`, `AERODATABOX_KEY`, `DEBUG_EMAIL_OVERRIDE`, `PORT`.

`.claude/settings.local.json` quedó de la máquina de desarrollo anterior: tiene paths de Windows y permisos para deployar por `scp`/`rsync`. Está obsoleto — el deploy es por GitHub Actions desde que existe el workflow.
