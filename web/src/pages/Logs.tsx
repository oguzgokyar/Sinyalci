import { useEffect, useState } from "react";
import { api } from "../api";
import type { AuditLog, SystemState } from "../types";

export default function Logs({ state }: { state: SystemState | null }) {
  const [logs, setLogs] = useState<AuditLog[]>([]);

  useEffect(() => {
    api.getLogs().then(setLogs).catch(() => {});
  }, []);

  const webhookUrl = `${location.origin}/api/webhook/signal`;

  return (
    <div className="space-y-6">
      {/* Webhook Integration Card */}
      <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-2">
        <div className="text-xs uppercase font-semibold text-zinc-400">Harici Sinyal / TradingView Webhook</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs mono">
          <div className="p-2.5 bg-zinc-950 border border-zinc-800 rounded text-zinc-300 break-all">
            <span className="text-zinc-500 mr-2">POST</span>
            {webhookUrl}
          </div>
          <div className="p-2.5 bg-zinc-950 border border-zinc-800 rounded text-emerald-400 break-all">
            <span className="text-zinc-500 mr-2">SECRET</span>
            {state?.webhook_secret ?? "—"}
          </div>
        </div>
      </div>

      {/* Audit Logs Table */}
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase">
          Denetim Kayıtları
        </div>
        <div className="divide-y divide-zinc-800/60 max-h-[540px] overflow-y-auto">
          {logs.map((l) => (
            <div key={l.id} className="px-4 py-2.5 flex items-center gap-4 text-xs mono">
              <span className="text-zinc-500 shrink-0">{l.created_at.slice(11, 19)}</span>
              <span
                className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                  l.level === "ERROR"
                    ? "bg-rose-500/10 text-rose-400"
                    : l.level === "WARN"
                    ? "bg-amber-500/10 text-amber-400"
                    : "bg-zinc-800 text-zinc-400"
                }`}
              >
                {l.level}
              </span>
              <span className="text-zinc-200">{l.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
