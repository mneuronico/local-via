"use client";

import type { ModelDefinition, WorkflowId } from "@/lib/types";

export function ParameterPanel({ model, workflowId, values, negativePrompt, onNegativePrompt, onChange }: {
  model: ModelDefinition;
  values: Record<string, string | number | boolean>;
  workflowId: WorkflowId;
  negativePrompt: string;
  onNegativePrompt: (value: string) => void;
  onChange: (values: Record<string, string | number | boolean>) => void;
}) {
  return <div className="advancedPanel">
    {model.parameters.filter((parameter) => !parameter.workflows || parameter.workflows.includes(workflowId)).map((parameter) => <label key={parameter.key} title={parameter.help}>
      {parameter.label}
      {parameter.type === "select" ? <select value={String(values[parameter.key] ?? "")} onChange={(event) => {
        const option = parameter.options?.find((item) => String(item.value) === event.target.value);
        onChange({ ...values, [parameter.key]: option?.value ?? event.target.value });
      }}><option value="">Predeterminado</option>{parameter.options?.map((option) => <option value={String(option.value)} key={String(option.value)}>{option.label}</option>)}</select>
        : parameter.type === "boolean" ? <input type="checkbox" checked={Boolean(values[parameter.key])} onChange={(event) => onChange({ ...values, [parameter.key]: event.target.checked })} />
        : <input type={parameter.type} min={parameter.min} max={parameter.max} step={parameter.step} value={String(values[parameter.key] ?? "")} onChange={(event) => onChange({ ...values, [parameter.key]: parameter.type === "number" ? Number(event.target.value) : event.target.value })} />}
    </label>)}
    <label className="wide">Prompt negativo<input value={negativePrompt} onChange={(event) => onNegativePrompt(event.target.value)} placeholder="borroso, artefactos, baja calidad…" /></label>
  </div>;
}
