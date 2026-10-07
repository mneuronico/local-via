"use client";

import { Admin } from "@/components/admin";
import { AppGate } from "@/components/app-gate";

export default function AdminPage() {
  return <AppGate>{(me, logout) => <Admin me={me} onLogout={logout} />}</AppGate>;
}
