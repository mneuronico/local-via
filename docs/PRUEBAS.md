# Pruebas y verificaciones

Todo lo que se verificó antes de entregar, con su resultado y cómo repetirlo. Fecha: **7 de octubre de 2026**.

## Resumen

| Verificación | Resultado |
|---|---|
| Tests automáticos de Python (hub + agente) | ✅ 38/38 |
| Recorridos en navegador (Playwright) con hub y agente reales | ✅ 6/6 |
| Lint, tipos y build de la interfaz | ✅ sin errores |
| Prueba de carga: 40 estudiantes × 3 pedidos, 8 PCs | ✅ 120/120, sin duplicados ni solapamientos |
| Generación real con GPU a través del hub y el agente | ✅ Z-Image en RTX 2060: 2:37 en frío, 0:41 con el modelo cargado |
| Instaladores (hub y agente) en una copia limpia | ✅ partes que no requieren Administrador |
| TLS: el agente rechaza un hub con un certificado ajeno | ✅ |
| Medición de ancho de banda con navegadores reales | ✅ ver [ANCHO_DE_BANDA.md](ANCHO_DE_BANDA.md) |
| Vulnerabilidades conocidas en dependencias que se instalan | ✅ 0 (`npm audit --omit=dev`, `pip-audit`) |

## 1. Tests automáticos

```powershell
.venv\Scripts\python.exe -m pytest hub\tests worker\tests -q
```

**[`hub/tests/test_hub.py`](../hub/tests/test_hub.py)** (26 tests) cubre:
- **Sesiones:** login, cookie `HttpOnly`/`SameSite=Strict` (`Secure` y `__Host-` en HTTPS), cierre de sesión y límite de intentos.
- **Registro:** códigos de clase, incluidos el vencimiento y el cupo.
- **Protección de pedidos:** encabezado CSRF obligatorio y rechazo de pedidos que vienen de otro sitio.
- **Aislamiento entre estudiantes:** no pueden ver, cancelar ni descargar lo ajeno, ni usar archivos ajenos.
- **Archivos subidos:** tamaño, orden de los fragmentos, tipo real por firma binaria, cuota.
- **Validación de pedidos:** modelo y tarea, parámetros fuera de la lista blanca, límites de resolución y pasos, un pedido en curso por estudiante, modelos deshabilitados.
- **Cola:** orden de llegada, posición y espera estimada, respuestas `304` cuando nada cambió.
- **Agentes:**
  - token por PC y redes permitidas;
  - rechazo por el túnel;
  - cada PC recibe solo modelos que tiene instalados;
  - preferencia por el modelo ya cargado;
  - una PC que deja de responder devuelve el pedido a la cola y, tras 2 intentos, el pedido falla;
  - una PC reiniciada libera su pedido anterior;
  - la cancelación llega a la PC;
  - una PC no puede tocar pedidos de otra.
- **Administración:** usuarios en lote, deshabilitar, tokens de PCs, política, auditoría; restricción de red y bloqueo por el túnel.
- **Retención:** el borrado automático elimina los pedidos y archivos vencidos.

**[`worker/tests/test_agent.py`](../worker/tests/test_agent.py)** (3 tests): un agente real (backend simulado) contra el hub real por HTTP. Prueba un pedido con archivo de entrada, la cancelación en curso y la propagación de errores, y verifica que la PC no conserve archivos.

**[`worker/tests/test_backends.py`](../worker/tests/test_backends.py)** (9 tests): adaptador de WanGP (orden de referencias, variantes Lightning y Turbo, descarga del modelo por inactividad).

## 2. Recorridos en navegador

```powershell
npm run build; npx playwright test
```

[`e2e/studio.spec.ts`](../e2e/studio.spec.ts) levanta un hub real con un agente simulado y usa la interfaz como un estudiante:

1. registro con código de clase, generación, ver el resultado, y que no aparezcan pedidos de otra persona;
2. con la PC ocupada, el pedido muestra *Puesto N en la cola* y el botón queda bloqueado hasta terminar;
3. subida de una imagen y edición imagen → imagen;
4. un archivo que no es imagen se rechaza;
5. administración: computadoras, códigos de clase, registro de una PC, deshabilitar un modelo (y el rechazo correspondiente para estudiantes), auditoría;
6. un estudiante no puede usar la API de administración, y sin sesión no hay acceso.

En todos los recorridos se verifica además que el navegador no registre errores ni respuestas fallidas.

## 3. Prueba de carga

```powershell
.venv\Scripts\python.exe scripts\load_test.py --students 40 --jobs 3 --workers 8 --mock-seconds 3
```

[`scripts/load_test.py`](../scripts/load_test.py): 40 estudiantes en paralelo por la API HTTP real, cada uno con 3 pedidos seguidos, contra 8 PCs simuladas.

| Verificación | Resultado |
|---|---|
| Pedidos completados | 120 de 120, todos en el primer intento |
| Pedidos procesados dos veces | 0 |
| PCs con dos pedidos a la vez | 0 |
| Reparto | 15 pedidos por PC |
| Orden | FIFO, sin saltos de cola |
| Rendimiento | 142 pedidos/min (máximo teórico 160) |
| Cada estudiante ve solo sus pedidos | Verificado en cada consulta |

## 4. Generación real con GPU

Hub y agente reales, con el backend WanGP (v12.51) en una NVIDIA GeForce RTX 2060 de 12 GB. Pedidos enviados por la API como cualquier estudiante: Z-Image Turbo 6B, 512×512, 8 pasos.

| Pedido | Tiempo total | Temperatura máxima de la GPU | Resultado |
|---|---:|---:|---|
| 1º, en frío (carga del modelo incluida) | 2:37 | 65 °C | JPEG de 61,6 kB, correcto |
| 2º, con el modelo ya cargado | 0:41 | 74 °C | Correcto |

Desglose del primero, según las fases que el agente informó al hub: carga del modelo ~1:25, interpretación del prompt ~0:35, generación ~0:30, entrega ~0:05.

Además se verificó que:
- el hub registró qué modelo quedó cargado en la PC, que es lo que usa para preferirla;
- la PC no conservó ninguna entrada ni ningún resultado al terminar.

Los demás modelos del catálogo se probaron directamente con WanGP en esta misma GPU: ver [MODEL_COMPATIBILITY.md](MODEL_COMPATIBILITY.md) y [MODEL_BENCHMARKS.md](MODEL_BENCHMARKS.md). El agente usa exactamente el mismo adaptador.

## 5. Instaladores y TLS

En una copia limpia del repositorio:

- [`scripts/install-hub.ps1`](../scripts/install-hub.ps1) con `-SkipFirewall -SkipTask -SkipAdmin`: creó el entorno, el certificado con los nombres indicados y `hub\.env`. La clave privada quedó legible solo por la cuenta actual, Administradores y SYSTEM.
- [`scripts/install-worker.ps1`](../scripts/install-worker.ps1) con backend simulado y `-SkipTask`: creó `worker\.env` (legible solo por la cuenta actual) y copió el certificado.
- El hub instalado arrancó en HTTPS con HSTS, CSP y `X-Frame-Options`. El agente instalado se conectó **verificando el certificado del hub**.
- Con otro certificado, el agente **rechazó la conexión** (`CERTIFICATE_VERIFY_FAILED`). Sin el certificado, un cliente HTTPS común también la rechaza.

Durante esta prueba se encontró y corrigió un problema: si la computadora tiene el mismo nombre que el usuario de Windows, el nombre de la cuenta es ambiguo. Los scripts ahora asignan permisos por SID.

Revisión de requisitos y logs (después de un primer intento de instalación en la sala, en una PC sin Git):

- [`scripts/check-prereqs.ps1`](../scripts/check-prereqs.ps1) en la PC de desarrollo: detectó GPU, driver, Git, conda, espacio libre y acceso a GitHub, PyPI y Hugging Face. Sin Administrador, marcó `[FALTA] Administrador` para el rol hub.
- Simulando la PC de la sala (PATH sin Git, conda ni Python), `install-wangp.ps1` listó los tres `[FALTA]` con su solución y se detuvo antes de cambiar nada, con código de salida 1.
- Un `git clone` que falla dentro de `install-worker.ps1` → `install-wangp.ps1` dejó la salida de git y el error en un solo log, informado una sola vez.
- `install-wangp.ps1` sobre una instalación existente: verificó WanGP (15 de 15 modelos reconocidos y descargados).
- El token que se pasa a `install-worker.ps1` no queda en el log (el encabezado de la transcripción lo repite; se reemplaza por `<oculto>`).
- El agente escribe `logs\worker.log` con `Agente iniciado` y `Conectado al hub`; si el archivo no se puede escribir, sigue funcionando y lo avisa por consola.

Durante esta prueba se encontró y corrigió un problema: en Windows PowerShell, un mensaje de git por stderr detenía el script aunque se redirigiera con `2>$null`.

Primer intento real en la sala: el instalador de WanGP falló al instalar SpargeAttention (`Invalid build number`). Hubo dos causas:

1. **WanGP sin versión fija.** El script clonaba la última versión de WanGP (18.21, publicada el día anterior) y no la probada (89a77e3).
2. **URLs rotas por `conda run`.** WanGP instala con `conda run`, que en Windows pasa por un `.bat`. Ahí `%2B` (un `+` codificado en la URL) se convierte en `B`. En la RTX 2060 de desarrollo no aparecía porque ese perfil no instala SpargeAttention; la 18.21 tiene además otras URLs con `%2B` que afectan a todos los perfiles NVIDIA.

Corrección en `install-wangp.ps1`:

- WanGP queda fijado en 89a77e3.
- Durante la instalación, las URLs con `%2B` se reemplazan por `+`, que GitHub acepta. Se comprobó que las 13 descargas de Windows de esa versión responden.
- Un entorno a medio hacer se reconstruye al volver a ejecutar el script.

Se simuló la PC de la sala (WanGP 18.21 clonado y `env_conda` incompleto). El script pasó a 89a77e3, detectó el entorno incompleto, ajustó la configuración y la restauró al terminar.

La instalación completa en esa simulación encontró un tercer problema, que la verificación final detectó: aun con WanGP fijado, pip instala la última versión de las dependencias sin versión fija. `tensordict` 0.15 (posterior a las pruebas) exige torch 2.11 o más nuevo, y pip reemplazó torch 2.10 con CUDA por torch 2.14 sin CUDA. Unos 150 paquetes quedaron en versiones distintas a las probadas.

Corrección: [`scripts/wangp-constraints.txt`](../scripts/wangp-constraints.txt) tiene las versiones exactas del entorno probado y se le pasa a cada llamada de pip del instalador (`PIP_CONSTRAINT`). Quedan afuera solo los núcleos de atención que WanGP elige según la generación de la GPU (SageAttention, SpargeAttention, lightx2v). Esto también fija `triton-windows` en la versión probada.

**Pendiente:** una instalación completa con las restricciones; la prueba se detuvo antes de terminar. Mientras tanto, en la primera PC de la sala WanGP 18.21 se instaló a mano: se reemplazó `%2B` por `+` en `setup_config.json` y se volvió a correr el script anterior. La verificación reconoció los 15 modelos, y `smoke_wangp_model.py z_image` generó una imagen. Hubo que cambiar a mano una ruta fija a `N:\` en ese script, que ahora usa `data\smoke` cuando no hay disco N:. En esa PC el script nuevo deja WanGP 18.21 como está, porque ya funciona, y solo avisa que no es la versión probada.

**Pendiente de validar en la sala:** la regla de firewall y las tareas programadas, porque requieren Administrador en las PCs reales. Eso incluye la espera de los primeros mensajes del agente en `install-worker.ps1` y la comprobación del puerto en `install-hub.ps1`. También la opción B con un túnel real de Cloudflare y el acceso por la VPN de la universidad.

## 6. Ancho de banda

Ver [ANCHO_DE_BANDA.md](ANCHO_DE_BANDA.md): navegadores reales por HTTPS, bytes contados en la red, archivos reales generados en la RTX 2060, 1 y 12 estudiantes simultáneos.

## 7. Dependencias

| Comando | Resultado |
|---|---|
| `npm audit --omit=dev` (lo que llega al navegador) | 0 vulnerabilidades |
| `pip-audit` sobre el entorno del hub | 0 vulnerabilidades |

Durante el trabajo se actualizaron Next.js (16.3.0 → 16.4.0, que tenía avisos críticos), Starlette (0.47.3 → 1.7.0), FastAPI, Uvicorn y cryptography a versiones sin vulnerabilidades conocidas. En herramientas de desarrollo queda un aviso en `braces`, a través de `eslint-config-next`, que no se instala en la sala.

## Qué no se probó todavía

- Las 8 PCs físicas del laboratorio a la vez. La prueba de carga usó 8 agentes simulados en una sola máquina.
- La red, el firewall y la VPN reales de la universidad.
- Modelos de video pesados a través del agente con GPU real. Con el agente se probó Z-Image; los modelos de video se probaron con WanGP directamente.
