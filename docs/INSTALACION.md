# Guía de instalación — sala de computación

Esta guía instala Local Via en las computadoras de la sala. Una de ellas cumple además el rol de **hub**: es el servidor central al que se conectan los estudiantes y que reparte los pedidos. Todas las computadoras con GPU, incluida la del hub, corren el **agente**, que procesa los pedidos.

```text
Estudiantes (navegador) ──HTTPS──▶ Hub (aula-pc-01) ◀──HTTPS saliente── Agente en cada PC (aula-pc-01 … aula-pc-16)
```

Los agentes nunca reciben conexiones: son ellos los que se conectan al hub para pedir trabajo. En las PCs del laboratorio no se abre ningún puerto, salvo el del hub en `aula-pc-01`. La guía usa nombres como `aula-pc-01` y 16 PCs de ejemplo; la cantidad de PCs no tiene límite fijo.

## 0. Antes de empezar

Para cada computadora hace falta:

| Requisito | Detalle |
|---|---|
| Sistema | Windows 10/11 de 64 bits, con una cuenta local que pueda ejecutar tareas programadas |
| GPU | NVIDIA con driver actualizado (todas iguales en esta sala) |
| Disco | Unos 250 GB libres para los modelos, preferentemente en un disco secundario |
| Software | Git y Anaconda o Miniconda en todas las PCs; en el hub, además, Python 3.11 o 3.12 y Node.js LTS, que se instalan con conda (ver [sección 1](#1-hub-una-sola-vez-en-aula-pc-01)). **No** hace falta el CUDA Toolkit ni instalar WanGP a mano |

Datos de red que hay que pedirle a TI de la universidad:

1. **Nombre o IP fija del hub** (por ejemplo `aula-pc-01` / `10.20.30.11`). El hub necesita una IP estable: si la PC recibe la IP por DHCP, pedir una reserva para ella.
2. **Subred del laboratorio** (por ejemplo `10.20.30.0/24`). Solo desde ahí se aceptan agentes y el panel de administración. Se puede sacar de `ipconfig`: con IP `10.20.30.11` y máscara `255.255.255.0`, la subred es `10.20.30.0/24`. En la PC del hub, `.\scripts\check-prereqs.ps1 -Role hub` la calcula y muestra los valores para el instalador.
3. **Tipo de red de Windows en el hub:** tiene que ser *Dominio* o *Privada*. La regla de firewall del hub no vale en redes *Públicas*: con la red como Pública, ni los estudiantes ni las otras PCs pueden conectarse. Se ve con `Get-NetConnectionProfile`, y `check-prereqs.ps1 -Role hub` avisa si es Pública.
4. **Opción de acceso para estudiantes:**
   - **Opción A (red de la universidad o VPN):** la subred o el pool de la VPN desde donde se conectarán los estudiantes (por ejemplo `10.8.0.0/16`).
   - **Opción B (Cloudflare Tunnel):** un dominio administrado en Cloudflare y la decisión de usar Cloudflare Access.
5. **Certificado TLS (recomendado):** si TI puede emitir un certificado para el nombre del hub con la CA institucional, los navegadores no muestran advertencias. Si no, el instalador genera uno autofirmado.

Todos los comandos de esta guía se ejecutan en **Anaconda PowerShell Prompt abierto como Administrador** (menú Inicio → clic derecho → *Ejecutar como administrador*). Hay que usar esa consola porque el instalador de WanGP usa conda.

Clonar el repositorio en **la misma ruta en todas las PCs** (por ejemplo `D:\local-via`) y habilitar los scripts para esa consola:

```powershell
git clone https://github.com/mneuronico/local-via.git D:\local-via
cd D:\local-via
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Si `git` "no se reconoce como nombre de un cmdlet", falta Git: `conda install -y git` en esa misma consola. También se puede usar el instalador de https://git-scm.com, y después hay que cerrar y volver a abrir la consola. `winget install --id Git.Git -e` funciona en algunas PCs, pero en otras falla con `0x8a15000f`.

Si el repositorio ya estaba clonado, traer la última versión antes de cada paso:

```powershell
git pull
```

### Revisar requisitos

```powershell
.\scripts\check-prereqs.ps1             # PC con GPU
.\scripts\check-prereqs.ps1 -Role hub   # PC que hará de hub
```

El script no cambia nada. Para cada requisito (Git, conda, driver de NVIDIA, espacio en disco, acceso a GitHub, PyPI y Hugging Face, permisos de Administrador y, en el hub, versión de Python, Node.js, tipo de red y dirección) muestra `[OK]`, `[AVISO]` (funciona, pero conviene corregirlo) o `[FALTA]`, junto con cómo resolverlo. Los instaladores hacen la misma revisión al empezar y se detienen antes de tocar nada si falta algo.

### Instalar WanGP en cada PC con GPU

Se puede hacer antes de tener el hub:

```powershell
.\scripts\install-wangp.ps1
```

Descarga WanGP en `.runtime\Wan2GP` y crea su propio entorno de conda (`env_conda`); la primera vez tarda entre 15 y 30 minutos. Siempre instala la misma versión de WanGP, la que se usó para probar el catálogo (parámetro `-WanGPCommit`), así todas las PCs quedan iguales aunque WanGP publique versiones nuevas. Si una instalación se cortó a la mitad, volver a ejecutar el script rehace el entorno. Al terminar verifica que WanGP arranque e informa cuántos modelos del catálogo reconoce y cuántos ya están descargados. Los modelos se descargan aparte (ver [Descarga inicial de modelos](#descarga-inicial-de-modelos-en-la-primera-pc)).

### Logs

Cada script guarda todo lo que hace, incluida la salida de git, pip y npm, en `logs\<script>-<fecha>.log`. Los tokens se reemplazan por `<oculto>` y las contraseñas nunca pasan por el log. Si algo falla, el script muestra la ruta del archivo que hay que mandar a quien ayude con la instalación.

## 1. Hub (una sola vez, en `aula-pc-01`)

Abrir Anaconda PowerShell Prompt **como Administrador**. El hub se probó con Python 3.11 y 3.12, pero las versiones actuales de Anaconda traen uno más nuevo (3.14). Por eso, el hub se instala desde un entorno de conda con Python 3.12, que además trae Node.js para compilar la interfaz:

```powershell
conda create -y -n localvia-hub python=3.12 nodejs
conda activate localvia-hub
cd D:\local-via
git pull
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\check-prereqs.ps1 -Role hub
```

El entorno `localvia-hub` solo se usa para instalar: el hub corre después con su propio `.venv`. La salida de `check-prereqs.ps1` incluye la línea `Dirección de esta PC` con los valores para `-HostNames` y `-LabSubnet`.

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

`-StudentNetworks` es obligatorio en la opción A. Para una primera prueba solo dentro del laboratorio, se puede pasar la misma subred del laboratorio y agregar las redes de estudiantes después, cambiando solo la regla de firewall:

```powershell
Set-NetFirewallRule -DisplayName "Local Via Hub" -RemoteAddress 10.20.30.0/24, 10.8.0.0/16
```

No volver a ejecutar `install-hub.ps1` para eso: genera un certificado nuevo, y los agentes, que confían en el anterior, dejan de conectarse hasta que se les copie el nuevo `hub.crt`.

Al terminar, el script comprueba que el hub responda y muestra `El hub responde en el puerto 8443`. Si en cambio dice que no responde, sugiere cómo ejecutarlo en primer plano para ver el error.

Comprobación: desde otra PC del laboratorio, abrir `https://aula-pc-01:8443`. Con el certificado autofirmado, el navegador muestra una advertencia la primera vez; se acepta y debe aparecer la pantalla de ingreso. Si no carga, revisar que el tipo de red del hub no sea Público (ver [sección 0](#0-antes-de-empezar)).

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

En el hub, una vez por PC. Cada token se muestra **una sola vez**: guardar la salida hasta haber instalado todos los agentes.

```powershell
.venv\Scripts\python.exe -m hub.cli add-worker aula-pc-01
```

Para registrar todas de una vez (acá, 16) y guardar los tokens en un archivo:

```powershell
1..16 | ForEach-Object { .venv\Scripts\python.exe -m hub.cli add-worker ("aula-pc-{0:D2}" -f $_) } | Tee-Object tokens.txt
```

El nombre es solo una etiqueta para el panel; puede ser el nombre real de cada PC. `tokens.txt` da acceso a los pedidos de los estudiantes: borrarlo cuando todas las PCs estén conectadas. También se puede registrar cada PC desde **Administración → Computadoras → Registrar**.

## 3. Agente en cada PC (todas, incluida `aula-pc-01`)

1. Copiar `hub\certs\hub.crt` del hub a la PC, por ejemplo con un pendrive o una carpeta compartida. **Nunca copiar `hub.key`.**
2. Modelos: la primera PC descarga los modelos desde Hugging Face (~240 GB para el catálogo completo; ver [Descarga inicial de modelos](#descarga-inicial-de-modelos-en-la-primera-pc)). Para no repetir esa descarga en cada PC, las demás los copian de la primera, con `-ModelSource` (ver [Compartir los modelos](#compartir-los-modelos-entre-las-pcs)).
3. En Anaconda PowerShell Prompt como Administrador, con la última versión del repositorio (`git pull`):

   ```powershell
   .\scripts\install-worker.ps1 -HubUrl https://aula-pc-01:8443 -Token <token de esta PC> -CaFile D:\hub.crt -ModelSource \\aula-pc-01\local-via-ckpts
   ```

   Sin `-ModelSource`, el agente queda conectado pero sin modelos, y el hub no le manda pedidos hasta que los tenga.

El script instala WanGP (si no estaba), copia los modelos, escribe `worker\.env` (legible solo por la cuenta que corre el agente) y registra la tarea **Local Via Worker**. Después espera hasta 90 segundos y muestra los primeros mensajes del agente: lo normal es ver `Conectado al hub`. Si en su lugar aparece `El hub rechazó al worker`, el token es incorrecto; `Sin conexión con el hub` indica un problema de red, firewall o certificado.

En `aula-pc-01` usar también `-HubUrl https://aula-pc-01:8443` (o `https://localhost:8443`).

Comprobación: en **Administración → Sala** la computadora aparece como *libre*, con su GPU y la cantidad de modelos instalados. El hub solo le asigna pedidos de modelos que esa PC tiene instalados.

### Descarga inicial de modelos en la primera PC

Con WanGP ya instalado (`.\scripts\install-wangp.ps1`):

```powershell
.runtime\Wan2GP\env_conda\python.exe scripts\smoke_wangp_model.py z_image
```

`smoke_wangp_model.py <modelo>` descarga lo que falte de ese modelo y hace una generación mínima de prueba. Ejecutarlo para cada modelo que se vaya a habilitar en clase. **Ojo:** es carga real de GPU; hacerlo de a un modelo y vigilando la temperatura. Hacerlo en una sola PC: bajar los modelos en todas a la vez multiplica la descarga por la cantidad de PCs.

### Compartir los modelos entre las PCs

Los modelos quedan en la carpeta a la que apunta `.runtime\Wan2GP\ckpts`; `install-wangp.ps1` la muestra al terminar (por defecto `.runtime\model-cache\ckpts`). En la PC que los descargó, como Administrador, compartirla en solo lectura:

```powershell
New-SmbShare -Name local-via-ckpts -Path D:\local-via\.runtime\model-cache\ckpts -ReadAccess ([Security.Principal.SecurityIdentifier]"S-1-5-11").Translate([Security.Principal.NTAccount]).Value
```

(`S-1-5-11` es *Usuarios autenticados*; se usa el SID porque el nombre del grupo cambia según el idioma de Windows.) Las demás PCs la usan como `-ModelSource \\aula-pc-01\local-via-ckpts`. Si piden usuario y contraseña, sirve una cuenta de la PC que comparte. También se puede copiar la carpeta a un disco externo y pasar esa ruta, por ejemplo `-ModelSource E:\ckpts`.

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
| Ver qué está haciendo el agente | `logs\worker.log` en esa PC (conexión con el hub, pedidos, errores) |
| Ver el agente en primer plano | Detener la tarea y ejecutar `.runtime\Wan2GP\env_conda\python.exe -m worker` |

Los resultados se borran automáticamente a los 14 días (`LOCALVIA_HUB_RETENTION_DAYS` en `hub\.env`). Respaldar periódicamente `data\hub\hub.db` si se quiere conservar las cuentas.

### Si algo falla

| Mensaje | Qué hacer |
|---|---|
| `git` / `conda` "no se reconoce como nombre de un cmdlet" | Falta instalar ese programa, o la consola no es Anaconda PowerShell Prompt. `.\scripts\check-prereqs.ps1` dice cuál falta |
| "la ejecución de scripts está deshabilitada en este sistema" | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` en esa consola |
| "Ejecutá ... como administrador" / `[FALTA] Administrador` | Cerrar la consola y abrirla con *Ejecutar como administrador* |
| `winget` falla con `0x8a15000f` ("Data required by the source is missing") | Instalar Git con `conda install -y git` desde Anaconda PowerShell Prompt, o desde https://git-scm.com |
| `Invalid build number` / `Invalid wheel filename` en el instalador de WanGP | Pasaba con versiones anteriores de los scripts: `git pull` y volver a ejecutar `.\scripts\install-wangp.ps1` |
| `[AVISO] Python 3.11 o 3.12` en el hub | Instalar desde el entorno `localvia-hub` (ver [sección 1](#1-hub-una-sola-vez-en-aula-pc-01)) |
| `[AVISO] Tipo de red: ... está como Pública` | Pedirle a TI que la red sea de Dominio o Privada; si no, nadie puede conectarse al hub |
| El hub responde en el hub mismo pero no desde otras PCs | Tipo de red Pública, o la PC que intenta conectarse no está en `-LabSubnet` / `-StudentNetworks` |
| Cualquier otro error de un instalador | Mandar el archivo de `logs\` que indica el mensaje final |
| La PC no aparece en Administración → Sala | Ver `logs\worker.log` en esa PC |

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
| `LOCALVIA_WORKER_LOG_FILE` | Archivo de log del agente (por defecto `logs\worker.log`, rota a los 2 MB y guarda 3 anteriores) |
