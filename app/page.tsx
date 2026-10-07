"use client";

import { AppGate } from "@/components/app-gate";
import { Studio } from "@/components/studio";

export default function Home() {
  return <AppGate>{(me, logout) => <Studio me={me} onLogout={logout} />}</AppGate>;
}
