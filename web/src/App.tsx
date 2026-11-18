import { useEffect, useState } from "react";
import { api, connectWS } from "./api";
import type { SystemState } from "./types";
import Overview from "./pages/Overview";
import Devices from "./pages/Devices";
import Orders from "./pages/Orders";
import Logs from "./pages/Logs";
import Settings from "./pages/Settings";
import Strategy from "./pages/Strategy";

type Page = "overview" | "strategy" | "devices" | "orders" | "logs" | "settings";

export default function App() {
  const [page, setPage] = useState<Page>("overview");
  const [state, setState] = useState<SystemState | null>(null);

  const refreshState = () => {
    api.getSystem().then(setState).catch(() => {});
  };

  useEffect(() => {
    refreshState();
    const unsub = connectWS((event, data) => {
      if (event === "system_state") {
        setState(data as SystemState);
      } else {
        refreshState();
      }
    });
    return unsub;
  }, []);

  const toggleKillSwitch = async () => {
    if (!state) return;
    const next = !state.kill_switch;
    const updated = await api.setKillSwitch(next);
    setState(updated);
  };

  const toggleDryRun = async () => {
    if (!state) return;
    const next = !state.dry_run;
    const updated = await api.setDryRun(next);
    setState(updated);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0b0d11] text-zinc-100">
      {/* Top Header / Master Bar */}
      <header className="h-14 border-b border-zinc-800/80 px-6 flex items-center justify-between bg-zinc-950/60 backdrop-blur sticky top-0 z-50">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
            <span className="font-bold tracking-wider text-sm mono">SINYALCI</span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-bold mono border ${
                state?.env_mode === "vps"
                  ? "bg-sky-500/15 border-sky-500/40 text-sky-400"
                  : "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
              }`}
            >
              {state?.env_mode === "vps" ? "VPS (BULUT)" : "LOKAL (PC)"}
            </span>
          </div>

          <nav className="flex items-center gap-1 text-xs">
            {(["overview", "strategy", "devices", "orders", "logs", "settings"] as Page[]).map((p) => (
              <button
                key={p}
                onClick={() => setPage(p)}
                className={`px-3 py-1.5 rounded font-medium transition capitalize ${
                  page === p
                    ? "bg-zinc-800 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40"
                }`}
              >
                {p === "overview"
                  ? "Genel Bakış"
                  : p === "strategy"
                  ? "🎯 Strateji & Sinyaller"
                  : p === "devices"
                  ? "Cihazlar"
                  : p === "orders"
                  ? "Emirler"
                  : p === "logs"
                  ? "Kayıtlar"
                  : "Ayarlar"}
              </button>
            ))}
          </nav>
        </div>

        {/* Master Switches */}
        <div className="flex items-center gap-3">
          {/* Dry Run Toggle */}
          <button
            onClick={toggleDryRun}
            className={`px-3 py-1 rounded text-xs font-semibold mono border transition ${
              state?.dry_run
                ? "bg-amber-500/10 border-amber-500/40 text-amber-400"
                : "bg-zinc-800/50 border-zinc-700 text-zinc-400"
            }`}
          >
            {state?.dry_run ? "DRY-RUN: ON (Simülasyon)" : "DRY-RUN: OFF (Fiziksel)"}
          </button>

          {/* Master Kill-Switch */}
          <button
            onClick={toggleKillSwitch}
            className={`px-3 py-1 rounded text-xs font-bold uppercase tracking-wider transition border ${
              state?.kill_switch
                ? "bg-rose-600 text-white border-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.5)]"
                : "bg-zinc-900 hover:bg-rose-500/20 text-rose-400 border-rose-500/30"
            }`}
          >
            {state?.kill_switch ? "KILL-SWITCH AKTİF" : "KILL-SWITCH"}
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto">
        {page === "overview" && <Overview state={state} />}
        {page === "strategy" && <Strategy />}
        {page === "devices" && <Devices />}
        {page === "orders" && <Orders state={state} />}
        {page === "logs" && <Logs state={state} />}
        {page === "settings" && <Settings onStateChange={setState} />}
      </main>
    </div>
  );
}
