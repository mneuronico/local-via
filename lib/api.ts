import type { Job, Me, Room } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

/** Same-origin call to the hub. The custom header is the hub's CSRF guard; the session lives in an HttpOnly cookie. */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isBinary = init.body instanceof Blob || init.body instanceof ArrayBuffer;
  const response = await fetch(path, {
    ...init,
    credentials: "same-origin",
    headers: { "X-LocalVia": "1", ...(init.body && !isBinary ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (!response.ok) {
    const detail = (await response.json().catch(() => null))?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `El servidor respondió ${response.status}`, response.status);
  }
  return response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) => api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const hubApi = {
  session: () => api<Me | { user: null }>("/api/session"),
  login: (username: string, password: string) => post<Me>("/api/auth/login", { username, password }),
  register: (body: { class_code: string; username: string; display_name: string; password: string }) => post<Me>("/api/auth/register", body),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),
  changePassword: (current_password: string, new_password: string) => post<{ ok: boolean }>("/api/me/password", { current_password, new_password }),
  state: () => api<{ jobs: Job[]; room: Room }>("/api/state"),
  catalog: () => api<{ models: { id: string; name: string; enabled: boolean; available: boolean }[] }>("/api/catalog"),
  createJob: (body: object) => post<Job>("/api/jobs", body),
  cancelJob: (id: string) => post<{ ok: boolean }>(`/api/jobs/${id}/cancel`),
  deleteJob: (id: string) => api<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
};

export async function uploadFile(file: File, inputKey: string, onProgress?: (value: number) => void) {
  const created = await post<{ id: string; chunk_bytes: number }>("/api/uploads", { name: file.name, size: file.size, media_type: file.type || "application/octet-stream", input_key: inputKey });
  const chunks = Math.ceil(file.size / created.chunk_bytes);
  for (let index = 0; index < chunks; index++) {
    const chunk = file.slice(index * created.chunk_bytes, Math.min(file.size, (index + 1) * created.chunk_bytes));
    await api(`/api/uploads/${created.id}/chunks/${index}`, { method: "PUT", body: chunk, headers: { "Content-Type": "application/octet-stream" } });
    onProgress?.(Math.round(((index + 1) / chunks) * 100));
  }
  await post(`/api/uploads/${created.id}/complete`);
  return created.id;
}

export function formatWait(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "sin computadoras conectadas";
  if (seconds < 60) return "menos de un minuto";
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `~${minutes} min` : `~${Math.floor(minutes / 60)} h ${minutes % 60} min`;
}
