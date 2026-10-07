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

**Pendiente de validar en la sala:** la regla de firewall y las tareas programadas, porque requieren Administrador en las PCs reales. También la opción B con un túnel real de Cloudflare y el acceso por la VPN de la universidad.

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
