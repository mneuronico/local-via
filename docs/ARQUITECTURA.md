# Arquitectura

```text
                ┌─────────────── Opción A: campus / VPN ───────────────┐
 Estudiantes ───┤                                                      ├──▶  HUB  (una de las PCs, HTTPS :8443)
 (navegador)    └── Opción B: Cloudflare Access ─▶ Cloudflare Tunnel ──┘     ├─ interfaz web (export estático de Next.js)
                                                                             ├─ cuentas, sesiones, cola global, política
                                                                             ├─ SQLite + archivos (data\hub)
                                                                             └─ API de agentes (/worker-api)
                                                                                   ▲  ▲  ▲   conexiones SALIENTES
                                                                                   │  │  │   (HTTPS, token por PC)
                                                              Agente PC-01 ────────┘  │  └──────── Agente PC-08
                                                              (WanGP + GPU)       Agente PC-02 …
```

## Piezas

| Carpeta | Qué es | Dónde corre |
|---|---|---|
| `hub/` | Servidor central FastAPI: cuentas, cola, despacho, archivos, administración. También sirve la interfaz. | Una PC (Python 3.11/3.12, `.venv`) |
| `worker/` | Agente que pide trabajo al hub y lo ejecuta con WanGP. No abre puertos. | Cada PC con GPU (Python de WanGP) |
| `app/`, `components/`, `lib/` | Interfaz web (Next.js 16, exportada como archivos estáticos en `out/`) | Navegador del estudiante |
| `scripts/` | Instalación en Windows, sala simulada, medición de ancho de banda | — |

## Flujo de un pedido

1. El estudiante inicia sesión (cookie de sesión `HttpOnly`) y elige modalidad, modelo y parámetros.
2. Si hay archivos de entrada, el navegador los sube al hub en fragmentos de 8 MB. El hub verifica tamaño, cuota y tipo real del contenido.
3. `POST /api/jobs`: el hub valida modelo, tarea, parámetros y límites, y que el estudiante no tenga otro pedido en curso. Después encola el pedido.
4. Cada agente libre tiene abierta una consulta larga `POST /worker-api/claim` (hasta 20 s). El hub le asigna, en una transacción, el pedido más antiguo que esa PC puede correr porque tiene el modelo instalado. Si la PC ya tiene cargado en VRAM el modelo de un pedido algo posterior (dentro de una ventana de 5 min), prefiere ese, para evitar unos 3 minutos de carga.
5. El agente descarga las entradas, ejecuta WanGP e informa progreso cada 5 s. Cada informe renueva su permiso de 90 s y le avisa si el estudiante canceló.
6. El agente sube el resultado (`PUT /worker-api/jobs/{id}/artifacts`), cierra el pedido y borra todo lo local.
7. Mientras tanto, el navegador consulta `GET /api/state` cada 2,5 s si tiene un pedido en curso y cada 10 s si no; nunca con la pestaña oculta. La respuesta lleva `ETag`: si nada cambió, el hub responde `304` sin cuerpo. Incluye la posición en la cola y una estimación de espera.

## Cola y estimaciones

- Cola **FIFO global**, con un pedido en curso por estudiante (`LOCALVIA_HUB_MAX_ACTIVE_JOBS_PER_USER`). Así nadie acapara la sala.
- La espera estimada simula la cola sobre las PCs conectadas. Para cada modelo usa la mediana de las últimas 20 duraciones reales; mientras no hay historial, usa 2 min para imagen, 15 min para video y 3 min para audio.
- Si una PC deja de reportar durante 90 s, su pedido vuelve al frente de la cola. Si un agente se reinicia, libera su pedido anterior al volver a pedir trabajo. Después de 2 intentos, el pedido falla con un mensaje claro.

## Estados

`queued → running → succeeded | failed | cancelled`

Fases visibles: `queued`, `requeued`, `dispatched`, `downloading_inputs`, `loading`, `loading_model`, `encoding_text`, `inference`, `decoding`, `uploading_output`, `cancelling`, `complete`.

## API

**Estudiantes** (`/api`, cookie de sesión + encabezado `X-LocalVia: 1` en las modificaciones):

| Método y ruta | Uso |
|---|---|
| `POST /api/auth/login`, `/api/auth/register`, `/api/auth/logout` | Sesión; el registro requiere código de clase |
| `GET /api/session`, `GET /api/me`, `POST /api/me/password` | Cuenta |
| `GET /api/catalog` | Modelos habilitados y disponibles en la sala |
| `GET /api/state` | Pedidos propios, posición en cola y estado de la sala (con `ETag`) |
| `POST /api/uploads`, `PUT /api/uploads/{id}/chunks/{n}`, `POST /api/uploads/{id}/complete` | Subida en fragmentos |
| `POST /api/jobs`, `POST /api/jobs/{id}/cancel`, `DELETE /api/jobs/{id}` | Pedidos |
| `GET /api/files/{id}` (`?download=1`) | Resultado (solo su dueño o administración) |

**Administración** (`/api/admin/...`): `overview`, `users`, `users/bulk`, `classes`, `workers` (alta, rotación y baja de tokens), `jobs/{id}/cancel`, `policy`, `audit`.

**Agentes** (`/worker-api`, `Authorization: Bearer <token de la PC>`): `claim`, `jobs/{id}/inputs/{upload}`, `jobs/{id}/progress`, `jobs/{id}/artifacts`, `jobs/{id}/complete`.

## Almacenamiento

- `data\hub\hub.db`: SQLite en modo WAL, con usuarios, sesiones, clases, agentes, pedidos, archivos, auditoría y política.
- `data\hub\uploads\<usuario>\<id>.bin` y `data\hub\outputs\<pedido>\<id>.<ext>`.
- Una tarea interna de mantenimiento corre cada 5 s (permisos vencidos) y cada hora (retención, sesiones vencidas, subidas abandonadas).

## Pruebas

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest hub\tests worker\tests -q   # 38 tests de Python
npm ci; npm run lint; npm run typecheck; npm run build
npx playwright test                                            # 6 recorridos en navegador
```

`scripts\dev_classroom.py` levanta una sala simulada completa (hub + N agentes sin GPU) para desarrollo, pruebas y la medición de ancho de banda.

Resultados de todas las verificaciones (tests, recorridos en navegador, prueba de carga, generación real con GPU, instaladores, TLS y dependencias): ver [PRUEBAS.md](PRUEBAS.md).

## Dependencias

| Componente | Paquetes fijados |
|---|---|
| Hub | `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `cryptography` (ver `hub/requirements.txt`) |
| Agente | `httpx`, `pydantic-settings`, `nvidia-ml-py` (ya incluidos en el entorno de WanGP) |
| Interfaz | `next`, `react`, `react-dom`, `lucide-react`, fuentes `@fontsource` (ver `package.json`) |

Revisión del 7 de octubre de 2026:

- `npm audit --omit=dev`: **0 vulnerabilidades** en lo que llega al navegador.
- `pip-audit` sobre el entorno del hub: **0 vulnerabilidades**.
- En herramientas de desarrollo queda un aviso en `braces`, que llega a través de `eslint-config-next` y no forma parte de lo que se instala en la sala.

Para repetirla: `npm audit --omit=dev` y `.venv\Scripts\python.exe -m pip_audit`.

## WanGP

Local Via integra [WanGP](https://github.com/deepbeepmeep/Wan2GP) como motor de generación y lo indica en la interfaz y en la documentación, como piden los términos de su API. El agente usa la API de Python de WanGP (`shared.api`) dentro del entorno que instala `scripts/install-wangp.ps1`. Para probar sin GPU existe un backend simulado (`LOCALVIA_WORKER_BACKEND=mock`).
