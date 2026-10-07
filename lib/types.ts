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

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type Job = {
  id: string;
  model: string;
  model_name: string;
  task: string;
  prompt: string;
  status: JobStatus;
  progress: number;
  phase?: string | null;
  error?: string | null;
  worker_id?: string | null;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  parameters: Record<string, unknown>;
  artifacts: Artifact[];
  queue?: { position: number; estimated_wait_seconds: number | null } | null;
  username?: string;
};

export type Room = { queued_total: number; running_total: number; workers_online: number; workers_busy: number };

export type User = { id: string; username: string; display_name: string; role: "student" | "admin"; class_id?: string | null; disabled: boolean; created_at?: string | null; last_login_at?: string | null };

export type Me = { user: User; limits: { max_active_jobs: number; max_upload_mb: number; quota_mb: number; retention_days: number } };

export type WorkerInfo = {
  id: string;
  online: boolean;
  disabled: boolean;
  last_seen_at: string | null;
  ip: string | null;
  backend: string | null;
  version: string | null;
  loaded_model: string | null;
  gpu: { name: string; vram_total_mb: number; vram_free_mb: number; temperature_c?: number } | null;
  installed_models: string[];
  current_job_id: string | null;
};

export type Policy = { enabled_models: string[]; max_pixels: number; max_video_frames: number; max_steps: number; max_audio_seconds: number; max_batch_size: number };

export type ClassGroup = { id: string; name: string; code: string; expires_at: string | null; max_uses: number | null; uses: number; revoked: boolean; students: number; created_at: string };

export type AuditEvent = { id: number; at: string; actor: string | null; action: string; detail: string | null; ip: string | null };
