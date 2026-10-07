"use client";
/* Hub artifact URLs are same-origin API routes that need the session cookie, so Next image optimization cannot proxy them. */
/* eslint-disable @next/next/no-img-element */

import { AudioLines, CircleStop, Clock3, Download, Film, Image as ImageIcon, KeyRound, LoaderCircle, LogOut, Menu, Mic2, Music2, Play, RefreshCw, Shield, SlidersHorizontal, Sparkles, Users, WifiOff, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MODELS, WORKFLOWS, modelsForWorkflow, workflowFor } from "@/lib/models";
import type { Job, Me, ModelDefinition, Room, WorkflowId } from "@/lib/types";
import { ApiError, formatWait, hubApi, uploadFile } from "@/lib/api";
import { describePhase } from "@/lib/job-phase";
import { ModelInputs } from "./model-inputs";
import { ParameterPanel } from "./parameter-panel";
import { ResultViewer } from "./result-viewer";

const ACTIVE_POLL_MS = 2500;
const IDLE_POLL_MS = 10000;
const workflowIcon: Record<string, typeof Film> = { image: ImageIcon, video: Film, audio: AudioLines };

function timeAgo(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`;
  return `hace ${Math.floor(seconds / 86400)} d`;
}

export function Studio({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [workflowId, setWorkflowId] = useState<WorkflowId>("text-to-image");
  const initialModel = modelsForWorkflow("text-to-image")[0];
  const [modelId, setModelId] = useState(initialModel.id);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [room, setRoom] = useState<Room | null>(null);
  const [catalog, setCatalog] = useState<Record<string, { enabled: boolean; available: boolean }>>({});
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [connected, setConnected] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [files, setFiles] = useState<Record<string, File[]>>({});
  const poke = useRef<() => void>(() => undefined);

  const models = useMemo(() => modelsForWorkflow(workflowId), [workflowId]);
  const selected = models.find((model) => model.id === modelId) ?? models[0];
  const selectedWorkflow = workflowFor(selected, workflowId);
  const [parameters, setParameters] = useState<Record<string, string | number | boolean>>(selectedWorkflow.defaults);
  const activeJob = jobs.find((job) => job.status === "running" || job.status === "queued");
  const currentJob = jobs.find((job) => job.id === currentJobId) ?? activeJob ?? jobs[0];
  const workflow = WORKFLOWS.find((item) => item.id === workflowId)!;
  const selectedState = catalog[selected.id];
  const blockedReason = selectedState && !selectedState.enabled ? "Este modelo no está habilitado en la sala." : selectedState && !selectedState.available ? "Ninguna computadora conectada tiene este modelo ahora." : "";
  const atLimit = me.user.role !== "admin" && jobs.filter((job) => job.status === "running" || job.status === "queued").length >= me.limits.max_active_jobs;

  const refresh = useCallback(async () => {
    try {
      const state = await hubApi.state();
      setJobs(state.jobs); setRoom(state.room); setConnected(true);
      return state.jobs.some((job) => job.status === "running" || job.status === "queued");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) { onLogout(); return false; }
      setConnected(false); return false;
    }
  }, [onLogout]);

  // Polls fast only while the student has work in progress, and never while the tab is hidden.
  useEffect(() => {
    let handle: number | undefined; let generation = 0; let stopped = false;
    const tick = async (mine: number) => {
      const busy = document.hidden ? false : await refresh();
      if (!stopped && mine === generation) handle = window.setTimeout(() => void tick(mine), busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    };
    const now = () => { window.clearTimeout(handle); generation += 1; const mine = generation; handle = window.setTimeout(() => void tick(mine), 0); };
    poke.current = now;
    now();
    const onVisible = () => { if (!document.hidden) now(); };
    document.addEventListener("visibilitychange", onVisible);
    return () => { stopped = true; window.clearTimeout(handle); document.removeEventListener("visibilitychange", onVisible); };
  }, [refresh]);

  // Model availability depends on which computers are online, so reload it whenever that changes.
  const workersOnline = room?.workers_online;
  useEffect(() => {
    const load = () => hubApi.catalog().then(({ models }) => setCatalog(Object.fromEntries(models.map((model) => [model.id, model])))).catch(() => undefined);
    load(); const interval = window.setInterval(load, 60000);
    return () => window.clearInterval(interval);
  }, [workersOnline]);

  function chooseWorkflow(id: WorkflowId) {
    const first = modelsForWorkflow(id)[0]; setWorkflowId(id); setModelId(first.id); setParameters(first.workflows.find((item) => item.id === id)!.defaults); setFiles({}); setNegativePrompt(""); setMobileOpen(false);
  }
  function chooseModel(model: ModelDefinition) {
    const item = workflowFor(model, workflowId); setModelId(model.id); setParameters(item.defaults); setFiles({}); setNegativePrompt("");
  }

  async function generate() {
    const promptOptional = selectedWorkflow.task === "audio.convert" || selectedWorkflow.task === "character.animate";
    if (!prompt.trim() && !promptOptional) { setMessage("Escribí una instrucción para generar."); return; }
    const missing = selectedWorkflow.inputs.find((input) => input.required && !(files[input.key]?.length));
    if (missing) { setMessage(`Falta cargar: ${missing.label}`); return; }
    const tooBig = Object.values(files).flat().find((file) => file.size > me.limits.max_upload_mb * 1024 * 1024);
    if (tooBig) { setMessage(`${tooBig.name} supera el máximo de ${me.limits.max_upload_mb} MB.`); return; }
    setSubmitting(true); setMessage("");
    try {
      const inputs: Record<string, string | string[]> = {};
      const allFiles = Object.values(files).flat(); let completed = 0;
      for (const [key, values] of Object.entries(files)) {
        const ids: string[] = [];
        for (const file of values) { ids.push(await uploadFile(file, key, (value) => setUploadProgress(Math.round(((completed + value / 100) / Math.max(allFiles.length, 1)) * 100)))); completed += 1; }
        inputs[key] = ids.length === 1 && !selectedWorkflow.inputs.find((item) => item.key === key)?.multiple ? ids[0] : ids;
      }
      const job = await hubApi.createJob({ model: selected.id, task: selectedWorkflow.task, prompt, inputs, parameters: { ...parameters, negative_prompt: negativePrompt || undefined } });
      setCurrentJobId(job.id); setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]); setFiles({});
      poke.current();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) onLogout();
      setMessage(error instanceof Error ? error.message : "No se pudo crear el pedido");
    } finally { setSubmitting(false); setUploadProgress(null); }
  }

  async function cancel(job: Job) { await hubApi.cancelJob(job.id).catch((error) => setMessage(error.message)); poke.current(); }
  async function remove(job: Job) { await hubApi.deleteJob(job.id).catch((error) => setMessage(error.message)); setCurrentJobId(null); poke.current(); }

  const free = room ? Math.max(0, room.workers_online - room.workers_busy) : 0;
  const generateLabel = submitting ? (uploadProgress !== null ? `Subiendo ${uploadProgress}%` : "Enviando…") : atLimit ? "Tenés un pedido en curso" : "Generar";

  return <div className="shell">
    <aside className={`sidebar ${mobileOpen ? "sidebarOpen" : ""}`}>
      <div className="brand"><span className="brandMark"><Sparkles size={17} /></span><span>Local Via</span><button className="mobileClose" onClick={() => setMobileOpen(false)} aria-label="Cerrar menú"><X /></button></div>
      <nav className="primaryNav" aria-label="Modalidades de generación"><p className="eyebrow">Modalidades</p>{WORKFLOWS.map((item) => { const Icon = workflowIcon[item.output]; return <button key={item.id} className={workflowId === item.id ? "navActive" : ""} onClick={() => chooseWorkflow(item.id)}><Icon size={17} />{item.shortLabel}</button>; })}</nav>
      <div className="workerMini roomMini" aria-label="Estado de la sala">
        <div><span className={`statusDot ${connected && room?.workers_online ? "online" : ""}`} /> <b>{!connected ? "Sin conexión" : room ? `${free} de ${room.workers_online} computadoras libres` : "Conectando…"}</b></div>
        <small>{room ? `${room.queued_total} pedido${room.queued_total === 1 ? "" : "s"} en cola · ${room.running_total} generando` : "Sala de computación"}</small>
      </div>
    </aside>

    <main className="main">
      <header className="topbar"><button className="menuButton" onClick={() => setMobileOpen(true)} aria-label="Abrir menú"><Menu /></button><div><p className="topEyebrow">Sala de computación</p><h1>{workflow.label}</h1></div>
        <div className="topActions">
          <button className="iconButton" onClick={() => poke.current()} aria-label="Actualizar"><RefreshCw size={18} /></button>
          {me.user.role === "admin" && <a className="iconButton" href="/admin/" aria-label="Administración" title="Administración"><Shield size={18} /></a>}
          <button className="iconButton" onClick={() => setPasswordOpen(true)} aria-label="Cambiar contraseña" title="Cambiar contraseña"><KeyRound size={18} /></button>
          <button className={`connectionPill ${connected ? "connected" : ""}`} onClick={onLogout} title="Cerrar sesión"><Users size={15} /> {me.user.display_name} <LogOut size={14} /></button>
        </div>
      </header>
      <section className="workspace">
        <div className="intro"><div><span className="sectionKicker">{workflow.label}</span><h2>{workflow.description}</h2><p>Elegí el modelo según el resultado que querés. Tu pedido entra en una cola común y lo procesa la primera computadora libre de la sala.</p></div>
          {room && <div className="hardwareCard"><Clock3 size={18} /><span><small>Sala</small><b>{room.workers_online} computadoras conectadas</b></span><strong>{room.queued_total} en cola</strong></div>}</div>
        <div className="modelScroller">{models.map((model) => { const state = catalog[model.id]; return <button key={model.id} className={`modelCard ${model.id === selected.id ? "modelSelected" : ""}`} style={{ "--accent": model.accent } as React.CSSProperties} onClick={() => chooseModel(model)}><div className="modelCardTop"><span className="modelIcon">{workflow.output === "video" ? <Film /> : workflow.output === "image" ? <ImageIcon /> : workflowId.includes("speech") || workflowId === "voice-clone" ? <Mic2 /> : workflowId.includes("music") ? <Music2 /> : <AudioLines />}</span><span className="tier">{model.tier}</span></div><h3>{model.name}</h3><p>{model.summary}</p><div className="modelMeta"><span>{model.family}</span><span className={state && (!state.enabled || !state.available) ? "unavailable" : ""}>{!state ? model.license : !state.enabled ? "No habilitado" : !state.available ? "No disponible" : "Disponible"}</span></div></button>; })}</div>

        <div className="creationGrid">
          <section className="composer">
            <div className="composerHead"><div><span className="selectedAccent" style={{ background: selected.accent }} /><span>{workflow.label}</span></div><button onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={16} /> Parámetros</button></div>
            <label className="promptLabel" htmlFor="prompt">{workflowId.includes("music") ? "Concepto, estilo o letra" : workflowId.includes("speech") || workflowId === "voice-clone" ? "Texto a pronunciar y dirección de voz" : "Instrucción creativa"}</label>
            <textarea id="prompt" value={prompt} maxLength={4000} onChange={(event) => setPrompt(event.target.value)} placeholder={workflowId === "image-to-image" ? "Conservá la identidad, cambiá la escena a una noche lluviosa…" : workflowId === "text-to-speech" ? "[voz cálida y serena] Bienvenidos…" : "Describí el contenido, el estilo y los detalles importantes…"} />
            <ModelInputs definitions={selectedWorkflow.inputs} files={files} onChange={setFiles} />
            {advanced && <ParameterPanel model={selected} workflowId={workflowId} values={parameters} negativePrompt={negativePrompt} onNegativePrompt={setNegativePrompt} onChange={setParameters} />}
            {(message || blockedReason || !connected) && <div className="inlineError" role="alert"><WifiOff size={16} /><span>{!connected ? "Se perdió la conexión con el servidor de la sala. Reintentando…" : message || blockedReason}</span></div>}
            <div className="composerFooter"><div><span className="licenseTag">{selected.license}</span><span className="backendTag">WanGP</span></div><button className="generateButton" onClick={generate} disabled={submitting || atLimit || !!blockedReason}><Play size={17} fill="currentColor" />{generateLabel}</button></div>
          </section>
          <ResultViewer job={currentJob} modelName={currentJob?.model_name ?? selected.name}
            onCancel={currentJob && (currentJob.status === "queued" || currentJob.status === "running") ? () => cancel(currentJob) : undefined}
            onDelete={currentJob && !(currentJob.status === "queued" || currentJob.status === "running") ? () => remove(currentJob) : undefined} />
        </div>

        <section className="activitySection"><div className="resultsHead"><div><span className="sectionKicker">Tus pedidos</span><h2>Actividad</h2></div><span>Los resultados se guardan {me.limits.retention_days} días.</span></div><div className="jobList horizontalJobs">{jobs.slice(0, 8).map((job) => <JobRow key={job.id} job={job} selected={job.id === currentJob?.id} onSelect={() => setCurrentJobId(job.id)} />)}{jobs.length === 0 && <div className="resultsEmpty"><Sparkles /><span>Todavía no hiciste pedidos.</span></div>}</div></section>
        <section className="results"><div className="resultsHead"><div><span className="sectionKicker">Tus archivos</span><h2>Resultados recientes</h2></div><span>Solo vos podés ver tus resultados.</span></div><div className="resultGrid">{jobs.flatMap((job) => job.artifacts.map((artifact) => ({ artifact, job }))).slice(0, 9).map(({ artifact, job }) => <article className="resultCard" key={artifact.id}><button className="historyMedia" onClick={() => setCurrentJobId(job.id)}>{artifact.media_type.startsWith("image/") ? <img src={artifact.url} alt={job.prompt || artifact.name} loading="lazy" /> : artifact.media_type.startsWith("video/") ? <video src={artifact.url} preload="none" /> : <div className="audioVisual"><AudioLines /></div>}</button><div className="resultInfo"><span className="resultModel">{job.model_name}</span><p>{job.prompt || "Transformación de medios"}</p><small>{timeAgo(job.updated_at)} · {(artifact.size / 1024 / 1024).toFixed(1)} MB</small><a href={`${artifact.url}?download=1`} download={artifact.name} aria-label={`Descargar ${artifact.name}`}><Download size={15} /></a></div></article>)}{jobs.every((job) => job.artifacts.length === 0) && <div className="resultsEmpty"><ImageIcon /><span>Los resultados aparecerán acá y arriba al terminar.</span></div>}</div></section>
      </section>
    </main>
    {passwordOpen && <PasswordModal onClose={() => setPasswordOpen(false)} />}
  </div>;
}

function PasswordModal({ onClose }: { onClose: () => void }) {
  const [current, setCurrent] = useState(""); const [next, setNext] = useState(""); const [status, setStatus] = useState("");
  async function save(event: React.FormEvent) {
    event.preventDefault();
    try { await hubApi.changePassword(current, next); setStatus("Contraseña actualizada. Las otras sesiones se cerraron."); setCurrent(""); setNext(""); }
    catch (error) { setStatus(error instanceof Error ? error.message : "No se pudo cambiar"); }
  }
  return <div className="modalBackdrop" onMouseDown={onClose}><form className="modal" onMouseDown={(event) => event.stopPropagation()} onSubmit={save}>
    <div className="modalHead"><div><span className="sectionKicker">Cuenta</span><h2>Contraseña</h2></div><button type="button" onClick={onClose} aria-label="Cerrar"><X /></button></div>
    <label>Contraseña actual<input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" required /></label>
    <label>Contraseña nueva<input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" minLength={8} required /></label>
    {status && <p>{status}</p>}
    <div className="modalActions"><button type="button" onClick={onClose}>Cerrar</button><button className="primary">Guardar</button></div>
  </form></div>;
}

function JobRow({ job, selected, onSelect }: { job: Job; selected: boolean; onSelect: () => void }) {
  const model = MODELS.find((item) => item.id === job.model); const running = job.status === "running" || job.status === "queued"; const phase = describePhase(job.phase || job.status);
  const detail = job.status === "queued" && job.queue ? `Puesto ${job.queue.position} · ${formatWait(job.queue.estimated_wait_seconds)}` : phase.label;
  return <button className={`jobRow ${selected ? "selectedJob" : ""}`} onClick={onSelect}><div className="jobTop"><span className="jobIcon" style={{ background: model?.accent }}>{running ? <LoaderCircle className="spin" /> : job.status === "succeeded" ? <Sparkles /> : <CircleStop />}</span><div><b>{job.model_name}</b><small>{detail} · {timeAgo(job.created_at)}</small></div></div><p>{job.prompt || "Transformación de medios"}</p>{job.status === "running" && <div className="progress"><span style={{ width: `${Math.max(3, job.progress)}%` }} /><small>{job.progress}%</small></div>}{job.error && <small className="jobError">{job.error}</small>}</button>;
}
