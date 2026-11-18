import { useEffect, useState } from "react";
import { api, connectWS } from "../api";
import type { StrategyConfig, StrategySignal, SignalStats } from "../types";

export default function Strategy() {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [signals, setSignals] = useState<StrategySignal[]>([]);
  const [stats, setStats] = useState<SignalStats>({ total: 0, executed: 0, pending: 0 });
  const [loading, setLoading] = useState(false);
  const [scanningTicker, setScanningTicker] = useState<string | null>(null);
  const [customTicker, setCustomTicker] = useState("");
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Form states
  const [balance, setBalance] = useState("46250");
  const [riskPct, setRiskPct] = useState("1.0");
  const [minRR, setMinRR] = useState("2.0");
  const [suffix, setSuffix] = useState(".us");
  const [autoExec, setAutoExec] = useState(false);
  const [watchlistInput, setWatchlistInput] = useState("");

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [cfg, sigData] = await Promise.all([api.getStrategyConfig(), api.getSignals()]);
      setConfig(cfg);
      setSignals(sigData.signals);
      setStats(sigData.stats);

      setBalance(String(cfg.balance));
      setRiskPct(String(cfg.risk_percent));
      setMinRR(String(cfg.min_rr));
      setSuffix(cfg.symbol_suffix);
      setAutoExec(cfg.auto_execute);
      setWatchlistInput(cfg.watchlist.join(", "));
    } catch (e: any) {
      showToast("Veri yüklenemedi: " + (e?.message || e), "err");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const unsub = connectWS((event, data) => {
      if (event === "signal_created" || event === "signal_executed" || event === "signal_updated") {
        api.getSignals().then((res) => {
          setSignals(res.signals);
          setStats(res.stats);
        }).catch(() => {});
      } else if (event === "scan_started") {
        const t = (data as any)?.ticker;
        if (t) setScanningTicker(t);
      } else if (event === "scan_failed") {
        setScanningTicker(null);
        showToast(`Tarama hatası: ${(data as any)?.error}`, "err");
      }
    });
    return unsub;
  }, []);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const wl = watchlistInput
        .split(",")
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean);

      const updated = await api.updateStrategyConfig({
        balance: parseFloat(balance),
        risk_percent: parseFloat(riskPct),
        min_rr: parseFloat(minRR),
        symbol_suffix: suffix,
        auto_execute: autoExec,
        watchlist: wl,
      });
      setConfig(updated);
      showToast("Strateji ayarları başarıyla kaydedildi.");
    } catch (e: any) {
      showToast("Kaydetme hatası: " + (e?.message || e), "err");
    }
  };

  const handleScan = async (ticker: string) => {
    if (!ticker) return;
    setScanningTicker(ticker);
    try {
      await api.scanTicker(ticker);
      showToast(`${ticker} için TradingAgents analizi başlatıldı. Sonuç ekrana düşecektir.`);
    } catch (e: any) {
      setScanningTicker(null);
      showToast("Tarama başlatılamadı: " + (e?.message || e), "err");
    }
  };

  const handleExecute = async (id: number) => {
    try {
      await api.executeSignal(id);
      showToast(`Sinyal #${id} MetaTrader 5 emrine dönüştürüldü!`);
      const sigData = await api.getSignals();
      setSignals(sigData.signals);
      setStats(sigData.stats);
    } catch (e: any) {
      showToast("Emir iletim hatası: " + (e?.message || e), "err");
    }
  };

  const handleReject = async (id: number) => {
    try {
      await api.rejectSignal(id);
      showToast(`Sinyal #${id} pas geçildi.`);
      const sigData = await api.getSignals();
      setSignals(sigData.signals);
      setStats(sigData.stats);
    } catch (e: any) {
      showToast("Reddetme hatası: " + (e?.message || e), "err");
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 px-4 py-3 rounded-lg shadow-xl text-sm font-medium border animate-in fade-in ${
            toast.type === "ok"
              ? "bg-emerald-950/90 border-emerald-500/50 text-emerald-200"
              : "bg-rose-950/90 border-rose-500/50 text-rose-200"
          }`}
        >
          {toast.msg}
        </div>
      )}

      {/* Top Banner: Strategy Engine & Health */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-gradient-to-r from-zinc-900 via-zinc-900 to-indigo-950/40 p-5 rounded-xl border border-zinc-800">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.7)]" />
              ACD Markets Günlük Trade Stratejisi
            </h1>
            <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              1:2 R:R Pullback to Value
            </span>
          </div>
          <p className="text-xs text-zinc-400 mt-1">
            46.250$ başlangıç bakiyesi ile %1 sabit risk (462,50$) kuralı ve TradingAgents LLM motoru destekli swing işlem yönetimi.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadData}
            disabled={loading}
            className="px-3.5 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
          >
            {loading ? "Yenileniyor..." : "Yenile"}
          </button>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Hesap Bakiyesi</div>
          <div className="text-xl font-bold text-zinc-100 mt-1 font-mono">
            ${Number(config?.balance || 46250).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">ACD Markets Demo</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">İşlem Başı Risk (%1)</div>
          <div className="text-xl font-bold text-rose-400 mt-1 font-mono">
            ${Number(config?.risk_amount || 462.5).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">Maksimum Stop Kaybı</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Hedef Kâr (1:2)</div>
          <div className="text-xl font-bold text-emerald-400 mt-1 font-mono">
            ${Number(config?.target_profit || 925).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">İşlem Başı Net Kazanç</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Günlük Fren Limiti</div>
          <div className="text-xl font-bold text-amber-400 mt-1 font-mono">
            ${Number(config?.max_daily_loss || 925).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">2 Stop Sonrası Kilitleme</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Bugünkü Sinyaller</div>
          <div className="text-xl font-bold text-cyan-400 mt-1 font-mono">
            {stats.executed} / {stats.total}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">{stats.pending} Onay Bekliyor</div>
        </div>
      </div>

      {/* Main Grid: Config vs Watchlist Scanning */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 1 Col: Strategy Settings Form */}
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-2">
            ⚙️ Kasa & Risk Parametreleri
          </h2>

          <form onSubmit={handleSaveConfig} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Hesap Bakiyesi ($)</label>
              <input
                type="number"
                step="any"
                value={balance}
                onChange={(e) => setBalance(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Risk Oranı (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={riskPct}
                  onChange={(e) => setRiskPct(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Hedef R:R Oranı</label>
                <input
                  type="number"
                  step="0.1"
                  value={minRR}
                  onChange={(e) => setMinRR(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:outline-none focus:border-cyan-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">Broker Sembol Eki (Suffix)</label>
              <input
                type="text"
                placeholder=".us veya # veya boş"
                value={suffix}
                onChange={(e) => setSuffix(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:outline-none focus:border-cyan-500"
              />
              <span className="text-[10px] text-zinc-500 mt-1 block">Örn: NVDA + .us = NVDA.us</span>
            </div>

            <div>
              <label className="block text-xs font-medium text-zinc-400 mb-1">İzleme Listesi (Watchlist)</label>
              <textarea
                rows={2}
                value={watchlistInput}
                onChange={(e) => setWatchlistInput(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-100 font-mono focus:outline-none focus:border-cyan-500 resize-none"
              />
            </div>

            <div className="pt-2 border-t border-zinc-800">
              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={autoExec}
                  onChange={(e) => setAutoExec(e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-950 border-zinc-700 text-cyan-500 focus:ring-0"
                />
                <span className="text-xs text-zinc-300 font-medium">
                  Otomatik İcra (Sinyal üretilince beklemeden emri MT5'e gönder)
                </span>
              </label>
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-slate-950 tracking-wider transition uppercase shadow-lg shadow-cyan-600/20"
            >
              Ayarları Kaydet
            </button>
          </form>
        </div>

        {/* Right 2 Cols: Watchlist Quick Scan & Active Scanner */}
        <div className="lg:col-span-2 space-y-6">
          {/* Quick Scanner Bar */}
          <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5">
            <h2 className="text-sm font-bold text-zinc-200 uppercase tracking-wider mb-3 flex items-center justify-between">
              <span>🚀 Çoklu Ajan Taraması (TradingAgents)</span>
              {scanningTicker && (
                <span className="text-xs text-cyan-400 flex items-center gap-1.5 animate-pulse font-mono">
                  <span className="w-2 h-2 rounded-full bg-cyan-400" />
                  {scanningTicker} analiz ediliyor... (1-2 dk)
                </span>
              )}
            </h2>

            <div className="flex flex-wrap gap-2 mb-4">
              {(config?.watchlist || []).map((ticker) => (
                <button
                  key={ticker}
                  onClick={() => handleScan(ticker)}
                  disabled={scanningTicker !== null}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border transition flex items-center gap-1.5 ${
                    scanningTicker === ticker
                      ? "bg-cyan-500/20 border-cyan-500 text-cyan-300 animate-pulse"
                      : "bg-zinc-800/80 border-zinc-700/80 text-zinc-300 hover:bg-zinc-700 hover:border-zinc-600"
                  }`}
                >
                  <span>{ticker}</span>
                  <span className="text-[10px] text-zinc-500 font-normal">Tara</span>
                </button>
              ))}
            </div>

            <div className="flex items-center gap-2 pt-3 border-t border-zinc-800/80">
              <input
                type="text"
                placeholder="Özel Sembol (örn: PLTR, NFLX, BABA)"
                value={customTicker}
                onChange={(e) => setCustomTicker(e.target.value.toUpperCase())}
                className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-100 font-mono focus:outline-none focus:border-cyan-500"
              />
              <button
                onClick={() => {
                  handleScan(customTicker);
                  setCustomTicker("");
                }}
                disabled={!customTicker || scanningTicker !== null}
                className="px-4 py-1.5 rounded-lg text-xs font-semibold bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-600 transition disabled:opacity-50"
              >
                Analiz Et
              </button>
            </div>
          </div>

          {/* Active Signals Stream */}
          <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5">
            <h2 className="text-sm font-bold text-zinc-200 uppercase tracking-wider mb-4 flex items-center justify-between">
              <span>📊 Üretilen Strateji Sinyalleri</span>
              <span className="text-xs text-zinc-500 font-normal font-mono">Son {signals.length} kayıt</span>
            </h2>

            {signals.length === 0 ? (
              <div className="text-center py-12 text-zinc-500 text-xs">
                Henüz sinyal üretilmedi. Yukarıdan bir hisse seçerek tarama başlatabilirsiniz.
              </div>
            ) : (
              <div className="space-y-3.5">
                {signals.map((sig) => (
                  <div
                    key={sig.id}
                    className={`p-4 rounded-xl border transition ${
                      sig.status === "executed"
                        ? "bg-zinc-950/80 border-emerald-500/30"
                        : sig.status === "rejected"
                        ? "bg-zinc-950/40 border-zinc-800/60 opacity-60"
                        : "bg-zinc-950 border-zinc-700 shadow-lg"
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <span
                          className={`px-2.5 py-1 rounded text-xs font-extrabold font-mono tracking-wider ${
                            sig.side === "BUY"
                              ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                              : sig.side === "SELL"
                              ? "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                              : "bg-amber-500/20 text-amber-400 border border-amber-500/40"
                          }`}
                        >
                          {sig.side}
                        </span>

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-zinc-100 font-mono text-base">{sig.ticker}</span>
                            <span className="text-xs text-zinc-500 font-mono">({sig.broker_symbol})</span>
                          </div>
                          <div className="text-[11px] text-zinc-400 font-mono">
                            Giriş: <span className="text-zinc-200">${sig.entry_price}</span> | SL:{" "}
                            <span className="text-rose-400">${sig.sl}</span> | TP:{" "}
                            <span className="text-emerald-400">${sig.tp}</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-4">
                        <div className="text-right font-mono">
                          <div className="text-xs font-bold text-cyan-400">{sig.calculated_lot} LOT</div>
                          <div className="text-[10px] text-zinc-500">Risk: ${sig.risk_amount}</div>
                        </div>

                        {sig.status === "pending" && (
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => handleExecute(sig.id)}
                              className="px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-slate-950 transition shadow"
                            >
                              MT5'e İlet
                            </button>
                            <button
                              onClick={() => handleReject(sig.id)}
                              className="px-2.5 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-400 border border-zinc-700 transition"
                            >
                              Pas Geç
                            </button>
                          </div>
                        )}

                        {sig.status === "executed" && (
                          <span className="px-2.5 py-1 rounded-md text-[11px] font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                            Emir Açıldı #{sig.order_id}
                          </span>
                        )}

                        {sig.status === "rejected" && (
                          <span className="px-2 py-0.5 rounded text-[11px] font-mono text-zinc-500">
                            Pas Geçildi
                          </span>
                        )}
                      </div>
                    </div>

                    {sig.reasoning && (
                      <div className="mt-2.5 pt-2.5 border-t border-zinc-800/80 text-xs text-zinc-400 leading-relaxed">
                        <span className="text-zinc-500 font-semibold mr-1">TradingAgents Gerekçesi:</span>
                        {sig.reasoning}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
