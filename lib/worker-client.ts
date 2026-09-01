import type { Job, WorkerModelCatalog, WorkerStatus } from "./types";

export type WorkerConfig = { url: string; token: string };

function endpoint(config: WorkerConfig, path: string) {
  return `${config.url.replace(/\/$/, "")}${path}`;
}

async function request<T>(config: WorkerConfig, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(endpoint(config, path), {
    ...init,
    headers: { ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...(config.token ? { Authorization: `Bearer ${config.token}` } : {}), ...init?.headers },
  });
  if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail ?? `Worker respondió ${response.status}`);
  return response.json() as Promise<T>;
}

export const workerClient = {
  status: (config: WorkerConfig) => request<WorkerStatus>(config, "/v1/status"),
  models: (config: WorkerConfig) => request<{ models: WorkerModelCatalog[] }>(config, "/v1/models"),
  jobs: (config: WorkerConfig) => request<{ jobs: Job[] }>(config, "/v1/jobs"),
  job: (config: WorkerConfig, id: string) => request<Job>(config, `/v1/jobs/${id}`),
  createJob: (config: WorkerConfig, body: object) => request<Job>(config, "/v1/jobs", { method: "POST", body: JSON.stringify(body) }),
  cancelJob: (config: WorkerConfig, id: string) => request<Job>(config, `/v1/jobs/${id}/cancel`, { method: "POST" }),
  createUpload: (config: WorkerConfig, file: File) => request<{ id: string }>(config, "/v1/uploads", { method: "POST", body: JSON.stringify({ name: file.name, size: file.size, media_type: file.type }) }),
  uploadChunk: async (config: WorkerConfig, uploadId: string, index: number, chunk: Blob) => {
    const body = new FormData(); body.append("chunk", chunk);
    return request<{ received: number }>(config, `/v1/uploads/${uploadId}/chunks/${index}`, { method: "PUT", body });
  },
  finishUpload: (config: WorkerConfig, uploadId: string, chunks: number) => request<{ id: string }>(config, `/v1/uploads/${uploadId}/complete`, { method: "POST", body: JSON.stringify({ chunks }) }),
};

export async function uploadFile(config: WorkerConfig, file: File, onProgress?: (value: number) => void) {
  const upload = await workerClient.createUpload(config, file);
  const chunkSize = 8 * 1024 * 1024;
  const chunks = Math.ceil(file.size / chunkSize);
  for (let index = 0; index < chunks; index++) {
    await workerClient.uploadChunk(config, upload.id, index, file.slice(index * chunkSize, Math.min(file.size, (index + 1) * chunkSize)));
    onProgress?.(Math.round(((index + 1) / chunks) * 100));
  }
  await workerClient.finishUpload(config, upload.id, chunks);
  return upload.id;
}
