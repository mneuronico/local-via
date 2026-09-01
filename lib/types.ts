export type WorkflowId =
  | "text-to-image" | "image-to-image" | "image-inpaint"
  | "text-to-video" | "image-to-video" | "video-to-video" | "audio-to-video"
  | "character-animation" | "text-to-speech" | "voice-clone"
  | "text-to-sound" | "audio-to-audio" | "text-to-music" | "audio-to-music";

export type OutputKind = "image" | "video" | "audio";

export type InputDefinition = {
  key: string;
  label: string;
  help: string;
  accept: string;
  required: boolean;
  multiple?: boolean;
  max?: number;
};

export type ParameterOption = { label: string; value: string | number };
export type ParameterDefinition = {
  key: string;
  label: string;
  type: "number" | "select" | "text" | "boolean";
  help?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: ParameterOption[];
  workflows?: WorkflowId[];
};

export type WorkflowDefinition = {
  id: WorkflowId;
  label: string;
  shortLabel: string;
  description: string;
  output: OutputKind;
};

export type ModelWorkflow = {
  id: WorkflowId;
  task: string;
  inputs: InputDefinition[];
  defaults: Record<string, string | number | boolean>;
};

export type ModelDefinition = {
  id: string;
  name: string;
  family: string;
  summary: string;
  tier: "Rápido" | "Equilibrado" | "Avanzado" | "Especialista";
  license: string;
  accent: string;
  workflows: ModelWorkflow[];
  parameters: ParameterDefinition[];
  installed?: boolean;
};

export type Artifact = {
  id: string;
  name: string;
  media_type: string;
  size: number;
  url: string;
};

export type Job = {
  id: string;
  project_id: string;
  model: string;
  task: string;
  prompt: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  phase?: string;
  error?: string;
  created_at: string;
  updated_at: string;
  parameters: Record<string, unknown>;
  artifacts: Artifact[];
};

export type WorkerStatus = {
  worker_id: string;
  status: string;
  backend: string;
  gpu: { name: string; vram_total_mb: number; vram_free_mb: number } | null;
  queue_depth: number;
  active_job_id: string | null;
  wangp_ready: boolean;
};

export type WorkerModelCatalog = {
  id: string;
  name: string;
  license: string;
  tasks: string[];
  installed: boolean;
};
