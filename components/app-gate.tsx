"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { hubApi } from "@/lib/api";
import type { Me } from "@/lib/types";
import { Login } from "./login";

/** Loads the session once; renders the login screen when there is none. */
export function AppGate({ children }: { children: (me: Me, logout: () => void) => React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [checked, setChecked] = useState(false);
  const [offline, setOffline] = useState("");

  useEffect(() => {
    hubApi.session().then((session) => setMe(session.user ? session as Me : null)).catch((error) => setOffline(error instanceof Error ? error.message : "Sin conexión")).finally(() => setChecked(true));
  }, []);

  async function logout() { await hubApi.logout().catch(() => undefined); setMe(null); }

  if (!checked) return <main className="authShell"><LoaderCircle className="spin" aria-label="Cargando" /></main>;
  if (offline && !me) return <main className="authShell"><section className="authCard"><h2>No hay conexión con el servidor</h2><p className="authLead">{offline}</p><button className="generateButton authSubmit" onClick={() => location.reload()}>Reintentar</button></section></main>;
  if (!me) return <Login onLogin={setMe} />;
  return <>{children(me, logout)}</>;
}
