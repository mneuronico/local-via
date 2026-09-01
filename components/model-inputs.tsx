"use client";

import { FileImage, Plus, Trash2, UploadCloud } from "lucide-react";
import type { InputDefinition } from "@/lib/types";

export function ModelInputs({ definitions, files, onChange }: {
  definitions: InputDefinition[];
  files: Record<string, File[]>;
  onChange: (files: Record<string, File[]>) => void;
}) {
  if (!definitions.length) return null;
  return <div className="inputGrid">
    {definitions.map((input) => {
      const current = files[input.key] ?? [];
      const remaining = input.max ? input.max - current.length : Infinity;
      return <section className={`mediaInput ${current.length ? "hasFile" : ""}`} key={input.key}>
        <div className="mediaInputHead">
          <span><b>{input.label}</b><small>{input.required ? "Requerido" : "Opcional"}{input.multiple ? " · varias referencias" : ""}</small></span>
          {input.multiple && current.length > 0 && <em>{current.length}{input.max ? `/${input.max}` : ""}</em>}
        </div>
        <p>{input.help}</p>
        {current.length > 0 && <div className="fileList">{current.map((file, index) => <div className="fileChip" key={`${file.name}-${file.lastModified}-${index}`}>
          <FileImage size={15} /><span><b>{input.multiple ? `${index + 1} · ${file.name}` : file.name}</b><small>{(file.size / 1024 / 1024).toFixed(1)} MB</small></span>
          <button type="button" onClick={() => onChange({ ...files, [input.key]: current.filter((_, fileIndex) => fileIndex !== index) })} aria-label={`Quitar ${file.name}`}><Trash2 size={14} /></button>
        </div>)}</div>}
        {remaining > 0 && <label className="dropzone">
          <input type="file" accept={input.accept} multiple={input.multiple} onChange={(event) => {
            const picked = Array.from(event.target.files ?? []).slice(0, remaining);
            if (!picked.length) return;
            onChange({ ...files, [input.key]: input.multiple ? [...current, ...picked] : picked.slice(0, 1) });
            event.target.value = "";
          }} />
          {input.multiple && current.length ? <Plus size={18} /> : <UploadCloud size={18} />}
          <span>{current.length ? "Agregar otra referencia" : "Elegir archivo"}</span>
        </label>}
      </section>;
    })}
  </div>;
}
