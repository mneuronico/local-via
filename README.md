# Local Via

Estudio audiovisual con IA que corre **en las computadoras de una sala de computación**, sin servicios en la nube. Los estudiantes entran desde el navegador, eligen qué generar (imagen, video, voz, sonido o música), y un servidor central (**hub**) reparte cada pedido a la primera PC con GPU que esté libre. Si todas están ocupadas, el pedido espera en una cola visible, con posición y tiempo estimado.

Local Via usa [WanGP](https://github.com/deepbeepmeep/Wan2GP) como motor de generación y lo indica en la interfaz y en esta documentación, como piden los términos de su API.

```text
Estudiantes ──HTTPS──▶ Hub (1 PC) ◀──HTTPS saliente── Agente en cada PC con GPU (8)
                        cuentas · cola · resultados        WanGP · un pedido a la vez
```

## Características

- **Cola global y reparto automático** entre las PCs. Cada PC hace un pedido por vez, y el hub prefiere la PC que ya tiene el modelo cargado en memoria.
- **Cola visible para cada estudiante:** posición, espera estimada con tiempos reales de la sala, progreso y fase.
- **Cuentas individuales:** código de clase o cuentas creadas en lote. Cada estudiante ve solo lo suyo y tiene un pedido en curso a la vez.
- **Panel de administración:**
  - estado de cada PC (GPU, temperatura, modelo cargado);
  - cola y cancelaciones;
  - usuarios, clases y tokens de PCs;
  - modelos habilitados y límites por pedido;
  - auditoría.
- **Tolerancia a fallas:** si una PC se cuelga, su pedido vuelve al frente de la cola. Además, ninguna PC toma trabajo con la GPU demasiado caliente.
- **Dos formas de acceso, con el mismo código:**
  - **A:** red de la universidad o VPN;
  - **B:** Cloudflare Tunnel con Cloudflare Access.
- **Las PCs no exponen puertos:** el agente solo hace conexiones salientes al hub.
- **Retención limitada:** los resultados se borran solos a los 14 días, y las PCs que generan no guardan datos de estudiantes.

## Para quien evalúa el proyecto

Orden de lectura sugerido:

1. Este README: qué es y cómo se usa.
2. [docs/SEGURIDAD.md](docs/SEGURIDAD.md): qué queda expuesto y cómo se protege.
3. [docs/ANCHO_DE_BANDA.md](docs/ANCHO_DE_BANDA.md): consumo de red medido, por estudiante y para 8 a la vez.
4. [docs/PRUEBAS.md](docs/PRUEBAS.md): todo lo que se verificó, con resultados y cómo repetirlo.
5. [docs/INSTALACION.md](docs/INSTALACION.md): cómo se instala en la sala.
6. [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md): cómo funciona por dentro y la API.

Resumen en cuatro líneas:
- Lo único que escucha en la red es el hub, por HTTPS.
- Las PCs que generan no abren puertos.
- Cada estudiante ve solo lo suyo.
- Los datos se borran solos a los 14 días.

Un estudiante consume 6,5 kbit/s mientras espera y unos 12 MB por cada video que genera, ve y descarga. Con 8 estudiantes generando video a la vez son entre 0,6 y 2,6 Mbit/s de promedio en total.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/INSTALACION.md](docs/INSTALACION.md) | Guía paso a paso para instalar el hub y las 8 PCs (opciones A y B) y preparar la clase |
| [docs/SEGURIDAD.md](docs/SEGURIDAD.md) | Superficie expuesta, autenticación, autorización, datos y retención, límites conocidos, recomendaciones para TI |
| [docs/ANCHO_DE_BANDA.md](docs/ANCHO_DE_BANDA.md) | Medición real del consumo por estudiante y para N estudiantes a la vez |
| [docs/PRUEBAS.md](docs/PRUEBAS.md) | Tests, recorridos en navegador, prueba de carga, generación real con GPU, instaladores, TLS y dependencias |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Componentes, flujo de un pedido, cola y API |
| [docs/MODEL_COMPATIBILITY.md](docs/MODEL_COMPATIBILITY.md) | Modelos del catálogo y su estado en una RTX 2060 de 12 GB (referencia técnica, en inglés) |
| [docs/MODEL_BENCHMARKS.md](docs/MODEL_BENCHMARKS.md) | Tiempos de generación medidos |

## Instalación rápida

En la PC que hará de hub, en PowerShell como Administrador:

```powershell
.\scripts\install-hub.ps1 -Mode lan -HostNames "aula-pc-01,10.20.30.11" -LabSubnet "10.20.30.0/24" -StudentNetworks "10.8.0.0/16" -AdminUser profe
.venv\Scripts\python.exe -m hub.cli add-worker aula-pc-01   # repetir para cada PC; guarda el token
```

En cada PC con GPU, incluida la del hub:

```powershell
.\scripts\install-worker.ps1 -HubUrl https://aula-pc-01:8443 -Token <token> -CaFile D:\hub.crt
```

Los detalles y la opción B están en [docs/INSTALACION.md](docs/INSTALACION.md).

## Probar sin GPU

Para levantar una sala simulada con 4 PCs falsas en `http://localhost:8090`:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci; npm run build
.venv\Scripts\python.exe scripts\dev_classroom.py --workers 4 --reset
```

Cuentas de prueba (solo para esta sala simulada): `admin` / `admin-dev-password` y `alumno1` … `alumno30` / `alumno-dev-password`. Código de clase: `DEMO-2026`.

## Verificación

```powershell
.venv\Scripts\python.exe -m pytest hub\tests worker\tests -q
npm run lint; npm run typecheck; npm run build
npx playwright test
node scripts\measure-bandwidth.mjs
```

## Estructura

```text
hub/         servidor central (FastAPI + SQLite) y su CLI de administración
worker/      agente de cada PC + adaptador de WanGP y backend simulado
app/ components/ lib/   interfaz web (Next.js, export estático servido por el hub)
scripts/     instalación en Windows, sala simulada, medición de ancho de banda
docs/        instalación, seguridad, ancho de banda, arquitectura, modelos
```

## Licencia

El código de este repositorio se distribuye bajo la licencia [MIT](LICENSE).

[WanGP](https://github.com/deepbeepmeep/Wan2GP) y los modelos de IA **no** forman parte de este repositorio: se descargan durante la instalación y conservan sus propias licencias. La licencia de cada modelo figura en el catálogo de la interfaz y en [docs/MODEL_COMPATIBILITY.md](docs/MODEL_COMPATIBILITY.md).
