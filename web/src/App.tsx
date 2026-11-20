import { useEffect, useState } from "react";
import { api, connectWS } from "./api";
import type { SystemState, TradingAgentsHealth } from "./types";
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
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [taHealth, setTaHealth] = useState<TradingAgentsHealth | null>(null);

  const refreshState = () => {
    api.getSystem().then(setState).catch(() => {});
  };

  const refreshTAHealth = () => {
    api.getTradingAgentsHealth().then(setTaHealth).catch(() => setTaHealth(null));
  };

  useEffect(() => {
    refreshState();
    refreshTAHealth();
    const interval = setInterval(refreshTAHealth, 25000);
    const unsub = connectWS((event, data) => {
      if (event === "system_state") {
        setState(data as SystemState);
      } else {
        refreshState();
      }
    });
    return () => {
      clearInterval(interval);
      unsub();
    };
  }, []);

  const toggleKillSwitch = async () => {
    if (!state) return;
    const next = !state.kill_switch;
    const updated = await api.setKillSwitch(next);
    setState(updated);
  };

  const navItems: Array<{ id: Page; label: string; icon: string }> = [
    { id: "overview", label: "Genel Bakış", icon: "📊" },
    { id: "strategy", label: "İşlemler", icon: "📈" },
    { id: "devices", label: "Cihazlar", icon: "📱" },
    { id: "orders", label: "Emirler", icon: "⚡" },
    { id: "logs", label: "Kayıtlar", icon: "📜" },
    { id: "settings", label: "Ayarlar", icon: "⚙️" },
  ];

  const handleSelectPage = (p: Page) => {
    setPage(p);
    setMobileMenuOpen(false);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0b0d11] text-zinc-100 selection:bg-emerald-500/30">
      {/* Top Header / Master Bar */}
      <header className="h-14 border-b border-zinc-800/80 px-4 sm:px-6 flex items-center justify-between bg-zinc-950/80 backdrop-blur sticky top-0 z-40">
        <div className="flex items-center gap-4 sm:gap-6">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
            <span className="font-bold tracking-wider text-sm font-mono">SINYALCI</span>
            <span
              className={`hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-bold font-mono border ${
                state?.env_mode === "vps"
                  ? "bg-sky-500/15 border-sky-500/40 text-sky-400"
                  : "bg-emerald-500/15 border-emerald-500/40 text-emerald-400"
              }`}
            >
              {state?.env_mode === "vps" ? "VPS" : "LOKAL"}
            </span>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden lg:flex items-center gap-1 text-xs">
            {navItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handleSelectPage(item.id)}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 ${
                  page === item.id
                    ? "bg-zinc-800 text-zinc-100 shadow-sm"
                    : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        {/* Desktop Master Switches */}
        <div className="hidden lg:flex items-center gap-3">
          {/* TradingAgents Status Pill */}
          <div
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-mono border transition ${
              taHealth?.healthy
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-rose-500/10 border-rose-500/30 text-rose-400"
            }`}
            title={taHealth?.url || "TradingAgents AI Analiz Motoru"}
          >
            <span className={`w-2 h-2 rounded-full ${taHealth?.healthy ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]" : "bg-rose-500"}`} />
            <span>AI: {taHealth?.healthy ? `${taHealth.latency_ms}ms` : "Çevrimdışı"}</span>
          </div>

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

        {/* Mobile & Tablet Right Controls: Quick Kill-switch indicator & Hamburger Button */}
        <div className="flex lg:hidden items-center gap-2">
          {state?.kill_switch && (
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-600 text-white font-mono">
              STOP
            </span>
          )}

          <button
            onClick={() => setMobileMenuOpen(true)}
            aria-label="Menüyü Aç"
            className="p-2 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-200 hover:text-white hover:bg-zinc-800 transition flex items-center justify-center"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
        </div>
      </header>

      {/* Mobile & Tablet Slide-Over Sidebar (From Right) */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex justify-end lg:hidden animate-in fade-in duration-150">
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/70 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
          />

          {/* Slide-out Drawer */}
          <div className="relative w-72 sm:w-80 bg-zinc-950 border-l border-zinc-800 h-full flex flex-col p-5 shadow-2xl z-10 animate-in slide-in-from-right duration-200">
            {/* Drawer Header */}
            <div className="flex items-center justify-between pb-4 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
                <span className="font-bold tracking-wider text-sm font-mono">SINYALCI</span>
              </div>
              <button
                onClick={() => setMobileMenuOpen(false)}
                className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900 transition"
              >
                ✕
              </button>
            </div>

            {/* Navigation Links */}
            <div className="flex-1 overflow-y-auto py-4 space-y-1.5">
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 px-3 block mb-2">
                Gezinme Menüsü
              </span>
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleSelectPage(item.id)}
                  className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl font-medium text-sm transition text-left ${
                    page === item.id
                      ? "bg-cyan-600 text-slate-950 font-bold shadow-md shadow-cyan-950/40"
                      : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                  }`}
                >
                  <span className="text-base">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              ))}
            </div>

            {/* Drawer Footer: Master Controls */}
            <div className="pt-4 border-t border-zinc-800 space-y-3">
              <span className="text-[10px] font-mono uppercase tracking-wider text-zinc-500 block">
                Sistem Kontrolleri
              </span>

              {/* Kill-Switch Mobile Toggle */}
              <button
                onClick={toggleKillSwitch}
                className={`w-full py-2.5 px-3 rounded-xl text-xs font-bold uppercase tracking-wider border transition flex items-center justify-between ${
                  state?.kill_switch
                    ? "bg-rose-600 text-white border-rose-500 shadow-lg shadow-rose-950/50"
                    : "bg-rose-950/30 text-rose-400 border-rose-900/60 hover:bg-rose-900/40"
                }`}
              >
                <span>Acil Durdurma</span>
                <span>{state?.kill_switch ? "AKTİF" : "KILL-SWITCH"}</span>
              </button>

              <div className="flex items-center justify-between text-[11px] font-mono px-1 text-zinc-400 pt-1">
                <span>AI Analiz:</span>
                <span className={taHealth?.healthy ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                  {taHealth?.healthy ? `Aktif (${taHealth.latency_ms}ms)` : "Çevrimdışı"}
                </span>
              </div>
              <div className="text-[10px] text-zinc-500 text-center font-mono">
                Ortam: {state?.env_mode === "vps" ? "VPS (Bulut)" : "Lokal (PC)"}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <main className="flex-1 p-3 sm:p-6 max-w-7xl w-full mx-auto">
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
