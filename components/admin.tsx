"use client";

import { ArrowLeft, Ban, CircleCheck, Copy, Cpu, KeyRound, ListChecks, RefreshCw, ScrollText, Server, Trash2, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, formatWait } from "@/lib/api";
import { describePhase } from "@/lib/job-phase";
import type { AuditEvent, ClassGroup, Job, Me, Policy, Room, User, WorkerInfo } from "@/lib/types";

type Overview = { workers: WorkerInfo[]; queue: Job[]; room: Room; last_24h: { total: number; succeeded: number; failed: number }; users_total: number };
type Tab = "room" | "classes" | "users" | "workers" | "policy" | "audit";
const post = <T,>(path: string, body?: unknown, method = "POST") => api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" }) : "—";

export function Admin({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>("room");
  const [error, setError] = useState("");
  const fail = useCallback((failure: unknown) => setError(failure instanceof Error ? failure.message : "Error inesperado"), []);
  const tabs: [Tab, string, typeof Users][] = [["room", "Sala", Cpu], ["classes", "Clases", ListChecks], ["users", "Usuarios", Users], ["workers", "Computadoras", Server], ["policy", "Modelos y límites", KeyRound], ["audit", "Auditoría", ScrollText]];
  if (me.user.role !== "admin") return <main className="authShell"><section className="authCard"><h2>Solo para administración</h2><Link href="/">Volver al estudio</Link></section></main>;
  return <div className="adminShell">
    <header className="topbar adminTop"><Link className="iconButton" href="/" aria-label="Volver al estudio"><ArrowLeft size={18} /></Link><div><p className="topEyebrow">Local Via</p><h1>Administración</h1></div><div className="topActions"><button className="connectionPill connected" onClick={onLogout}>{me.user.username} · salir</button></div></header>
    <nav className="adminTabs" aria-label="Secciones de administración">{tabs.map(([id, label, Icon]) => <button key={id} className={tab === id ? "active" : ""} onClick={() => { setTab(id); setError(""); }}><Icon size={15} /> {label}</button>)}</nav>
    <main className="adminBody">
      {error && <div className="inlineError" role="alert"><span>{error}</span><button onClick={() => setError("")}>Cerrar</button></div>}
      {tab === "room" && <RoomPanel onError={fail} />}
      {tab === "classes" && <ClassesPanel onError={fail} />}
      {tab === "users" && <UsersPanel me={me} onError={fail} />}
      {tab === "workers" && <WorkersPanel onError={fail} />}
      {tab === "policy" && <PolicyPanel onError={fail} />}
      {tab === "audit" && <AuditPanel onError={fail} />}
    </main>
  </div>;
}

function useLoader<T>(path: string, onError: (error: unknown) => void, intervalMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const load = useCallback(() => api<T>(path).then(setData).catch(onError), [path, onError]);
  useEffect(() => {
    const first = window.setTimeout(load, 0);
    const timer = intervalMs ? window.setInterval(load, intervalMs) : undefined;
    return () => { window.clearTimeout(first); if (timer) window.clearInterval(timer); };
  }, [load, intervalMs]);
  return { data, load };
}

function RoomPanel({ onError }: { onError: (error: unknown) => void }) {
  const { data, load } = useLoader<Overview>("/api/admin/overview", onError, 4000);
  if (!data) return <p className="adminMuted">Cargando…</p>;
  return <>
    <section className="adminStats">
      <div><small>Computadoras conectadas</small><b>{data.room.workers_online} / {data.workers.filter((worker) => !worker.disabled).length}</b></div>
      <div><small>Generando ahora</small><b>{data.room.running_total}</b></div>
      <div><small>En cola</small><b>{data.room.queued_total}</b></div>
      <div><small>Últimas 24 h</small><b>{data.last_24h.succeeded} ok · {data.last_24h.failed} con error</b></div>
    </section>
    <h2 className="adminTitle">Computadoras</h2>
    <div className="workerGrid">{data.workers.map((worker) => <article key={worker.id} className={`workerCard ${worker.online ? "online" : ""}`}>
      <header><span className={`statusDot ${worker.online ? "online" : ""}`} /><b>{worker.id}</b><small>{worker.disabled ? "deshabilitada" : worker.online ? (worker.current_job_id ? "generando" : "libre") : "sin conexión"}</small></header>
      <dl><dt>GPU</dt><dd>{worker.gpu ? `${worker.gpu.name}${worker.gpu.temperature_c ? ` · ${worker.gpu.temperature_c} °C` : ""}` : "—"}</dd><dt>Modelo en memoria</dt><dd>{worker.loaded_model ?? "—"}</dd><dt>Modelos instalados</dt><dd>{worker.installed_models.length}</dd><dt>Última señal</dt><dd>{when(worker.last_seen_at)}</dd><dt>IP</dt><dd>{worker.ip ?? "—"}</dd></dl>
    </article>)}{data.workers.length === 0 && <p className="adminMuted">Todavía no se registró ninguna computadora. Usá la pestaña Computadoras.</p>}</div>
    <h2 className="adminTitle">Cola</h2>
    <table className="adminTable"><thead><tr><th>#</th><th>Usuario</th><th>Modelo</th><th>Estado</th><th>Creado</th><th /></tr></thead><tbody>
      {data.queue.map((job) => <tr key={job.id}><td>{job.queue?.position ?? "—"}</td><td>{job.username}</td><td>{job.model_name}</td><td>{job.status === "queued" ? `En cola · ${formatWait(job.queue?.estimated_wait_seconds)}` : `${describePhase(job.phase ?? "").label} ${job.progress}% · ${job.worker_id ?? ""}`}</td><td>{when(job.created_at)}</td>
        <td><button className="ghostButton" onClick={() => post(`/api/admin/jobs/${job.id}/cancel`).then(load).catch(onError)}><Ban size={14} /> Cancelar</button></td></tr>)}
      {data.queue.length === 0 && <tr><td colSpan={6} className="adminMuted">No hay pedidos en curso.</td></tr>}
    </tbody></table>
  </>;
}

function ClassesPanel({ onError }: { onError: (error: unknown) => void }) {
  const { data, load } = useLoader<{ classes: ClassGroup[] }>("/api/admin/classes", onError);
  const [name, setName] = useState(""); const [days, setDays] = useState(120); const [maxUses, setMaxUses] = useState("");
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await post("/api/admin/classes", { name, expires_in_days: days, max_uses: maxUses ? Number(maxUses) : null }).then(() => { setName(""); load(); }).catch(onError);
  }
  return <>
    <p className="adminMuted">Cada clase tiene un código. Quien lo tenga puede crear su propia cuenta de estudiante hasta que el código venza o lo revoques. Para cuentas creadas por vos, usá la pestaña Usuarios.</p>
    <form className="adminForm" onSubmit={create}><label>Nombre<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Taller de video · 2º cuatrimestre" required /></label><label>Vence en (días)<input type="number" min={1} max={730} value={days} onChange={(event) => setDays(Number(event.target.value))} /></label><label>Máximo de cuentas<input type="number" min={1} value={maxUses} onChange={(event) => setMaxUses(event.target.value)} placeholder="sin límite" /></label><button className="generateButton">Crear código</button></form>
    <table className="adminTable"><thead><tr><th>Clase</th><th>Código</th><th>Cuentas</th><th>Vence</th><th>Estado</th><th /></tr></thead><tbody>
      {data?.classes.map((group) => <tr key={group.id}><td>{group.name}</td><td><code className="classCode">{group.code}</code></td><td>{group.uses}{group.max_uses ? ` / ${group.max_uses}` : ""}</td><td>{when(group.expires_at)}</td><td>{group.revoked ? "Revocado" : "Activo"}</td>
        <td><button className="ghostButton" onClick={() => post(`/api/admin/classes/${group.id}`, { revoked: !group.revoked }, "PATCH").then(load).catch(onError)}>{group.revoked ? "Reactivar" : "Revocar"}</button></td></tr>)}
    </tbody></table>
  </>;
}

function UsersPanel({ me, onError }: { me: Me; onError: (error: unknown) => void }) {
  const { data, load } = useLoader<{ users: User[] }>("/api/admin/users", onError);
  const classes = useLoader<{ classes: ClassGroup[] }>("/api/admin/classes", onError).data?.classes ?? [];
  const [names, setNames] = useState(""); const [classId, setClassId] = useState(""); const [admin, setAdmin] = useState("");
  const [created, setCreated] = useState<{ username: string; password: string }[]>([]);
  async function bulk(event: React.FormEvent) {
    event.preventDefault();
    const usernames = names.split(/[\s,;]+/).filter(Boolean);
    await post<{ created: { username: string; password: string }[] }>("/api/admin/users/bulk", { usernames, class_id: classId || null }).then((result) => { setCreated(result.created); setNames(""); load(); }).catch(onError);
  }
  async function createAdmin(event: React.FormEvent) {
    event.preventDefault();
    await post<{ user: User; password: string }>("/api/admin/users", { username: admin, role: "admin" }).then((result) => { setCreated([{ username: result.user.username, password: result.password }]); setAdmin(""); load(); }).catch(onError);
  }
  async function reset(user: User) {
    await post<{ password: string }>(`/api/admin/users/${user.id}`, { reset_password: true }, "PATCH").then((result) => { setCreated([{ username: user.username, password: result.password }]); }).catch(onError);
  }
  const copyText = created.map((item) => `${item.username}\t${item.password}`).join("\n");
  return <>
    <div className="adminColumns">
      <form className="adminForm vertical" onSubmit={bulk}><h3>Crear cuentas de estudiantes</h3><label>Usuarios (uno por línea o separados por coma)<textarea value={names} onChange={(event) => setNames(event.target.value)} placeholder={"jperez\nmgarcia"} required /></label><label>Clase<select value={classId} onChange={(event) => setClassId(event.target.value)}><option value="">Sin clase</option>{classes.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}</select></label><button className="generateButton"><UserPlus size={15} /> Crear y generar contraseñas</button></form>
      <form className="adminForm vertical" onSubmit={createAdmin}><h3>Agregar administración</h3><label>Usuario<input value={admin} onChange={(event) => setAdmin(event.target.value)} required /></label><button className="generateButton"><UserPlus size={15} /> Crear cuenta de administración</button></form>
    </div>
    {created.length > 0 && <div className="secretBox" role="status"><b>Contraseñas generadas (se muestran una sola vez):</b><pre>{copyText}</pre><button className="ghostButton" onClick={() => navigator.clipboard?.writeText(copyText)}><Copy size={14} /> Copiar</button><button className="ghostButton" onClick={() => setCreated([])}>Ocultar</button></div>}
    <table className="adminTable"><thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Último ingreso</th><th>Estado</th><th /></tr></thead><tbody>
      {data?.users.map((user) => <tr key={user.id}><td>{user.username}</td><td>{user.display_name}</td><td>{user.role === "admin" ? "Administración" : "Estudiante"}</td><td>{when(user.last_login_at)}</td><td>{user.disabled ? "Deshabilitado" : "Activo"}</td>
        <td className="rowActions">{user.id !== me.user.id && <>
          <button className="ghostButton" onClick={() => post(`/api/admin/users/${user.id}`, { disabled: !user.disabled }, "PATCH").then(load).catch(onError)}>{user.disabled ? <CircleCheck size={14} /> : <Ban size={14} />} {user.disabled ? "Habilitar" : "Deshabilitar"}</button>
          <button className="ghostButton" onClick={() => reset(user)}><KeyRound size={14} /> Nueva contraseña</button>
          <button className="ghostButton danger" onClick={() => { if (confirm(`¿Borrar a ${user.username} y todos sus archivos?`)) api(`/api/admin/users/${user.id}`, { method: "DELETE" }).then(load).catch(onError); }}><Trash2 size={14} /></button>
        </>}</td></tr>)}
    </tbody></table>
  </>;
}

function WorkersPanel({ onError }: { onError: (error: unknown) => void }) {
  const { data, load } = useLoader<{ workers: WorkerInfo[] }>("/api/admin/workers", onError, 5000);
  const [name, setName] = useState(""); const [token, setToken] = useState<{ id: string; token: string } | null>(null);
  async function create(event: React.FormEvent) {
    event.preventDefault();
    await post<{ id: string; token: string }>("/api/admin/workers", { id: name }).then((result) => { setToken(result); setName(""); load(); }).catch(onError);
  }
  return <>
    <p className="adminMuted">Cada computadora del laboratorio necesita su propio token. Se muestra una sola vez: copialo en <code>worker/.env</code> de esa computadora (o usá <code>scripts/install-worker.ps1</code>).</p>
    <form className="adminForm" onSubmit={create}><label>Nombre de la computadora<input value={name} onChange={(event) => setName(event.target.value)} placeholder="aula-pc-02" pattern="[A-Za-z0-9._\-]{2,40}" required /></label><button className="generateButton">Registrar</button></form>
    {token && <div className="secretBox" role="status"><b>Token de {token.id} (se muestra una sola vez):</b><pre>{token.token}</pre><button className="ghostButton" onClick={() => navigator.clipboard?.writeText(token.token)}><Copy size={14} /> Copiar</button><button className="ghostButton" onClick={() => setToken(null)}>Ocultar</button></div>}
    <table className="adminTable"><thead><tr><th>Computadora</th><th>Estado</th><th>Última señal</th><th>IP</th><th>Versión</th><th /></tr></thead><tbody>
      {data?.workers.map((worker) => <tr key={worker.id}><td>{worker.id}</td><td>{worker.disabled ? "Deshabilitada" : worker.online ? "Conectada" : "Sin conexión"}</td><td>{when(worker.last_seen_at)}</td><td>{worker.ip ?? "—"}</td><td>{worker.backend ? `${worker.backend} ${worker.version ?? ""}` : "—"}</td>
        <td className="rowActions">
          <button className="ghostButton" onClick={() => post(`/api/admin/workers/${worker.id}`, { disabled: !worker.disabled }, "PATCH").then(load).catch(onError)}>{worker.disabled ? "Habilitar" : "Deshabilitar"}</button>
          <button className="ghostButton" onClick={() => post<{ id: string; token: string }>(`/api/admin/workers/${worker.id}/rotate`).then(setToken).catch(onError)}><RefreshCw size={14} /> Nuevo token</button>
          <button className="ghostButton danger" onClick={() => { if (confirm(`¿Quitar ${worker.id}?`)) api(`/api/admin/workers/${worker.id}`, { method: "DELETE" }).then(load).catch(onError); }}><Trash2 size={14} /></button>
        </td></tr>)}
    </tbody></table>
  </>;
}

function PolicyPanel({ onError }: { onError: (error: unknown) => void }) {
  const { data } = useLoader<{ policy: Policy; defaults: Policy; models: { id: string; name: string }[] }>("/api/admin/policy", onError);
  const [draft, setDraft] = useState<Policy | null>(null); const [saved, setSaved] = useState(false);
  const policy = draft ?? data?.policy;
  if (!data || !policy) return <p className="adminMuted">Cargando…</p>;
  const set = (changes: Partial<Policy>) => { setDraft({ ...policy, ...changes }); setSaved(false); };
  const limits: [keyof Policy, string][] = [["max_pixels", "Píxeles máximos por imagen/frame"], ["max_video_frames", "Frames máximos de video"], ["max_steps", "Pasos máximos"], ["max_audio_seconds", "Segundos máximos de audio"], ["max_batch_size", "Resultados por pedido"]];
  return <form className="adminForm vertical" onSubmit={(event) => { event.preventDefault(); post<{ policy: Policy }>("/api/admin/policy", policy, "PUT").then((result) => { setDraft(result.policy); setSaved(true); }).catch(onError); }}>
    <h3>Modelos habilitados para estudiantes</h3>
    <div className="modelChecks">{data.models.map((model) => <label key={model.id}><input type="checkbox" checked={policy.enabled_models.includes(model.id)} onChange={(event) => set({ enabled_models: event.target.checked ? [...policy.enabled_models, model.id] : policy.enabled_models.filter((id) => id !== model.id) })} /> {model.name}</label>)}</div>
    <h3>Límites por pedido</h3>
    <div className="limitGrid">{limits.map(([key, label]) => <label key={key}>{label}<input type="number" min={1} value={policy[key] as number} onChange={(event) => set({ [key]: Number(event.target.value) } as Partial<Policy>)} /></label>)}</div>
    <p className="adminMuted">Referencia: 1280×720 = 921.600 píxeles. Un video de 241 frames en esta GPU puede tardar más de 20 minutos.</p>
    <div className="modalActions"><button type="button" onClick={() => { setDraft(data.defaults); setSaved(false); }}>Valores por defecto</button><button className="primary">Guardar</button></div>
    {saved && <p className="adminMuted">Guardado.</p>}
  </form>;
}

function AuditPanel({ onError }: { onError: (error: unknown) => void }) {
  const { data } = useLoader<{ events: AuditEvent[] }>("/api/admin/audit", onError);
  return <table className="adminTable"><thead><tr><th>Fecha</th><th>Quién</th><th>Acción</th><th>Detalle</th><th>IP</th></tr></thead><tbody>
    {data?.events.map((event) => <tr key={event.id}><td>{when(event.at)}</td><td>{event.actor ?? "—"}</td><td>{event.action}</td><td>{event.detail ?? ""}</td><td>{event.ip ?? ""}</td></tr>)}
  </tbody></table>;
}
