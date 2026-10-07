const PHASES: Record<string, { label: string; hint: string }> = {
  queued: { label: "En cola", hint: "El pedido espera a que se libere una computadora de la sala." },
  requeued: { label: "En cola otra vez", hint: "La computadora asignada dejó de responder; el pedido volvió al frente de la cola." },
  dispatched: { label: "Asignado", hint: "Una computadora de la sala tomó el pedido." },
  downloading_inputs: { label: "Recibiendo archivos", hint: "La computadora asignada descarga tus archivos de entrada." },
  loading: { label: "Preparando archivos", hint: "La computadora valida los inputs antes de cargar el modelo." },
  loading_model: { label: "Cargando modelo", hint: "Se mueven bloques entre disco, RAM y VRAM; la GPU puede marcar 0% durante esta fase." },
  encoding_text: { label: "Interpretando el prompt", hint: "El encoder prepara el texto y las referencias." },
  inference: { label: "Generando en GPU", hint: "La GPU ejecuta los pasos de generación." },
  inference_stage_1: { label: "Generando en GPU · fase 1", hint: "Primera etapa de denoising." },
  inference_stage_2: { label: "Generando en GPU · fase 2", hint: "Segunda etapa de denoising." },
  inference_stage_3: { label: "Generando en GPU · fase 3", hint: "Tercera etapa de denoising." },
  decoding: { label: "Decodificando resultado", hint: "El VAE convierte los latentes al archivo final." },
  downloading_output: { label: "Guardando resultado", hint: "La computadora escribe los archivos generados." },
  uploading_output: { label: "Enviando resultado", hint: "El resultado viaja al servidor central para que puedas verlo." },
  cancelling: { label: "Cancelando", hint: "Se le avisó a la computadora que detenga el trabajo." },
  complete: { label: "Listo", hint: "La generación terminó correctamente." },
  error: { label: "Error", hint: "La generación no pudo completarse." },
  cancelled: { label: "Cancelado", hint: "La generación fue cancelada." },
};

export function describePhase(phase?: string) {
  const key = (phase || "queued").trim().toLowerCase();
  return PHASES[key] ?? { label: phase || "Preparando", hint: "Una computadora de la sala está procesando el trabajo." };
}
