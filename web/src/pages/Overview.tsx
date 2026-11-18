import { useEffect, useState } from "react";
import { api } from "../api";
import type { Account, Device, Order, SystemState } from "../types";

export default function Overview({ state }: { state: SystemState | null }) {
  const [devices, setDevices] = useState<Device[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);

  useEffect(() => {
    api.getDevices().then(setDevices).catch(() => {});
    api.getAccounts().then(setAccounts).catch(() => {});
    api.getOrders().then(setOrders).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-lg">
          <div className="text-xs uppercase text-zinc-500 font-medium">Toplam Bakiye</div>
          <div className="text-2xl font-bold mono text-emerald-400 mt-1">
            ${state?.total_balance.toLocaleString("en-US", { minimumFractionDigits: 2 }) ?? "0.00"}
          </div>
        </div>
        <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-lg">
          <div className="text-xs uppercase text-zinc-500 font-medium">Aktif Cihazlar</div>
          <div className="text-2xl font-bold mono text-zinc-100 mt-1">
            {state?.active_devices ?? 0} <span className="text-sm font-normal text-zinc-500">/ {state?.total_devices ?? 0}</span>
          </div>
        </div>
        <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-lg">
          <div className="text-xs uppercase text-zinc-500 font-medium">Bugünkü Emirler</div>
          <div className="text-2xl font-bold mono text-zinc-100 mt-1">{state?.today_orders ?? 0}</div>
        </div>
        <div className="p-4 bg-zinc-900/60 border border-zinc-800 rounded-lg">
          <div className="text-xs uppercase text-zinc-500 font-medium">Bekleyen / Planlı</div>
          <div className="text-2xl font-bold mono text-amber-400 mt-1">{state?.pending_orders ?? 0}</div>
        </div>
      </div>

      {/* Accounts List */}
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          Bağlı MT5 Hesapları
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900/80 text-zinc-500 text-xs border-b border-zinc-800">
            <tr>
              <th className="px-4 py-2 font-medium">Hesap</th>
              <th className="px-4 py-2 font-medium">Sunucu</th>
              <th className="px-4 py-2 font-medium">Tür</th>
              <th className="px-4 py-2 font-medium">Bakiye</th>
              <th className="px-4 py-2 font-medium">Limitler</th>
              <th className="px-4 py-2 font-medium">Bugün</th>
              <th className="px-4 py-2 font-medium text-right">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60 font-normal">
            {accounts.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-zinc-600 text-xs">
                  Henüz kayıtlı MT5 hesabı yok. Hesaplar sekmesinden ekleyin.
                </td>
              </tr>
            ) : (
              accounts.map((a) => (
                <tr key={a.id} className="hover:bg-zinc-800/20">
                  <td className="px-4 py-3 font-medium text-zinc-200">
                    {a.label} <span className="text-xs text-zinc-500 mono">({a.login})</span>
                  </td>
                  <td className="px-4 py-3 text-zinc-400 text-xs mono">{a.server}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                        a.account_type === "Real"
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                          : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      }`}
                    >
                      {a.account_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 mono font-semibold text-zinc-100">
                    ${a.balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </td>
                  <td className="px-4 py-3 text-xs text-zinc-400 mono">
                    Max {a.max_lot} Lot • Günde {a.daily_max_orders}
                  </td>
                  <td className="px-4 py-3 text-xs mono text-zinc-400">{a.today_orders}</td>
                  <td className="px-4 py-3 text-right">
                    <span
                      className={`inline-block w-2 h-2 rounded-full ${
                        a.enabled ? "bg-emerald-500 ring-4 ring-emerald-500/20" : "bg-zinc-600"
                      }`}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Recent Orders */}
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-800 text-xs font-semibold text-zinc-400 uppercase tracking-wider">
          Son İcra Akışı
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900/80 text-zinc-500 text-xs border-b border-zinc-800">
            <tr>
              <th className="px-4 py-2 font-medium">ID</th>
              <th className="px-4 py-2 font-medium">Hesap</th>
              <th className="px-4 py-2 font-medium">İşlem</th>
              <th className="px-4 py-2 font-medium">Lot</th>
              <th className="px-4 py-2 font-medium">Gecikme</th>
              <th className="px-4 py-2 font-medium">Zaman</th>
              <th className="px-4 py-2 font-medium text-right">Durum</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {orders.slice(0, 8).map((o) => (
              <tr key={o.id} className="hover:bg-zinc-800/20">
                <td className="px-4 py-2.5 text-xs mono text-zinc-500">#{o.id}</td>
                <td className="px-4 py-2.5 text-zinc-300 text-xs">{o.account_label || `Acc #${o.account_id}`}</td>
                <td className="px-4 py-2.5 font-semibold text-xs mono">
                  <span className={o.side === "BUY" ? "text-cyan-400" : "text-rose-400"}>{o.side}</span>{" "}
                  <span className="text-zinc-200">{o.symbol}</span>
                </td>
                <td className="px-4 py-2.5 text-xs mono text-zinc-300">{o.lot.toFixed(2)}</td>
                <td className="px-4 py-2.5 text-xs mono text-zinc-400">
                  {o.latency_ms ? `${o.latency_ms} ms` : "—"}
                </td>
                <td className="px-4 py-2.5 text-xs mono text-zinc-500">{o.created_at.slice(11, 19)}</td>
                <td className="px-4 py-2.5 text-right">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded uppercase font-semibold ${
                      o.status === "filled"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : o.status === "failed"
                        ? "bg-rose-500/10 text-rose-400"
                        : o.status === "cancelled"
                        ? "bg-zinc-700/20 text-zinc-500"
                        : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {o.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
