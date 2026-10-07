# Seguridad

Este documento describe qué expone Local Via, a quién, cómo se protege cada parte y cuáles son sus límites conocidos. Está pensado para que el área de sistemas de la universidad pueda evaluarlo junto con el código.

## Resumen

- **Un solo punto de entrada.** Lo único que escucha en la red es el hub (HTTPS, puerto 8443, en una de las PCs). Las otras PCs del laboratorio no abren ningún puerto: su agente hace conexiones **salientes** al hub para pedir trabajo.
- **Sin servicios externos en funcionamiento.** No hay telemetría ni APIs de terceros. Los modelos de IA se descargan de Hugging Face una sola vez, durante la instalación. En la opción B, el tráfico de los estudiantes pasa por Cloudflare.
- **Cuentas individuales.** Cada estudiante ve y descarga solo sus propios pedidos. La administración solo se usa desde la red del laboratorio.
- **Datos de vida corta.** Los archivos y pedidos se borran solos a los 14 días (configurable). Las PCs que generan no guardan nada de los estudiantes.

## Superficie de red

| Componente | Escucha | Quién se conecta | Protección |
|---|---|---|---|
| Hub (`python -m hub`) | TCP 8443, HTTPS | Navegadores de estudiantes; agentes del laboratorio | TLS; firewall de Windows limitado a las redes declaradas; login; token por agente |
| Agente (`python -m worker`) | Nada | — (sale hacia el hub) | Verifica el certificado del hub (`LOCALVIA_WORKER_CA_FILE`) |
| `cloudflared` (solo opción B) | Nada | — (sale hacia Cloudflare) | Túnel saliente; Cloudflare Access delante del hub |

### Opción A — campus o VPN

El firewall del hub acepta el puerto 8443 solo desde la subred del laboratorio y desde las redes que indique TI (por ejemplo el pool de direcciones de la VPN). Nada queda expuesto a Internet.

### Opción B — Cloudflare Tunnel

`cloudflared` abre una conexión saliente hacia Cloudflare. Los estudiantes entran por un hostname público protegido por **Cloudflare Access** (por ejemplo, código de un solo uso enviado al correo institucional). Antes de llegar a la pantalla de ingreso de Local Via, que exige su propia contraseña, hay que pasar por Access. El hub reconoce los pedidos que llegan por el túnel (conexión desde loopback con los encabezados que agrega Cloudflare) y para ellos:

- **rechaza el panel de administración**, que solo funciona desde la red del laboratorio;
- **rechaza la API de agentes**, aunque se presente un token válido.

Cloudflare termina TLS en su red, así que ve el contenido del tráfico (prompts y archivos). Si eso no es aceptable para la universidad, corresponde usar la opción A.

## Autenticación y sesiones

| Aspecto | Implementación |
|---|---|
| Cuentas | Locales, en la base SQLite del hub. Sin login institucional. |
| Alta de estudiantes | (1) Código de clase con vencimiento, cupo y revocación, o (2) cuentas creadas en lote por administración, con contraseñas aleatorias |
| Contraseñas | `scrypt` (N=2¹⁴, r=8, p=1, sal aleatoria de 16 bytes). Mínimo 8 caracteres. La consola exige 12 para las cuentas de administración y las contraseñas generadas por el sistema son aleatorias. |
| Sesión | Token aleatorio de 256 bits en una cookie `HttpOnly`, `SameSite=Strict`, `Secure` y con prefijo `__Host-` cuando hay HTTPS. En la base solo se guarda su SHA-256. Vence a las 12 h. |
| Fuerza bruta | 5 intentos fallidos por usuario y 20 por IP cada 15 min. Los intentos con usuarios inexistentes tardan lo mismo que los reales. 10 códigos de clase inválidos por IP cada 15 min. |
| Revocación | Cerrar sesión, deshabilitar o borrar un usuario, o cambiar o restablecer su contraseña invalida sus sesiones. |
| Auditoría | Ingresos, ingresos fallidos, altas, cambios de política, tokens de agentes y cancelaciones hechas por administración quedan registrados con fecha, actor e IP. Se conservan 1 año. |

## Autorización

- **Estudiante:** solo sus pedidos, sus archivos subidos y sus resultados. Un pedido no puede referenciar archivos de otra cuenta. Las rutas de archivos usan identificadores aleatorios (UUID v4) y además verifican el dueño.
- **Administración:** todo lo anterior, más usuarios, clases, agentes, política de modelos y auditoría. Solo desde `LOCALVIA_HUB_ADMIN_NETWORKS` y nunca a través del túnel.
- **Agente:** autenticado con un token propio de 256 bits (en la base se guarda su SHA-256), que se puede rotar o revocar. Solo desde `LOCALVIA_HUB_WORKER_NETWORKS` o loopback. Un agente solo puede descargar las entradas y subir resultados **del pedido que tiene asignado en ese momento**.

## Protección de la aplicación web

- **CSRF:** toda modificación exige el encabezado `X-LocalVia: 1`, que un sitio ajeno no puede enviar sin un *preflight* CORS. El hub no responde *preflights* ni habilita CORS. También se rechazan pedidos con `Sec-Fetch-Site` de otro sitio, y la cookie es `SameSite=Strict`.
- **Encabezados:** `Content-Security-Policy` (solo el mismo origen; `frame-ancestors 'none'`; `object-src 'none'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cross-Origin-Opener-Policy` y `Cross-Origin-Resource-Policy`, y HSTS en HTTPS.
- **Archivos generados:** se sirven con `Content-Security-Policy: sandbox` y solo con extensiones de imagen, video o audio de una lista blanca. SVG y HTML nunca se aceptan como resultado.
- **Archivos subidos:**
  - tamaño máximo por archivo (200 MB) y cuota por estudiante (2 GB);
  - fragmentos de 8 MB en orden y con límite de bytes;
  - el tipo se verifica leyendo la firma binaria del archivo (JPEG, PNG, WebP, GIF, MP4/MOV, WebM/MKV, WAV, MP3, FLAC, OGG, M4A), no el tipo que declara el navegador;
  - en disco se guardan con nombre aleatorio; el nombre original es solo un dato descriptivo.
- **Parámetros de generación:** lista blanca de claves, tipos simples y límites que fija la administración (resolución, frames, pasos, duración, cantidad). El prompt admite hasta 4000 caracteres.
- **Tamaño de pedidos:** los cuerpos JSON tienen un máximo de 1 MB.
- **Errores:** no se exponen trazas ni la documentación automática de la API (`/docs` y `/openapi.json` están deshabilitados).

## Datos y retención

| Dato | Dónde | Cuánto tiempo |
|---|---|---|
| Usuario, nombre visible, hash de contraseña, clase | `data\hub\hub.db` (hub) | Hasta que se borre la cuenta |
| Prompts, parámetros y estado de pedidos | `hub.db` | 14 días desde que terminan |
| Archivos subidos y resultados | `data\hub\uploads`, `data\hub\outputs` (hub) | 14 días; se borran antes si el pedido o la cuenta se borra |
| IP de inicio de sesión | `hub.db` (sesiones y auditoría) | Sesión: 12 h. Auditoría: 1 año |
| Archivos en las PCs que generan | Carpeta temporal del agente | Se borran al terminar cada pedido |

No se envía información a terceros, salvo el paso por Cloudflare en la opción B.

## Integridad del procesamiento

- Cada PC procesa un pedido a la vez. El hub asigna un pedido de forma atómica (transacción SQLite `BEGIN IMMEDIATE`), así que dos PCs no pueden tomar el mismo pedido.
- Si una PC deja de enviar señales durante 90 s, su pedido vuelve al frente de la cola. Tras 2 intentos se marca como fallido.
- El agente no acepta trabajo nuevo con la GPU a 85 °C o más (configurable).

## Límites conocidos

- **`script-src 'unsafe-inline'`:** la interfaz es un export estático de Next.js, que inserta scripts de arranque en línea. El resto de la política de contenido es estricta y la aplicación no inserta HTML de usuario.
- **Sin segundo factor ni login institucional** en Local Via. En la opción B, Cloudflare Access puede cubrir ese rol.
- **Certificado autofirmado** si TI no provee uno: los navegadores muestran una advertencia hasta que se confía en `hub.crt`. Lo recomendable es un certificado de la CA institucional (`-TlsCertFile`/`-TlsKeyFile`).
- **El hub es un punto único:** si la PC del hub se apaga, la sala deja de funcionar hasta que vuelva. La base SQLite admite un solo proceso de hub.
- **Sin moderación de contenido:** los modelos generan lo que se les pide dentro de sus propios filtros. El uso queda bajo las normas de la cátedra; la auditoría y el historial permiten revisar quién pidió qué durante el período de retención.
- **Sin antivirus integrado:** las entradas se validan por tipo, pero no se escanean. Pueden quedar cubiertas por el antivirus institucional del equipo hub.
- **Código de terceros:** WanGP y los modelos (formato `safetensors`) corren con los permisos de la cuenta del agente. Conviene usar una cuenta local sin privilegios de administración.

## Recomendaciones para TI

1. Laboratorio en una VLAN propia; desde las redes de estudiantes, solo el puerto 8443 del hub.
2. Certificado TLS emitido por la CA institucional para el nombre del hub.
3. Cuentas locales sin privilegios para las tareas **Local Via Hub** y **Local Via Worker**. Los scripts las registran con la cuenta que los ejecuta, con `RunLevel Limited`.
4. Después de descargar los modelos, bloquear la salida a Internet de las PCs del laboratorio, excepto la de `cloudflared` en la opción B.
5. Respaldar `data\hub\hub.db` si se quieren conservar las cuentas entre cuatrimestres.
6. Revisar periódicamente **Administración → Auditoría** y rotar los tokens de agentes si una PC se reinstala o cambia de manos.

## Verificación

- `hub/tests/test_hub.py`: autenticación, CSRF, cookies, límite de intentos, aislamiento entre estudiantes, validación de archivos y parámetros, restricciones de red para agentes y administración, comportamiento por el túnel, cancelación, PCs caídas, retención.
- `worker/tests/test_agent.py`: agente real contra el hub real (entradas, cancelación, errores, limpieza).
- `e2e/studio.spec.ts`: recorrido completo en navegador con hub y agente reales (backend simulado).
- Dependencias revisadas con `npm audit` y `pip-audit` el 7 de octubre de 2026.

El detalle de cada verificación, con resultados y cómo repetirla, está en [PRUEBAS.md](PRUEBAS.md).

## Reporte de vulnerabilidades

Escribir a la persona responsable del repositorio en lugar de abrir un *issue* público.
