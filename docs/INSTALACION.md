# Guía de instalación — sala de computación

Esta guía instala Local Via en las computadoras de la sala. Una de ellas cumple además el rol de **hub**: es el servidor central al que se conectan los estudiantes y que reparte los pedidos. Todas las computadoras con GPU, incluida la del hub, corren el **agente**, que procesa los pedidos.

```text
Estudiantes (navegador) ──HTTPS──▶ Hub (aula-pc-01) ◀──HTTPS saliente── Agente en cada PC (aula-pc-01 … aula-pc-08)
```

Los agentes nunca reciben conexiones: son ellos los que se conectan al hub para pedir trabajo. En las PCs del laboratorio no se abre ningún puerto, salvo el del hub en `aula-pc-01`.

## 0. Antes de empezar

Para cada computadora hace falta:

| Requisito | Detalle |
|---|---|
| Sistema | Windows 10/11 de 64 bits, con una cuenta local que pueda ejecutar tareas programadas |
| GPU | NVIDIA con driver actualizado (todas iguales en esta sala) |
| Disco | Unos 250 GB libres para los modelos, preferentemente en un disco secundario |
| Software | Git, Python 3.11 o 3.12 (solo en el hub, para `.venv`), Node.js LTS (solo para compilar la interfaz) |

Datos de red que hay que pedirle a TI de la universidad:

1. **Nombre o IP fija del hub** (por ejemplo `aula-pc-01` / `10.20.30.11`). El hub necesita una IP estable.
2. **Subred del laboratorio** (por ejemplo `10.20.30.0/24`). Solo desde ahí se aceptan agentes y el panel de administración.
3. **Opción de acceso para estudiantes:**
   - **Opción A (red de la universidad o VPN):** la subred o el pool de la VPN desde donde se conectarán los estudiantes (por ejemplo `10.8.0.0/16`).
   - **Opción B (Cloudflare Tunnel):** un dominio administrado en Cloudflare y la decisión de usar Cloudflare Access.
4. **Certificado TLS (recomendado):** si TI puede emitir un certificado para el nombre del hub con la CA institucional, los navegadores no muestran advertencias. Si no, el instalador genera uno autofirmado.

Clonar el repositorio en **la misma ruta en todas las PCs** (por ejemplo `D:\local-via`):

```powershell
git clone https://github.com/mneuronico/local-via.git D:\local-via
cd D:\local-via
```

## 1. Hub (una sola vez, en `aula-pc-01`)

Abrir PowerShell **como Administrador** en la carpeta del repositorio.

**Opción A — campus o VPN:**

```powershell
.\scripts\install-hub.ps1 -Mode lan -HostNames "aula-pc-01,10.20.30.11" -LabSubnet "10.20.30.0/24" -StudentNetworks "10.8.0.0/16" -AdminUser profe
```

**Opción B — Cloudflare Tunnel:**

```powershell
.\scripts\install-hub.ps1 -Mode tunnel -HostNames "aula-pc-01,10.20.30.11" -LabSubnet "10.20.30.0/24" -AdminUser profe
```

El script:

1. crea el entorno `.venv` con las dependencias del hub y compila la interfaz web (`out\`);
2. genera `hub\certs\hub.crt` y `hub\certs\hub.key` (o usa `-TlsCertFile`/`-TlsKeyFile` si TI entregó un certificado);
3. escribe `hub\.env`;
4. crea la cuenta de administración y pide su contraseña (mínimo 12 caracteres);
5. abre el puerto 8443 en el Firewall de Windows **solo** para la subred del laboratorio y, en la opción A, para las redes de estudiantes;
6. registra la tarea programada **Local Via Hub**, que arranca con Windows y se reinicia sola si falla.

Comprobación: desde otra PC del laboratorio, abrir `https://aula-pc-01:8443`. Debe aparecer la pantalla de ingreso.

### Opción B: publicar con Cloudflare Tunnel

1. En el panel de Cloudflare Zero Trust: **Networks → Tunnels → Create a tunnel** (tipo *Cloudflared*). Copiar el token.
2. En el túnel, **Public Hostname**: por ejemplo `localvia.tu-dominio.edu.ar` → servicio `https://localhost:8443`, y en *Additional settings → TLS* activar **No TLS Verify** (es el certificado del propio hub en la misma máquina).
3. **Access → Applications → Add an application → Self-hosted** para ese hostname. Política recomendada: *Allow* a los correos del dominio institucional, con *One-time PIN* como método de ingreso. Así nadie llega a la pantalla de Local Via sin pasar antes por Cloudflare Access.
4. En el hub, como Administrador:

   ```powershell
   .\scripts\setup-tunnel.ps1 -TunnelToken <token>
   ```

En modo túnel, el hub rechaza el panel de administración y la API de agentes para todo pedido que llegue por el túnel. La administración solo se usa desde la red del laboratorio.

## 2. Registrar cada computadora

En el hub, una vez por PC. El token se muestra **una sola vez**:

```powershell
.venv\Scripts\python.exe -m hub.cli add-worker aula-pc-01
.venv\Scripts\python.exe -m hub.cli add-worker aula-pc-02
# … hasta aula-pc-08
```

También se puede hacer desde **Administración → Computadoras → Registrar**.

## 3. Agente en cada PC (las 8, incluida `aula-pc-01`)

1. Copiar `hub\certs\hub.crt` del hub a la PC, por ejemplo con un pendrive o una carpeta compartida. **Nunca copiar `hub.key`.**
2. Modelos: la primera PC descarga los modelos desde Hugging Face (~240 GB para el catálogo completo). Para no repetir esa descarga 8 veces, compartir la carpeta de modelos de la primera PC (solo lectura) y pasarla como `-ModelSource`.
3. En PowerShell como Administrador:

   ```powershell
   .\scripts\install-worker.ps1 -HubUrl https://aula-pc-01:8443 -Token <token de esta PC> -CaFile D:\hub.crt -ModelSource \\aula-pc-01\local-via-ckpts
   ```

El script instala WanGP (con su propio Python), copia los modelos, escribe `worker\.env` (legible solo por la cuenta que corre el agente) y registra la tarea **Local Via Worker**.

En `aula-pc-01` usar también `-HubUrl https://aula-pc-01:8443` (o `https://localhost:8443`).

Comprobación: en **Administración → Sala** la computadora aparece como *libre*, con su GPU y la cantidad de modelos instalados. El hub solo le asigna pedidos de modelos que esa PC tiene instalados.

### Descarga inicial de modelos en la primera PC

```powershell
.\scripts\install-wangp.ps1
.runtime\Wan2GP\env_conda\python.exe scripts\smoke_wangp_model.py z_image
```

`smoke_wangp_model.py <modelo>` descarga lo que falte de ese modelo y hace una generación mínima de prueba. Ejecutarlo para cada modelo que se vaya a habilitar en clase. **Ojo:** es carga real de GPU; hacerlo de a un modelo y vigilando la temperatura.

## 4. Preparar la clase

En `https://aula-pc-01:8443` con la cuenta de administración:

1. **Modelos y límites:** dejar habilitados solo los modelos que se usarán y ajustar los máximos (resolución, frames, pasos, duración). Con valores altos, un video puede tardar más de 20 minutos y bloquear una PC.
2. **Cuentas de estudiantes**, de una de dos formas:
   - **Clases → Crear código:** se genera un código (por ejemplo `K7QH-M2XP`) con vencimiento y cupo opcional. Cada estudiante crea su cuenta con ese código.
   - **Usuarios → Crear cuentas:** se pega la lista de usuarios y el sistema genera contraseñas para repartir.
3. Recomendar a cada estudiante que cambie su contraseña (ícono de llave en la barra superior).

## 5. Operación diaria

| Tarea | Cómo |
|---|---|
| Ver estado de la sala, la cola y las temperaturas | Administración → Sala |
| Cancelar el pedido de alguien | Administración → Sala → Cancelar |
| Sacar una PC de servicio | Administración → Computadoras → Deshabilitar |
| Una PC se colgó a mitad de un pedido | El hub lo detecta en ~90 s y devuelve el pedido al frente de la cola (hasta 2 intentos) |
| Bloquear a un usuario | Administración → Usuarios → Deshabilitar (cierra sus sesiones) |
| Auditoría | Administración → Auditoría (ingresos, altas, cambios de política) |
| Reiniciar servicios | `Restart-ScheduledTask "Local Via Hub"` / `"Local Via Worker"` (o reiniciar la PC) |
| Ver logs del agente en primer plano | Detener la tarea y ejecutar `.runtime\Wan2GP\env_conda\python.exe -m worker` |

Los resultados se borran automáticamente a los 14 días (`LOCALVIA_HUB_RETENTION_DAYS` en `hub\.env`). Respaldar periódicamente `data\hub\hub.db` si se quiere conservar las cuentas.

## 6. Actualizar

```powershell
Stop-ScheduledTask "Local Via Hub"; Stop-ScheduledTask "Local Via Worker"
git pull
.venv\Scripts\python.exe -m pip install -r hub\requirements.txt
npm ci; npm run build
Start-ScheduledTask "Local Via Hub"; Start-ScheduledTask "Local Via Worker"
```

En las PCs que solo tienen agente, alcanza con `git pull` y reiniciar la tarea **Local Via Worker**.

## 7. Desinstalar

```powershell
.\scripts\uninstall.ps1
```

Quita las tareas programadas y la regla de firewall. Los datos (`data\`) y los modelos se borran a mano.

## Referencia de configuración

`hub\.env`:

| Variable | Valor por defecto | Significado |
|---|---|---|
| `LOCALVIA_HUB_MODE` | `lan` | `lan` (opción A) o `tunnel` (opción B) |
| `LOCALVIA_HUB_PORT` | `8443` | Puerto HTTPS |
| `LOCALVIA_HUB_TLS_CERT_FILE` / `_KEY_FILE` | — | Certificado y clave |
| `LOCALVIA_HUB_WORKER_NETWORKS` | — | Redes desde donde se aceptan agentes (subred del laboratorio) |
| `LOCALVIA_HUB_ADMIN_NETWORKS` | — | Redes desde donde se acepta el panel de administración |
| `LOCALVIA_HUB_MAX_ACTIVE_JOBS_PER_USER` | `1` | Pedidos en curso por estudiante (en cola o generando) |
| `LOCALVIA_HUB_MAX_UPLOAD_MB` | `200` | Tamaño máximo de cada archivo subido |
| `LOCALVIA_HUB_USER_QUOTA_MB` | `2048` | Espacio máximo por estudiante (entradas + resultados) |
| `LOCALVIA_HUB_RETENTION_DAYS` | `14` | Días que se guardan pedidos y archivos |
| `LOCALVIA_HUB_SESSION_HOURS` | `12` | Duración de la sesión |
| `LOCALVIA_HUB_LEASE_SECONDS` | `90` | Tiempo sin señales tras el cual un pedido vuelve a la cola |

`worker\.env`:

| Variable | Significado |
|---|---|
| `LOCALVIA_WORKER_HUB_URL` | URL HTTPS del hub |
| `LOCALVIA_WORKER_TOKEN` | Token de esta PC (generado por `add-worker`) |
| `LOCALVIA_WORKER_CA_FILE` | Certificado del hub que el agente debe aceptar |
| `LOCALVIA_WORKER_BACKEND` | `wangp` (real) o `mock` (pruebas sin GPU) |
| `LOCALVIA_WORKER_MAX_GPU_TEMP_C` | No toma pedidos nuevos con la GPU a esta temperatura o más (por defecto 85 °C) |
