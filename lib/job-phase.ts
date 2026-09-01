const PHASES: Record<string, { label: string; hint: string }> = {
  queued: { label: "En cola", hint: "El trabajo espera a que la GPU quede libre." },
  loading: { label: "Preparando archivos", hint: "El worker valida los inputs antes de cargar el modelo." },
  loading_model: { label: "Cargando modelo", hint: "Se mueven bloques entre disco, RAM y VRAM; la GPU puede marcar 0% durante esta fase." },
  encoding_text: { label: "Interpretando el prompt", hint: "El encoder prepara el texto y las referencias." },
  inference: { label: "Generando en GPU", hint: "La GPU ejecuta los pasos de generación." },
  inference_stage_1: { label: "Generando en GPU · fase 1", hint: "Primera etapa de denoising." },
  inference_stage_2: { label: "Generando en GPU · fase 2", hint: "Segunda etapa de denoising." },
  inference_stage_3: { label: "Generando en GPU · fase 3", hint: "Tercera etapa de denoising." },
  decoding: { label: "Decodificando resultado", hint: "El VAE convierte los latentes al archivo final." },
  downloading_output: { label: "Guardando resultado", hint: "El worker escribe y registra los archivos generados." },
  complete: { label: "Listo", hint: "La generación terminó correctamente." },
  error: { label: "Error", hint: "La generación no pudo completarse." },
  cancelled: { label: "Cancelado", hint: "La generación fue cancelada." },
};

export function describePhase(phase?: string) {
  const key = (phase || "queued").trim().toLowerCase();
  return PHASES[key] ?? { label: phase || "Preparando", hint: "El worker está procesando el trabajo." };
}
