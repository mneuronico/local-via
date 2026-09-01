# Tiempos de los smoke tests

Mediciones del 13 de agosto de 2026 en la GPU local. Los valores son de **primera ejecución completa**: incluyen arranque del proceso, descargas que faltaban, carga y offload del modelo, inferencia, codificación y escritura del archivo. Por eso no deben leerse como el tiempo estable de una segunda generación con el modelo ya cargado.

| Modelo | Modalidad probada | Ajuste mínimo del smoke test | Tiempo total |
|---|---|---:|---:|
| Stable Audio 3 Small SFX | Texto → audio | 2 s, 2 pasos | 1:15 |
| ACE-Step 1.5 | Texto → música | 10 s, 2 pasos | 1:35 |
| SeedVC | Voz → voz | clip corto | 1:36 |
| Qwen3-TTS Base | Texto → voz | 2 s | 1:46 |
| Qwen3-TTS VoiceDesign | Texto → voz | 2 s | 1:46 |
| Z-Image | Texto → imagen | 512×512, 2 pasos | 2:23 |
| TI2V 2.2 | Imagen → video | 512×288, 9 frames, 2 pasos | 3:56 |
| Animate | Imagen + video guía → video | 512×512, 17 frames, 2 pasos | 7:06 |
| VACE 14B | Video → video | 512×288, 9 frames, 2 pasos | 7:47 |
| Qwen Image Edit Plus 20B | Imagen → imagen | 512×512, 2 pasos | 8:46 |
| Qwen Image 20B | Texto → imagen | 512×512, 2 pasos | 11:50 |
| MiniMax H3 Ref2VA pruned | Imagen + audio → video | 512×288, 9 frames, 2 pasos | 15:26 |
| LTX-2.5 22B distilled | Texto → video | 512×288, 9 frames, 8 + 3 pasos | 18:44 |
| MiniMax H3 FL2VA pruned | Texto + audio → video | 512×288, 9 frames, 2 pasos | 23:03 |

Notas:

- Z-Image tardó aproximadamente 9 segundos en la inferencia de dos pasos una vez cargado; los 2:23 corresponden al recorrido completo en frío.
- LTX pidió dos pasos en el smoke test, pero el backend impuso su mínimo de ocho y luego ejecutó tres pasos de refinamiento. La parte de denoising/refinado observada fue de aproximadamente 1:30; el resto fue carga, descarga y codificación.
- Los casos de MiniMax y LTX descargaron pesos grandes durante esa primera ejecución (hasta decenas de GB), por lo que una segunda corrida debería ser sensiblemente más rápida.
- Para obtener cifras comparables de uso cotidiano falta una segunda ronda en caliente, midiendo por separado carga, inferencia y codificación con los mismos parámetros.

## Generaciones completas desde la UI

Estas mediciones salen de `created_at` y `updated_at` persistidos por el worker, por lo que incluyen cola, carga u offload, inferencia, codificación y guardado.

| Modelo | Ajustes usados | Tiempo total |
|---|---:|---:|
| Z-Image Turbo 6B | 512×512, 8 pasos | 0:51 |
| Qwen Image Edit Plus 20B | 512×512, 20 pasos | 13:01 |
| Wan 2.2 TI2V 5B | 512×512, 72 frames, 50 pasos | 23:34 |

Son tiempos reales de esas ejecuciones, no una predicción para cualquier prompt. Una corrida repetida dentro de la ventana de caché puede ahorrar la carga inicial del modelo.

## Variantes rápidas, preload y caché

Mediciones del 14 de agosto de 2026 con `--preload 4000` y una ventana de caché de una hora:

| Modelo | Ajustes usados | Estado | Tiempo total |
|---|---:|---:|---:|
| Wan 2.2 TI2V 5B FastWan, frío | 512×288, 9 frames, 3 pasos | Correcto | 3:10.58 |
| Wan 2.2 TI2V 5B FastWan, caliente | Idénticos ajustes | Correcto | 0:12.86 |
| Qwen Image Edit Plus Fast INT4 | 512×512, 4 pasos | Kernel CUDA inestable en RTX 2060 | 4:27 hasta el fallo |
| Qwen Image Edit Plus Fast INT4 | 256×256, 4 pasos | Kernel CUDA inestable en RTX 2060 | 4:08 hasta el fallo |
| Qwen Image Edit Plus Lightning 8, frío | 512×512, 8 pasos | Correcto | 7:16.55 |
| Qwen Image Edit Plus Lightning 8, caliente | Idénticos ajustes | Correcto | 2:38.06 |

- En FastWan el administrador de memoria precargó 3597.83 MB del transformer (76.7% de las capas recurrentes) y 3475.77 MB del text encoder.
- La segunda ejecución de FastWan reutilizó el modelo en memoria: no volvió a cargar pesos y pasó de 3:10.58 a 12.86 segundos.
- Qwen INT4 usó Nunchaku 1.2.1, PyTorch 2.10/CUDA 13 y los kernels `sm_75` correspondientes a Turing. En ambos tamaños el kernel terminó con `cudaErrorLaunchFailure`; por eso la UI lo identifica como experimental para RTX 20 y recomienda el Qwen estándar en esta máquina.
- Qwen Lightning 8 reutiliza el checkpoint Qwen Edit Plus INT8 estable y aplica la LoRA aceleradora con multiplicador 1, ocho pasos y guidance 1. En esta máquina precargó unos 3.3 GB del transformer y 3.3 GB del encoder; la repetición caliente omitió la carga completa del modelo.

## MiniMax H3 FL2VA: base vs Turbo 8 (1 de septiembre de 2026)

Medido con `scripts/bench_h3_turbo.py` a través del worker local: texto → video, 512×288, seed 1234, mismo prompt. Se pidieron 49 frames y H3 produjo en los tres casos el mismo archivo de 107 frames a 24 fps (4.5 s) con audio estéreo a 32 kHz, así que las corridas son comparables entre sí. Los tiempos incluyen carga, text encoder, denoising, decodificación y guardado.

| Corrida | Pasos | Carga modelo | Text encoder | Denoising | Decodificación | Total |
|---|---:|---:|---:|---:|---:|---:|
| Base, frío | 20 | 3:26 | 3:01 | 19:22 (~58 s/paso) | 1:05 | 26:59 |
| Base, caliente | 20 | 0:00 | 0:10 | 19:38 (~59 s/paso) | 0:56 | 20:49 |
| Turbo 8, frío | 8 | 3:31 | 3:56 | 8:42 (~65 s/paso) | 1:05 | 17:20 |

- El denoising es la parte que cambia: 8 pasos con la LoRA Turbo tardan 8:42 contra 19:22 de los 20 pasos base, es decir 2.2 veces menos. El costo por paso sube de 58 a 65 segundos por la LoRA sin mergear y por la menor RAM fijada (ver abajo).
- Total en frío: 17:20 contra 26:59, una reducción del 36 %. En caliente, restando la carga del modelo y del text encoder ya medidas, Turbo 8 quedaría en unos 10 minutos contra 20:49, cerca de la mitad. Ese número caliente es una estimación: no se repitió la corrida a propósito.
- El video generado tiene la misma resolución, cantidad de frames y pista de audio que el base. No se hizo una comparación de calidad sistemática.
- Turbo 4 no se midió.

### Incidente durante la medición

La tanda original encadenaba seis generaciones sin supervisión. Durante el primer paso de la tercera (Turbo 8), tras casi una hora de carga sostenida, la máquina sufrió un bugcheck del kernel cuyo volcado no pudo escribirse, y luego el BIOS no detectó el disco de arranque hasta abrir y limpiar el equipo. El registro de Windows muestra timeouts del motor de video de esta RTX 2060 desde 2025, y WanGP había fijado 16 GB de RAM como no paginable con un archivo de paginación de 2.5 GB.

Medidas tomadas:

- La corrida Turbo 8 de la tabla se hizo después, como trabajo único, con temperatura y consumo de la GPU monitoreados cada minuto y cancelación automática a 86 °C. La GPU se estabilizó en 82 °C y 165–184 W durante el denoising.
- `LOCAL_VIA_WANGP_CLI_ARGS` en `worker/.env` ahora incluye `--perc-reserved-mem-max 0.25` para que WanGP fije como máximo un cuarto de la RAM. Eso explica el text encoder más lento en la fila Turbo 8.
- En esta máquina no conviene encadenar generaciones pesadas ni dejarlas sin supervisión. Conviene además ampliar el archivo de paginación para que Windows pueda escribir un volcado la próxima vez.
