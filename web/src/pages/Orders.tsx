import { useEffect, useState } from "react";
import { api } from "../api";
import type { Account, Device, Order, SystemState } from "../types";

export default function Orders({ state }: { state: SystemState | null }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);

  // Order planner form state
  const [selectedAccounts, setSelectedAccounts] = useState<number[]>([]);
  const [symbol, setSymbol] = useState("AUDCAD.pro");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [lot, setLot] = useState("0.01");
  const [sl, setSl] = useState("");
  const [tp, setTp] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [msg, setMsg] = useState("");

  // Quick Add Account state
  const [showAddAcc, setShowAddAcc] = useState(false);
  const [accDevId, setAccDevId] = useState<number>(1);
  const [accLabel, setAccLabel] = useState("ACG Demo");
  const [accLogin, setAccLogin] = useState("2765609");
  const [accServer, setAccServer] = useState("ACGMarkets-Main");
  const [accBal, setAccBal] = useState("46250");
  const [accMaxLot, setAccMaxLot] = useState("0.50");

  // Editing order state
  const [editingOrder, setEditingOrder] = useState<Order | null>(null);
  const [editSymbol, setEditSymbol] = useState("");
  const [editSide, setEditSide] = useState<"BUY" | "SELL">("BUY");
  const [editLot, setEditLot] = useState("0.01");
  const [editSl, setEditSl] = useState("");
  const [editTp, setEditTp] = useState("");
  const [editScheduled, setEditScheduled] = useState("");

  const startEdit = (o: Order) => {
    setEditingOrder(o);
    setEditSymbol(o.symbol);
    setEditSide(o.side as "BUY" | "SELL");
    setEditLot(String(o.lot));
    setEditSl(o.sl !== null ? String(o.sl) : "");
    setEditTp(o.tp !== null ? String(o.tp) : "");
    setEditScheduled(o.scheduled_at ? o.scheduled_at.slice(0, 16) : "");
  };

  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingOrder) return;
    try {
      await api.updateOrder(editingOrder.id, {
        symbol: editSymbol.trim(),
        side: editSide,
        lot: parseFloat(editLot),
        sl: editSl ? parseFloat(editSl) : null,
        tp: editTp ? parseFloat(editTp) : null,
        scheduled_at: editScheduled ? new Date(editScheduled).toISOString() : null,
      });
      setEditingOrder(null);
      load();
    } catch (err: unknown) {
      setMsg(`Hata: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const load = () => {
    api.getAccounts().then((a) => {
      setAccounts(a);
      if (a.length > 0 && selectedAccounts.length === 0) {
        setSelectedAccounts([a[0].id]);
      }
    });
    api.getDevices().then((d) => {
      setDevices(d);
      if (d.length > 0) setAccDevId(d[0].id);
    });
    api.getOrders().then(setOrders);
  };

  useEffect(() => {
    load();
  }, [state?.today_orders, state?.pending_orders]);

  const toggleAccountSelect = (id: number) => {
    setSelectedAccounts((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleCreateOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg("");
    if (selectedAccounts.length === 0) {
      setMsg("En az bir hesap seçin.");
      return;
    }
    try {
      await api.createOrder({
        account_ids: selectedAccounts,
        symbol: symbol.trim(),
        side,
        lot: parseFloat(lot),
        sl: sl ? parseFloat(sl) : null,
        tp: tp ? parseFloat(tp) : null,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
      });
      setMsg("Emir kuyruğa eklendi.");
      load();
    } catch (err: unknown) {
      setMsg(`Hata: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.addAccount({
      device_id: accDevId,
      label: accLabel,
      login: accLogin,
      server: accServer,
      account_type: "Demo",
      balance: parseFloat(accBal) || 0,
      max_lot: parseFloat(accMaxLot) || 0.1,
      daily_max_orders: 5,
    });
    setShowAddAcc(false);
    load();
  };

  return (
    <div className="space-y-6">
      {/* Order Planner Form */}
      <form
        onSubmit={handleCreateOrder}
        className="bg-zinc-900/60 border border-zinc-800 rounded-lg p-4 space-y-4"
      >
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-zinc-400 uppercase">Yeni Emir Planla</div>
          <button
            type="button"
            onClick={() => setShowAddAcc(!showAddAcc)}
            className="text-xs text-cyan-400 hover:underline"
          >
            + Yeni MT5 Hesabı Ekle
          </button>
        </div>

        {/* Multi-account checkboxes */}
        <div className="flex flex-wrap gap-2">
          {accounts.map((a) => (
            <button
              type="button"
              key={a.id}
              onClick={() => toggleAccountSelect(a.id)}
              className={`px-3 py-1.5 rounded text-xs font-medium border transition ${
                selectedAccounts.includes(a.id)
                  ? "bg-emerald-500/10 border-emerald-500/50 text-emerald-400"
                  : "bg-zinc-800/40 border-zinc-800 text-zinc-400 hover:border-zinc-700"
              }`}
            >
              {a.label} ({a.login})
            </button>
          ))}
          {accounts.length === 0 && (
            <span className="text-xs text-zinc-500">Önce sağ üstten MT5 hesabı tanımlayın.</span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">Sembol</label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs mono text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">Yön</label>
            <div className="grid grid-cols-2 gap-1">
              <button
                type="button"
                onClick={() => setSide("BUY")}
                className={`py-1.5 text-xs font-bold rounded ${
                  side === "BUY" ? "bg-cyan-600 text-zinc-950" : "bg-zinc-800 text-zinc-400"
                }`}
              >
                BUY
              </button>
              <button
                type="button"
                onClick={() => setSide("SELL")}
                className={`py-1.5 text-xs font-bold rounded ${
                  side === "SELL" ? "bg-rose-600 text-zinc-950" : "bg-zinc-800 text-zinc-400"
                }`}
              >
                SELL
              </button>
            </div>
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">Lot</label>
            <input
              type="number"
              step="0.01"
              value={lot}
              onChange={(e) => setLot(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs mono text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">SL (Ops.)</label>
            <input
              type="number"
              step="0.00001"
              placeholder="—"
              value={sl}
              onChange={(e) => setSl(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs mono text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">TP (Ops.)</label>
            <input
              type="number"
              step="0.00001"
              placeholder="—"
              value={tp}
              onChange={(e) => setTp(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2.5 py-1.5 text-xs mono text-zinc-100"
            />
          </div>
          <div>
            <label className="block text-[10px] uppercase text-zinc-500 mb-1">Planlı Zaman (Boş=Hemen)</label>
            <input
              type="datetime-local"
              value={scheduledAt}
              onChange={(e) => setScheduledAt(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-[11px] mono text-zinc-100"
            />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2">
          <div className="text-xs mono">
            {msg ? (
              <span className="text-amber-400">{msg}</span>
            ) : (
              <span className="text-emerald-400">Canlı fiziksel icra aktif — emirler bağlı Android telefonda resmi MT5 ile açılır.</span>
            )}
          </div>
          <button
            type="submit"
            className="px-5 py-2 bg-emerald-500 hover:bg-emerald-400 text-zinc-950 font-bold text-xs rounded transition"
          >
            {scheduledAt ? "Zamanla" : "Emri Gönder"}
          </button>
        </div>
      </form>

      {/* Quick Add Account Modal/Box */}
      {showAddAcc && (
        <form
          onSubmit={handleAddAccount}
          className="p-4 bg-zinc-900 border border-cyan-500/30 rounded-lg grid grid-cols-2 md:grid-cols-6 gap-3"
        >
          <select
            value={accDevId}
            onChange={(e) => setAccDevId(Number(e.target.value))}
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs"
          >
            {devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
          <input
            value={accLabel}
            onChange={(e) => setAccLabel(e.target.value)}
            placeholder="Etiket"
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs"
          />
          <input
            value={accLogin}
            onChange={(e) => setAccLogin(e.target.value)}
            placeholder="Login No"
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
          />
          <input
            value={accServer}
            onChange={(e) => setAccServer(e.target.value)}
            placeholder="Sunucu"
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
          />
          <input
            value={accBal}
            onChange={(e) => setAccBal(e.target.value)}
            placeholder="Bakiye"
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
          />
          <button
            type="submit"
            className="bg-cyan-600 hover:bg-cyan-500 text-zinc-950 font-bold text-xs rounded py-1.5"
          >
            Kaydet
          </button>
        </form>
      )}

      {/* Edit Order Panel */}
      {editingOrder && (
        <form
          onSubmit={handleSaveEdit}
          className="p-4 bg-zinc-900 border border-amber-500/40 rounded-lg space-y-3"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-amber-400 uppercase mono">
              Emir #{editingOrder.id} Düzenle
            </span>
            <button
              type="button"
              onClick={() => setEditingOrder(null)}
              className="text-xs text-zinc-400 hover:text-zinc-200"
            >
              Kapat
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <input
              value={editSymbol}
              onChange={(e) => setEditSymbol(e.target.value)}
              placeholder="Sembol"
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
            />
            <select
              value={editSide}
              onChange={(e) => setEditSide(e.target.value as "BUY" | "SELL")}
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
            >
              <option value="BUY">BUY</option>
              <option value="SELL">SELL</option>
            </select>
            <input
              type="number"
              step="0.01"
              value={editLot}
              onChange={(e) => setEditLot(e.target.value)}
              placeholder="Lot"
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
            />
            <input
              type="number"
              step="0.00001"
              value={editSl}
              onChange={(e) => setEditSl(e.target.value)}
              placeholder="SL"
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
            />
            <input
              type="number"
              step="0.00001"
              value={editTp}
              onChange={(e) => setEditTp(e.target.value)}
              placeholder="TP"
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-xs mono"
            />
            <input
              type="datetime-local"
              value={editScheduled}
              onChange={(e) => setEditScheduled(e.target.value)}
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1.5 text-[11px] mono"
            />
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="submit"
              className="px-4 py-1.5 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-bold text-xs rounded"
            >
              Kaydet
            </button>
          </div>
        </form>
      )}

      {/* Orders Table */}
      <div className="bg-zinc-900/40 border border-zinc-800 rounded-lg overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-900/80 text-zinc-500 text-xs border-b border-zinc-800">
            <tr>
              <th className="px-4 py-2.5 font-medium">ID</th>
              <th className="px-4 py-2.5 font-medium">Hesap</th>
              <th className="px-4 py-2.5 font-medium">Sembol</th>
              <th className="px-4 py-2.5 font-medium">Yön / Lot</th>
              <th className="px-4 py-2.5 font-medium">OCR Okunan</th>
              <th className="px-4 py-2.5 font-medium">Gecikme</th>
              <th className="px-4 py-2.5 font-medium">Durum / Hata</th>
              <th className="px-4 py-2.5 font-medium text-right">Aksiyon</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-800/60">
            {orders.map((o) => (
              <tr key={o.id} className="hover:bg-zinc-800/20">
                <td className="px-4 py-2.5 text-xs mono text-zinc-500">#{o.id}</td>
                <td className="px-4 py-2.5 text-xs text-zinc-300">{o.account_label || `#${o.account_id}`}</td>
                <td className="px-4 py-2.5 text-xs mono font-semibold text-zinc-100">{o.symbol}</td>
                <td className="px-4 py-2.5 text-xs mono">
                  <span className={o.side === "BUY" ? "text-cyan-400 font-bold" : "text-rose-400 font-bold"}>
                    {o.side}
                  </span>{" "}
                  {o.lot.toFixed(2)}
                </td>
                <td className="px-4 py-2.5 text-xs mono text-zinc-400">{o.ocr_lot ?? "—"}</td>
                <td className="px-4 py-2.5 text-xs mono text-zinc-400">
                  {o.latency_ms ? `${o.latency_ms} ms` : "—"}
                </td>
                <td className="px-4 py-2.5 text-xs">
                  <span
                    className={`px-1.5 py-0.5 rounded uppercase text-[10px] font-semibold ${
                      o.status === "filled"
                        ? "bg-emerald-500/10 text-emerald-400"
                        : o.status === "failed"
                        ? "bg-rose-500/10 text-rose-400"
                        : o.status === "cancelled"
                        ? "bg-zinc-800 text-zinc-500"
                        : "bg-amber-500/10 text-amber-400"
                    }`}
                  >
                    {o.status}
                  </span>
                  {o.error && <span className="ml-2 text-[11px] text-rose-400">{o.error}</span>}
                </td>
                <td className="px-4 py-2.5 text-right space-x-2 whitespace-nowrap">
                  {o.status !== "filled" && o.status !== "executing" && (
                    <button
                      onClick={() => startEdit(o)}
                      className="text-xs text-amber-400 hover:underline"
                    >
                      Düzenle
                    </button>
                  )}
                  {(o.status === "failed" || o.status === "cancelled" || o.status === "scheduled") && (
                    <button
                      onClick={() => api.retryOrder(o.id).then(load)}
                      className="text-xs text-cyan-400 hover:underline"
                    >
                      Çalıştır
                    </button>
                  )}
                  {(o.status === "queued" || o.status === "scheduled") && (
                    <button
                      onClick={() => api.cancelOrder(o.id).then(load)}
                      className="text-xs text-rose-400 hover:underline"
                    >
                      İptal
                    </button>
                  )}
                  <button
                    onClick={() => api.deleteOrder(o.id).then(load)}
                    className="text-xs text-zinc-500 hover:text-rose-400"
                  >
                    Sil
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
