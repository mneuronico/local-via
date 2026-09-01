"use client";
/* Signed worker URLs are arbitrary and expiring, so Next image optimization cannot proxy them. */
/* eslint-disable @next/next/no-img-element */

import { AudioLines, CircleAlert, Download, Expand, Image as ImageIcon, LoaderCircle, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { describePhase } from "@/lib/job-phase";
import type { Artifact, Job } from "@/lib/types";

function Media({ artifact, alt, large = false }: { artifact: Artifact; alt: string; large?: boolean }) {
  if (artifact.media_type.startsWith("image/")) return <img className={large ? "largeMedia" : ""} src={artifact.url} alt={alt} />;
  if (artifact.media_type.startsWith("video/")) return <video className={large ? "largeMedia" : ""} src={artifact.url} controls autoPlay={large} preload="metadata" />;
  if (artifact.media_type.startsWith("audio/")) return <div className="audioVisual"><AudioLines /><audio src={artifact.url} controls /></div>;
  return <a href={artifact.url} target="_blank" rel="noreferrer">Abrir {artifact.name}</a>;
}

export function ResultViewer({ job, modelName, onCancel }: { job?: Job; modelName?: string; onCancel?: () => void }) {
  const [open, setOpen] = useState<Artifact | null>(null);
  const running = job?.status === "running" || job?.status === "queued";
  const phase = describePhase(job?.phase || job?.status);
  const artifact = job?.artifacts[0];
  const activeOpen = job?.status === "succeeded" && open && job.artifacts.some((item) => item.id === open.id) ? open : null;
  return <>
    <aside className="liveResult" aria-live="polite">
      <div className="liveResultHead"><div><span className="sectionKicker">Resultado actual</span><h2>{modelName ?? "Vista previa"}</h2></div>{job && <span className={`jobState ${job.status}`}>{job.status === "succeeded" ? "Listo" : job.status === "failed" ? "Error" : job.status === "cancelled" ? "Cancelado" : "Generando"}</span>}</div>
      {!job && <div className="emptyLive"><ImageIcon /><h3>Acá aparecerá lo generado</h3><p>Al terminar un trabajo podrás verlo, ampliarlo y descargarlo sin bajar hasta el historial.</p></div>}
      {running && <div className="renderingLive"><LoaderCircle className="spin" /><h3>{phase.label}</h3><p className="phaseHint">{phase.hint}</p><p>{job.prompt}</p><div className="bigProgress"><span style={{ width: `${Math.max(job.progress, 2)}%` }} /></div><small>{job.progress}%</small>{onCancel && <button onClick={onCancel}>Cancelar</button>}</div>}
      {job?.status === "failed" && <div className="failedLive"><CircleAlert /><h3>No se pudo generar</h3><p>{job.error || "El worker informó un error."}</p></div>}
      {job?.status === "cancelled" && <div className="emptyLive"><X /><h3>Generación cancelada</h3></div>}
      {job?.status === "succeeded" && artifact && <div className="completedLive">
        <button className="liveMedia" onClick={() => setOpen(artifact)} aria-label={`Ampliar ${artifact.name}`}><Media artifact={artifact} alt={job.prompt || artifact.name} /><span><Expand size={16} /> Ampliar</span></button>
        <div className="artifactActions"><div><Sparkles size={16} /><span><b>{artifact.name}</b><small>{(artifact.size / 1024 / 1024).toFixed(1)} MB</small></span></div><a href={artifact.url} download={artifact.name}><Download size={16} /> Descargar</a></div>
        {job.artifacts.length > 1 && <div className="artifactStrip">{job.artifacts.slice(1).map((item) => <button key={item.id} onClick={() => setOpen(item)}><Media artifact={item} alt={item.name} /></button>)}</div>}
      </div>}
    </aside>
    {activeOpen && <div className="viewerBackdrop" onMouseDown={() => setOpen(null)}><div className="viewerModal" onMouseDown={(event) => event.stopPropagation()}>
      <div className="viewerToolbar"><span>{activeOpen.name}</span><a href={activeOpen.url} download={activeOpen.name}><Download size={17} /> Descargar</a><button onClick={() => setOpen(null)} aria-label="Cerrar"><X /></button></div>
      <div className="viewerCanvas"><Media artifact={activeOpen} alt={job?.prompt || activeOpen.name} large /></div>
    </div></div>}
  </>;
}
