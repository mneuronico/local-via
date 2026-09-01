"use client";
/* Worker artifacts use arbitrary signed URLs and must bypass Next image optimization. */
/* eslint-disable @next/next/no-img-element */

import { Activity, AudioLines, CircleStop, Clock3, Download, Film, FolderOpen, Image as ImageIcon, LoaderCircle, Menu, Mic2, Music2, Play, Plus, RefreshCw, Settings2, SlidersHorizontal, Sparkles, Wifi, WifiOff, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { MODELS, WORKFLOWS, modelsForWorkflow, workflowFor } from "@/lib/models";
import type { Job, ModelDefinition, WorkerStatus, WorkflowId } from "@/lib/types";
import { uploadFile, workerClient, type WorkerConfig } from "@/lib/worker-client";
import { describePhase } from "@/lib/job-phase";
import { ModelInputs } from "./model-inputs";
import { ParameterPanel } from "./parameter-panel";
import { ResultViewer } from "./result-viewer";

const LOCAL_CONFIG: WorkerConfig = { url: "http://127.0.0.1:9000", token: "" };

function defaultConfig(): WorkerConfig {
  if (typeof window === "undefined") return LOCAL_CONFIG;
  const localHost = ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
  return localHost
    ? LOCAL_CONFIG
    : { url: "https://localvia-worker.mneuronico.com", token: "" };
}
const workflowIcon: Record<string, typeof Film> = { image: ImageIcon, video: Film, audio: AudioLines };

function getStoredConfig(): WorkerConfig {
  const fallback = defaultConfig();
  if (typeof window === "undefined") return fallback;
  try { return { ...fallback, ...JSON.parse(localStorage.getItem("local-via-worker") ?? "{}") }; } catch { return fallback; }
}
function timeAgo(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000));
  if (seconds < 60) return "ahora";
  if (seconds < 3600) return `hace ${Math.floor(seconds / 60)} min`;
  if (seconds < 86400) return `hace ${Math.floor(seconds / 3600)} h`;
  return `hace ${Math.floor(seconds / 86400)} d`;
}

export function Studio() {
  const [workflowId, setWorkflowId] = useState<WorkflowId>("text-to-image");
  const initialModel = modelsForWorkflow("text-to-image")[0];
  const [modelId, setModelId] = useState(initialModel.id);
  const [prompt, setPrompt] = useState("");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [config, setConfig] = useState<WorkerConfig>(LOCAL_CONFIG);
  const [draftConfig, setDraftConfig] = useState<WorkerConfig>(LOCAL_CONFIG);
  const [configReady, setConfigReady] = useState(false);
  const [status, setStatus] = useState<WorkerStatus | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [installedModels, setInstalledModels] = useState<Record<string, boolean>>({});
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [connectionError, setConnectionError] = useState("");
  const [hasConnectedOnce, setHasConnectedOnce] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [files, setFiles] = useState<Record<string, File[]>>({});

  const models = useMemo(() => modelsForWorkflow(workflowId), [workflowId]);
  const selected = models.find((model) => model.id === modelId) ?? models[0];
  const selectedWorkflow = workflowFor(selected, workflowId);
  const [parameters, setParameters] = useState<Record<string, string | number | boolean>>(selectedWorkflow.defaults);
  const currentJob = jobs.find((job) => job.id === currentJobId) ?? jobs.find((job) => job.status === "running" || job.status === "queued") ?? jobs[0];
  const activeJob = jobs.find((job) => job.status === "running" || job.status === "queued");
  const workflow = WORKFLOWS.find((item) => item.id === workflowId)!;

  const refresh = useCallback(async (quiet = false) => {
    try {
      const [workerStatus, jobList] = await Promise.all([workerClient.status(config), workerClient.jobs(config)]);
      setStatus(workerStatus); setJobs(jobList.jobs); setConnectionError(""); setHasConnectedOnce(true);
    } catch (error) {
      setStatus(null); if (!quiet && hasConnectedOnce) setConnectionError(error instanceof Error ? error.message : "No se pudo conectar");
    }
  }, [config, hasConnectedOnce]);

  useEffect(() => { const timer = window.setTimeout(() => { const stored = getStoredConfig(); setConfig(stored); setDraftConfig(stored); setConfigReady(true); }, 0); return () => window.clearTimeout(timer); }, []);
  useEffect(() => { if (!configReady) return; const initial = window.setTimeout(() => void refresh(), 0); const timer = window.setInterval(() => void refresh(true), 2500); return () => { window.clearTimeout(initial); window.clearInterval(timer); }; }, [configReady, refresh]);
  useEffect(() => { if (!configReady) return; void workerClient.models(config).then(({ models }) => setInstalledModels(Object.fromEntries(models.map((model) => [model.id, model.installed])))).catch(() => undefined); }, [config, configReady]);

  function chooseWorkflow(id: WorkflowId) {
    const first = modelsForWorkflow(id)[0]; setWorkflowId(id); setModelId(first.id); setParameters(first.workflows.find((item) => item.id === id)!.defaults); setFiles({}); setNegativePrompt(""); setMobileOpen(false);
  }
  function chooseModel(model: ModelDefinition) {
    const item = workflowFor(model, workflowId); setModelId(model.id); setParameters(item.defaults); setFiles({}); setNegativePrompt("");
  }
  function saveConfig() { const normalized = { url: draftConfig.url.replace(/\/$/, ""), token: draftConfig.token.trim() }; localStorage.setItem("local-via-worker", JSON.stringify(normalized)); setConfig(normalized); setConfigOpen(false); }

  async function generate() {
    const promptOptional = selectedWorkflow.task === "audio.convert" || selectedWorkflow.task === "character.animate";
    if (!prompt.trim() && !promptOptional) { setConnectionError("Escribí una instrucción para generar."); return; }
    const missing = selectedWorkflow.inputs.find((input) => input.required && !(files[input.key]?.length));
    if (missing) { setConnectionError(`Falta cargar: ${missing.label}`); return; }
    setSubmitting(true); setConnectionError("");
    try {
      const inputs: Record<string, string | string[]> = {};
      const allFiles = Object.values(files).flat(); let completed = 0;
      for (const [key, values] of Object.entries(files)) {
        const ids: string[] = [];
        for (const file of values) { ids.push(await uploadFile(config, file, (value) => setUploadProgress(Math.round(((completed + value / 100) / Math.max(allFiles.length, 1)) * 100)))); completed += 1; }
        inputs[key] = ids.length === 1 && !selectedWorkflow.inputs.find((item) => item.key === key)?.multiple ? ids[0] : ids;
      }
      const job = await workerClient.createJob(config, { project_id: "default", model: selected.id, task: selectedWorkflow.task, prompt, inputs, parameters: { ...parameters, negative_prompt: negativePrompt || undefined } });
      setCurrentJobId(job.id); setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]); setFiles({}); setUploadProgress(null); await refresh(true);
    } catch (error) { setConnectionError(error instanceof Error ? error.message : "No se pudo crear el trabajo"); }
    finally { setSubmitting(false); setUploadProgress(null); }
  }

  return <div className="shell">
    <aside className={`sidebar ${mobileOpen ? "sidebarOpen" : ""}`}>
      <div className="brand"><span className="brandMark"><Sparkles size={17} /></span><span>Local Via</span><button className="mobileClose" onClick={() => setMobileOpen(false)} aria-label="Cerrar menú"><X /></button></div>
      <button className="newProject"><Plus size={17} /> Nuevo proyecto</button>
      <nav className="primaryNav" aria-label="Modalidades de generación"><p className="eyebrow">Modalidades</p>{WORKFLOWS.map((item) => { const Icon = workflowIcon[item.output]; return <button key={item.id} className={workflowId === item.id ? "navActive" : ""} onClick={() => chooseWorkflow(item.id)}><Icon size={17} />{item.shortLabel}</button>; })}</nav>
      <div className="projects"><p className="eyebrow">Proyecto</p><button><FolderOpen size={16} /><span><b>Laboratorio visual</b><small>{jobs.length} generaciones</small></span></button></div>
      <div className="workerMini"><div><span className={`statusDot ${status ? "online" : ""}`} /> <b>{status ? "Worker conectado" : "Worker sin conexión"}</b></div><small>{status?.gpu?.name ?? "Worker local o remoto"}</small><button onClick={() => setConfigOpen(true)}><Settings2 size={15} /> Configurar</button></div>
    </aside>

    <main className="main">
      <header className="topbar"><button className="menuButton" onClick={() => setMobileOpen(true)} aria-label="Abrir menú"><Menu /></button><div><p className="topEyebrow">Estudio audiovisual local</p><h1>{workflow.label}</h1></div><div className="topActions"><button className="iconButton" onClick={() => refresh()} aria-label="Actualizar"><RefreshCw size={18} /></button><button className={`connectionPill ${status ? "connected" : ""}`} onClick={() => setConfigOpen(true)}>{status ? <Wifi size={15} /> : <WifiOff size={15} />} {status ? status.worker_id : "Conectar worker"}</button></div></header>
      <section className="workspace">
        <div className="intro"><div><span className="sectionKicker">{workflow.label}</span><h2>{workflow.description}</h2><p>Elegí el modelo según el resultado que querés. Un mismo modelo aparece en cada modalidad que realmente admite.</p></div>{status?.gpu && <div className="hardwareCard"><Activity size={18} /><span><small>GPU disponible</small><b>{status.gpu.name}</b></span><strong>{Math.round(status.gpu.vram_free_mb / 1024)} GB libres</strong></div>}</div>
        <div className="modelScroller">{models.map((model) => <button key={model.id} className={`modelCard ${model.id === selected.id ? "modelSelected" : ""}`} style={{ "--accent": model.accent } as React.CSSProperties} onClick={() => chooseModel(model)}><div className="modelCardTop"><span className="modelIcon">{workflow.output === "video" ? <Film /> : workflow.output === "image" ? <ImageIcon /> : workflowId.includes("speech") || workflowId === "voice-clone" ? <Mic2 /> : workflowId.includes("music") ? <Music2 /> : <AudioLines />}</span><span className="tier">{model.tier}</span></div><h3>{model.name}</h3><p>{model.summary}</p><div className="modelMeta"><span>{model.family}</span><span>{installedModels[model.id] === true ? "Descargado" : installedModels[model.id] === false ? "Se descarga al usar" : model.license}</span></div></button>)}</div>

        <div className="creationGrid">
          <section className="composer">
            <div className="composerHead"><div><span className="selectedAccent" style={{ background: selected.accent }} /><span>{workflow.label}</span></div><button onClick={() => setAdvanced(!advanced)}><SlidersHorizontal size={16} /> Parámetros</button></div>
            <label className="promptLabel" htmlFor="prompt">{workflowId.includes("music") ? "Concepto, estilo o letra" : workflowId.includes("speech") || workflowId === "voice-clone" ? "Texto a pronunciar y dirección de voz" : "Instrucción creativa"}</label>
            <textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder={workflowId === "image-to-image" ? "Conservá la identidad, cambiá la escena a una noche lluviosa…" : workflowId === "text-to-speech" ? "[voz cálida y serena] Bienvenidos…" : "Describí el contenido, el estilo y los detalles importantes…"} />
            <ModelInputs definitions={selectedWorkflow.inputs} files={files} onChange={setFiles} />
            {advanced && <ParameterPanel model={selected} workflowId={workflowId} values={parameters} negativePrompt={negativePrompt} onNegativePrompt={setNegativePrompt} onChange={setParameters} />}
            {connectionError && <div className="inlineError"><WifiOff size={16} /><span>{connectionError}</span><button onClick={() => setConfigOpen(true)}>Configurar</button></div>}
            <div className="composerFooter"><div><span className="licenseTag">{selected.license}</span><span className="backendTag">WanGP</span></div><button className="generateButton" onClick={generate} disabled={submitting || !!activeJob}><Play size={17} fill="currentColor" />{submitting ? (uploadProgress !== null ? `Subiendo ${uploadProgress}%` : "Preparando…") : activeJob ? "GPU ocupada" : "Generar"}</button></div>
          </section>
          <ResultViewer job={currentJob} modelName={currentJob ? MODELS.find((item) => item.id === currentJob.model)?.name : selected.name} onCancel={activeJob && currentJob?.id === activeJob.id ? async () => { await workerClient.cancelJob(config, activeJob.id); refresh(true); } : undefined} />
        </div>

        <section className="activitySection"><div className="resultsHead"><div><span className="sectionKicker">Cola e historial</span><h2>Actividad</h2></div><Clock3 size={18} /></div><div className="jobList horizontalJobs">{jobs.slice(0, 8).map((job) => <JobRow key={job.id} job={job} selected={job.id === currentJob?.id} onSelect={() => setCurrentJobId(job.id)} />)}{jobs.length === 0 && <div className="resultsEmpty"><Sparkles /><span>Todavía no hay generaciones.</span></div>}</div></section>
        <section className="results"><div className="resultsHead"><div><span className="sectionKicker">Archivos locales</span><h2>Resultados recientes</h2></div><span>Podés abrir o descargar cualquier resultado.</span></div><div className="resultGrid">{jobs.flatMap((job) => job.artifacts.map((artifact) => ({ artifact, job }))).slice(0, 9).map(({ artifact, job }) => <article className="resultCard" key={artifact.id}><button className="historyMedia" onClick={() => setCurrentJobId(job.id)}>{artifact.media_type.startsWith("image/") ? <img src={artifact.url} alt={job.prompt || artifact.name} /> : artifact.media_type.startsWith("video/") ? <video src={artifact.url} preload="metadata" /> : <div className="audioVisual"><AudioLines /></div>}</button><div className="resultInfo"><span className="resultModel">{MODELS.find((model) => model.id === job.model)?.name ?? job.model}</span><p>{job.prompt || "Transformación de medios"}</p><small>{timeAgo(job.updated_at)} · {(artifact.size / 1024 / 1024).toFixed(1)} MB</small><a href={artifact.url} download={artifact.name} aria-label={`Descargar ${artifact.name}`}><Download size={15} /></a></div></article>)}{jobs.every((job) => job.artifacts.length === 0) && <div className="resultsEmpty"><ImageIcon /><span>Los outputs se mostrarán acá y arriba al terminar.</span></div>}</div></section>
      </section>
    </main>

    {configOpen && <div className="modalBackdrop" onMouseDown={() => setConfigOpen(false)}><div className="modal" onMouseDown={(event) => event.stopPropagation()}><div className="modalHead"><div><span className="sectionKicker">Conexión</span><h2>Worker</h2></div><button onClick={() => setConfigOpen(false)}><X /></button></div><p>En esta computadora, la URL local funciona sin token. Una web remota usa la URL HTTPS del túnel y sí necesita el token privado.</p><label>URL del worker<input value={draftConfig.url} onChange={(event) => setDraftConfig({ ...draftConfig, url: event.target.value })} placeholder="http://127.0.0.1:9000" /></label><label>Token remoto <small>(opcional en local)</small><input type="password" value={draftConfig.token} onChange={(event) => setDraftConfig({ ...draftConfig, token: event.target.value })} placeholder="Solo para acceso remoto" /></label><div className="modalHint"><Wifi size={17} /><span>Local: <code>http://127.0.0.1:9000</code>, sin copiar credenciales. Remoto: HTTPS + token.</span></div><div className="modalActions"><button onClick={() => setConfigOpen(false)}>Cancelar</button><button className="primary" onClick={saveConfig}>Guardar y conectar</button></div></div></div>}
  </div>;
}

function JobRow({ job, selected, onSelect }: { job: Job; selected: boolean; onSelect: () => void }) {
  const model = MODELS.find((item) => item.id === job.model); const running = job.status === "running" || job.status === "queued"; const phase = describePhase(job.phase || job.status);
  return <button className={`jobRow ${selected ? "selectedJob" : ""}`} onClick={onSelect}><div className="jobTop"><span className="jobIcon" style={{ background: model?.accent }}>{running ? <LoaderCircle className="spin" /> : job.status === "succeeded" ? <Sparkles /> : <CircleStop />}</span><div><b>{model?.name ?? job.model}</b><small>{phase.label} · {timeAgo(job.created_at)}</small></div></div><p>{job.prompt || "Transformación de medios"}</p>{running && <div className="progress"><span style={{ width: `${Math.max(3, job.progress)}%` }} /><small>{job.progress}%</small></div>}{job.error && <small className="jobError">{job.error}</small>}</button>;
}
