# Medición de ancho de banda

**Fecha:** 7 de octubre de 2026 · **Datos crudos:** [bandwidth/results.json](bandwidth/results.json) · **Script:** [`scripts/measure-bandwidth.mjs`](../scripts/measure-bandwidth.mjs)

## Conclusión

| Situación | Consumo por estudiante |
|---|---|
| Sesión abierta, sin generar | **1,5 kbit/s** |
| Esperando en la cola o mientras su pedido se genera | **6,5 kbit/s** |
| Pedido de **imagen** completo (subir, esperar, ver y descargar) | **0,3–0,4 MB** por pedido |
| Pedido de **video** completo, con un clip real de 5,7 MB | **12–13 MB** por pedido |
| Pedido de **música** completo, con un WAV real de 60 s (11,5 MB) | **18 MB** por pedido |
| Primera carga de la interfaz (sin caché) | **0,3 MB**, una sola vez; las siguientes ~37 kB |

Con **8 estudiantes generando video a la vez** (el máximo, una PC cada uno), el promedio es de **0,6 a 2,6 Mbit/s en total**, según cuánto tarde cada video (de 23 a 5 minutos). Los que esperan en la cola suman 6,5 kbit/s cada uno: 20 estudiantes en cola son 0,13 Mbit/s.

El tráfico no es parejo: llega en **ráfagas** cuando termina un pedido y el estudiante abre y descarga el resultado. El peor caso es que 8 videos terminen en el mismo instante: unos 95 MB, que tardan unos 8 s en un enlace de 100 Mbit/s o 15 s en uno de 50 Mbit/s. **El cuello de botella de la sala es la GPU, no la red.**

## Cómo se midió

- **Tráfico real de un navegador real.** Cada estudiante simulado es un Chromium independiente (Playwright, caché vacía) que usa la interfaz real: inicia sesión, elige modalidad y modelo, sube archivos, pulsa *Generar*, espera, amplía el resultado (reproduce video y audio) y lo descarga.
- **Contra el hub real por HTTPS** (TLS 1.3, HTTP/1.1, certificado del hub).
- **Cada navegador pasa por su propio relé TCP que cuenta bytes** en ambos sentidos, segundo a segundo. Los números son los bytes que cruzan la red, **con TLS incluido**. No incluyen los encabezados TCP/IP (alrededor de 3 % más) ni el encapsulado de una VPN si la hubiera (entre 3 % y 10 % más, según el tipo de VPN).
- **Las 8 PCs son agentes reales que no usan la GPU**: en lugar de generar, devuelven archivos **reales generados antes en la RTX 2060** de este proyecto.

  | Tipo | Archivo usado | Tamaño | Origen |
  |---|---|---:|---|
  | Imagen | JPEG 512×512 | 156 kB | Qwen Image Edit Lightning 8 |
  | Video | MP4 512×512, 60 frames | 5,69 MB | MiniMax H3 Turbo 4 (el video más pesado medido) |
  | Música | WAV estéreo 48 kHz, 60 s | 11,5 MB | ACE-Step 1.5 |
  | Entrada (imagen → video) | JPEG | 42 kB | Z-Image |

  Para la red, lo único que importa es el tamaño de los archivos y la cantidad de consultas, no la GPU. La duración de cada pedido se simuló en 60 s. Las tablas de abajo extrapolan a duraciones reales usando la tasa medida durante la espera.
- **Escenarios:**
  1. sesión abierta 120 s sin generar;
  2. un pedido de cada tipo, con la sala vacía;
  3. **12 estudiantes a la vez** generando video con 8 PCs: 8 generan y 4 esperan en la cola.

## Resultados por pedido (un estudiante)

| Fase | Imagen | Video | Música |
|---|---:|---:|---:|
| Subir entradas y enviar el pedido | 4 kB | 51 kB (incluye la imagen de 42 kB) | 4 kB |
| Esperar (por minuto de espera) | 49 kB | 49 kB | 49 kB |
| Ver el resultado en la página | 158 kB | 6,12 MB | 6,46 MB (reproducción parcial) |
| Descargar el resultado | 158 kB | 5,70 MB | 11,54 MB |
| **Total sin contar la espera** | **0,32 MB** | **11,86 MB** | **18,01 MB** |

El total es aproximadamente *(tamaño del resultado × 2) + entradas + 49 kB por minuto de espera*: el archivo viaja una vez para verlo y otra para descargarlo. Si el estudiante solo lo mira, la cifra baja a la mitad.

## Proyección con duraciones reales

Promedio por estudiante mientras genera un pedido tras otro, con ver y descargar incluidos. Las duraciones son tiempos reales medidos en la RTX 2060 (ver [MODEL_BENCHMARKS.md](MODEL_BENCHMARKS.md)).

| Pedido | Duración | Datos por pedido | Promedio por estudiante | 8 estudiantes a la vez |
|---|---:|---:|---:|---:|
| Z-Image, imagen 512² | 0:51 | 0,36 MB | 57 kbit/s | 0,45 Mbit/s |
| Qwen Image Edit, imagen 512² | 13:01 | 0,96 MB | 10 kbit/s | 0,08 Mbit/s |
| Video, si tardara 5 min | 5:00 | 12,1 MB | 323 kbit/s | 2,6 Mbit/s |
| MiniMax H3 Turbo 8, 49 frames (estimado en caliente) | ~10:00 | 12,4 MB | 165 kbit/s | 1,3 Mbit/s |
| Wan 2.2 TI2V, 72 frames, 50 pasos | 23:34 | 13,0 MB | 74 kbit/s | 0,6 Mbit/s |
| Música 60 s, si tardara 3 min | 3:00 | 18,2 MB | 807 kbit/s | 6,5 Mbit/s |
| Música 60 s, si tardara 5 min | 5:00 | 18,3 MB | 487 kbit/s | 3,9 Mbit/s |

Además, cada estudiante en la cola agrega 6,5 kbit/s y cada sesión abierta sin pedidos, 1,5 kbit/s.

## 12 estudiantes simultáneos (medido)

12 navegadores enviaron un pedido de video al mismo tiempo, con 8 PCs: 8 se procesaron de inmediato y 4 esperaron en la cola (con duración simulada de 60 s).

| Métrica | Valor |
|---|---:|
| Duración total del escenario | 125 s |
| Datos totales de los 12 estudiantes | 140,4 MB (11,6–12,0 MB cada uno) |
| Consumo durante la espera, por estudiante | 6,6–6,7 kbit/s |
| Promedio del escenario completo | 9,0 Mbit/s |
| Pico en 1 segundo | limitado solo por el enlace (en la prueba local, 273 Mbit/s) |

El promedio de 9,0 Mbit/s es alto porque en la prueba cada video tardó 60 s. Con videos reales, de 10 a 23 minutos, los mismos bytes se reparten en mucho más tiempo (ver tabla anterior). El pico refleja que las 8 descargas coincidieron en el mismo segundo; en un enlace real, esa ráfaga tarda lo que indica la tabla siguiente.

| Ráfaga: 8 videos terminan juntos (95 MB) | Tiempo de entrega |
|---|---:|
| Enlace de 10 Mbit/s | 76 s |
| Enlace de 50 Mbit/s | 15 s |
| Enlace de 100 Mbit/s | 8 s |
| Enlace de 1 Gbit/s | 1 s |

## Tráfico interno (hub ↔ PCs del laboratorio)

Este tráfico no sale del laboratorio. Por cada pedido, la PC que lo procesa descarga las entradas y sube el resultado al hub una vez: **aproximadamente el tamaño del resultado**. En la prueba de 12 videos fueron 69,2 MB: 68,2 MB de resultados (12 × 5,7 MB), 0,5 MB de entradas y unos 4 kB/s de consultas y avisos de progreso de las 8 PCs.

## Qué cambia con otros ajustes

- **Videos más grandes.** Los videos medidos son de 512×512 o 512×288 y de 49 a 121 frames, y ocupan entre 12 y 95 kB por frame. Un video de 832×480 y 124 frames, el valor por defecto de MiniMax H3, rondaría entre 4 y 18 MB (estimación por escala de píxeles y frames, **no medida**). El consumo por pedido escala igual.
- **Música más larga.** WAV estéreo de 48 kHz ocupa unos 11,5 MB por minuto, así que una canción de 2 minutos son ~23 MB por resultado.
- **Archivos de entrada.** Se suben una vez y cuestan su propio tamaño. Una foto de celular de 4 MB agrega 4 MB.

## Cómo reducirlo (opcional)

1. **Limitar resolución, frames y duración** desde *Administración → Modelos y límites*: es lo que más pesa.
2. **No descargar si no hace falta:** ver el resultado en la página ya lo trae una vez.
3. **Comprimir el audio** (por ejemplo a AAC/Opus) bajaría la música de ~11,5 MB a ~1 MB por minuto. Hoy no está implementado: WanGP entrega WAV.

## Reproducir la medición

```powershell
python -m venv .venv; .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci; npm run build; npx playwright install chromium
# Copiar a data\bandwidth-samples\ archivos reales: image.jpg, video.mp4, audio.wav, input-image.jpg
node scripts\measure-bandwidth.mjs           # ~10 minutos; escribe docs\bandwidth\results.json
```
