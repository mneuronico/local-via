"use client";

import { KeyRound, LoaderCircle, Sparkles, UserPlus } from "lucide-react";
import { useState } from "react";
import { hubApi } from "@/lib/api";
import type { Me } from "@/lib/types";

export function Login({ onLogin }: { onLogin: (me: Me) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [classCode, setClassCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      onLogin(mode === "login"
        ? await hubApi.login(username, password)
        : await hubApi.register({ class_code: classCode, username, display_name: displayName, password }));
    } catch (failure) { setError(failure instanceof Error ? failure.message : "No se pudo ingresar"); }
    finally { setBusy(false); }
  }

  return <main className="authShell">
    <section className="authCard">
      <div className="brand authBrand"><span className="brandMark"><Sparkles size={17} /></span><span>Local Via</span></div>
      <p className="authLead">Estudio audiovisual de la sala de computación. Tus pedidos se procesan en las computadoras del laboratorio, sin servicios externos.</p>
      <div className="authTabs" role="tablist">
        <button role="tab" aria-selected={mode === "login"} className={mode === "login" ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}><KeyRound size={15} /> Ingresar</button>
        <button role="tab" aria-selected={mode === "register"} className={mode === "register" ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}><UserPlus size={15} /> Crear cuenta</button>
      </div>
      <form onSubmit={submit} className="authForm">
        {mode === "register" && <label>Código de clase<input value={classCode} onChange={(event) => setClassCode(event.target.value)} placeholder="ABCD-1234" autoComplete="off" required /><small>Te lo da la persona a cargo de la clase.</small></label>}
        <label>Usuario<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required minLength={3} maxLength={40} /></label>
        {mode === "register" && <label>Nombre visible <small>(opcional)</small><input value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={80} /></label>}
        <label>Contraseña<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 8 : 1} />{mode === "register" && <small>Mínimo 8 caracteres.</small>}</label>
        {error && <div className="inlineError" role="alert"><span>{error}</span></div>}
        <button className="generateButton authSubmit" disabled={busy}>{busy && <LoaderCircle className="spin" size={16} />}{mode === "login" ? "Ingresar" : "Crear cuenta e ingresar"}</button>
      </form>
      <p className="authFoot">Generación local con <a href="https://github.com/deepbeepmeep/Wan2GP" target="_blank" rel="noreferrer">WanGP</a>.</p>
    </section>
  </main>;
}
