import { useEffect, useState, useMemo } from "react";
import { api, connectWS } from "../api";
import type { StrategyConfig, StrategySignal, SignalStats, AcgSymbol, PaperPosition, PaperStats } from "../types";

export default function Strategy() {
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [signals, setSignals] = useState<StrategySignal[]>([]);
  const [stats, setStats] = useState<SignalStats>({ total: 0, executed: 0, pending: 0 });
  const [openPositions, setOpenPositions] = useState<PaperPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<PaperPosition[]>([]);
  const [paperStats, setPaperStats] = useState<PaperStats>({
    open_count: 0,
    total_trades: 0,
    wins: 0,
    losses: 0,
    win_rate: 0,
    realized_pnl: 0,
  });

  const [loading, setLoading] = useState(false);
  const [scanningTicker, setScanningTicker] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<string>("H1");
  const [toast, setToast] = useState<{ msg: string; type: "ok" | "err" } | null>(null);

  // Modals & Collapsibles (Minimalist UI)
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showCatalogModal, setShowCatalogModal] = useState(false);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  // Form states (Settings Modal)
  const [balance, setBalance] = useState("46250");
  const [riskPct, setRiskPct] = useState("1.0");
  const [minRR, setMinRR] = useState("2.0");
  const [suffix, setSuffix] = useState(".pro");
  const [autoExec, setAutoExec] = useState(false);
  const [paperTrading, setPaperTrading] = useState(true);
  const [favorites, setFavorites] = useState<string[]>(["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]);

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const [cfg, sigData, paperData] = await Promise.all([
        api.getStrategyConfig(),
        api.getSignals(),
        api.getPaperTrades(),
      ]);
      setConfig(cfg);
      setSignals(sigData.signals);
      setStats(sigData.stats);
      setOpenPositions(paperData.open_positions);
      setClosedPositions(paperData.closed_positions);
      setPaperStats(paperData.stats);

      setBalance(String(cfg.balance));
      setRiskPct(String(cfg.risk_percent));
      setMinRR(String(cfg.min_rr));
      setSuffix(cfg.symbol_suffix || ".pro");
      setAutoExec(cfg.auto_execute);
      setPaperTrading(cfg.paper_trading !== false);
      setTimeframe(cfg.timeframe || "H1");
      setFavorites(cfg.favorites || ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]);
    } catch (e: any) {
      showToast("Veri yüklenemedi: " + (e?.message || e), "err");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const unsub = connectWS((event, data) => {
      if (
        event === "signal_created" ||
        event === "signal_executed" ||
        event === "signal_updated" ||
        event === "paper_position_opened" ||
        event === "paper_position_closed"
      ) {
        Promise.all([api.getSignals(), api.getPaperTrades()]).then(([sigRes, paperRes]) => {
          setSignals(sigRes.signals);
          setStats(sigRes.stats);
          setOpenPositions(paperRes.open_positions);
          setClosedPositions(paperRes.closed_positions);
          setPaperStats(paperRes.stats);
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

  const handleSaveConfig = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    try {
      const updated = await api.updateStrategyConfig({
        balance: parseFloat(balance),
        risk_percent: parseFloat(riskPct),
        min_rr: parseFloat(minRR),
        symbol_suffix: suffix,
        auto_execute: autoExec,
        timeframe: timeframe,
        paper_trading: paperTrading,
        favorites: favorites,
        watchlist: favorites,
      });
      setConfig(updated);
      setShowConfigModal(false);
      showToast("Strateji parametreleri kaydedildi.");
    } catch (e: any) {
      showToast("Kaydetme hatası: " + (e?.message || e), "err");
    }
  };

  const handleTimeframeChange = async (tf: string) => {
    setTimeframe(tf);
    try {
      const updated = await api.updateStrategyConfig({ timeframe: tf });
      setConfig(updated);
      showToast(`Zaman dilimi ${tf} olarak güncellendi.`);
    } catch (e: any) {
      showToast("Zaman dilimi güncellenemedi: " + (e?.message || e), "err");
    }
  };

  const toggleFavorite = async (ticker: string) => {
    const isFav = favorites.includes(ticker);
    const next = isFav ? favorites.filter((t) => t !== ticker) : [...favorites, ticker];
    setFavorites(next);
    try {
      const updated = await api.updateStrategyConfig({
        favorites: next,
        watchlist: next,
      });
      setConfig(updated);
      showToast(`${ticker} ${isFav ? "favorilerden çıkarıldı" : "favorilere eklendi"}!`);
    } catch (e: any) {
      showToast("Favori güncellenemedi: " + (e?.message || e), "err");
    }
  };

  const handleScan = async (ticker: string) => {
    if (!ticker) return;
    setScanningTicker(ticker);
    try {
      await api.scanTicker(ticker, undefined, timeframe);
      showToast(`${ticker} (${timeframe}) TradingAgents analizi başlatıldı. Canlı izleniyor...`);
    } catch (e: any) {
      setScanningTicker(null);
      showToast("Tarama başlatılamadı: " + (e?.message || e), "err");
    }
  };

  const handleClosePaperPosition = async (id: number) => {
    try {
      await api.closePaperTrade(id);
      showToast(`Sanal pozisyon #${id} kapatıldı ve bakiye güncellendi.`);
      const paperData = await api.getPaperTrades();
      setOpenPositions(paperData.open_positions);
      setClosedPositions(paperData.closed_positions);
      setPaperStats(paperData.stats);
      api.getStrategyConfig().then(setConfig).catch(() => {});
    } catch (e: any) {
      showToast("Pozisyon kapatma hatası: " + (e?.message || e), "err");
    }
  };

  const handleExecute = async (id: number) => {
    try {
      await api.executeSignal(id);
      showToast(`Sinyal #${id} gerçek MT5 emrine dönüştürüldü!`);
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

  const categories = useMemo(() => {
    const set = new Set<string>();
    (config?.acg_symbols || []).forEach((s) => set.add(s.category));
    return ["ALL", ...Array.from(set)];
  }, [config?.acg_symbols]);

  const filteredSymbols = useMemo(() => {
    return (config?.acg_symbols || []).filter((s) => {
      const matchSearch =
        s.ticker.toLowerCase().includes(symbolSearch.toLowerCase()) ||
        s.name.toLowerCase().includes(symbolSearch.toLowerCase());
      const matchCat = selectedCategory === "ALL" || s.category === selectedCategory;
      return matchSearch && matchCat;
    });
  }, [config?.acg_symbols, symbolSearch, selectedCategory]);

  return (
    <div className="space-y-6">
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

      {/* MINIMAL HEADER: Master Status, Timeframe & Quick Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-zinc-900/90 p-4 rounded-xl border border-zinc-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center font-mono font-bold text-cyan-400">
            {timeframe}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-bold text-zinc-100">ACG Markets Strateji Masası</h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/15 border border-emerald-500/40 text-emerald-400 font-bold">
                CANLI SİMÜLASYON
              </span>
            </div>
            <p className="text-xs text-zinc-400">
              1:2 R:R Pullback to Value • %1 Sabit Risk Modeli
            </p>
          </div>
        </div>

        {/* Timeframe Selector & Actions */}
        <div className="flex items-center gap-2.5">
          {/* Timeframe Buttons */}
          <div className="bg-zinc-950 p-1 rounded-lg border border-zinc-800 flex items-center gap-1">
            {["H1", "H4", "D1"].map((tf) => (
              <button
                key={tf}
                onClick={() => handleTimeframeChange(tf)}
                className={`px-3 py-1 rounded text-xs font-mono font-bold transition ${
                  timeframe === tf
                    ? "bg-cyan-600 text-slate-950 shadow"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowCatalogModal(true)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition flex items-center gap-1.5"
          >
            <span>⭐ Pariteleri Düzenle</span>
          </button>

          <button
            onClick={() => setShowConfigModal(true)}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition flex items-center gap-1.5"
          >
            <span>⚙️ Parametreler</span>
          </button>
        </div>
      </div>

      {/* CORE KPI METRICS: Balance, PnL, Win-Rate & Risk */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Sanal Kasa Bakiyesi</div>
          <div className="text-xl font-bold text-zinc-100 mt-1 font-mono">
            ${Number(config?.balance || 46250).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">Başlangıç: $46.250,00</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Gerçekleşen Kâr/Zarar</div>
          <div className={`text-xl font-bold mt-1 font-mono ${paperStats.realized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
            {paperStats.realized_pnl >= 0 ? "+" : ""}${paperStats.realized_pnl.toFixed(2)}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">{paperStats.total_trades} Kapanan İşlem</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Başarı Oranı (Win-Rate)</div>
          <div className="text-xl font-bold text-cyan-400 mt-1 font-mono">
            %{paperStats.win_rate}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">{paperStats.wins} Kazanç / {paperStats.losses} Kayıp</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">İşlem Başı Risk (%1)</div>
          <div className="text-xl font-bold text-rose-400 mt-1 font-mono">
            ${Number(config?.risk_amount || 462.5).toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">Hedef Kâr: ${Number(config?.target_profit || 925).toFixed(0)}</div>
        </div>

        <div className="bg-zinc-900/80 border border-zinc-800/80 p-4 rounded-xl">
          <div className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider">Açık Pozisyonlar</div>
          <div className="text-xl font-bold text-amber-400 mt-1 font-mono">
            {openPositions.length} Aktif
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">{signals.filter(s => s.status === "pending").length} Sinyal Beklemede</div>
        </div>
      </div>

      {/* QUICK LAUNCH BAR: FAVORITES ONE-CLICK SCANNER */}
      <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider font-mono">
            ⚡ Favori Pariteler Hızlı Analiz ({timeframe})
          </span>
          {scanningTicker && (
            <span className="text-xs text-cyan-400 flex items-center gap-1.5 animate-pulse font-mono bg-cyan-950/40 border border-cyan-800/60 px-3 py-0.5 rounded-lg">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              {scanningTicker} ({timeframe}) analiz ediliyor...
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2.5">
          {favorites.map((ticker) => {
            const isScanning = scanningTicker === ticker;
            return (
              <button
                key={ticker}
                onClick={() => handleScan(ticker)}
                disabled={scanningTicker !== null}
                className={`px-3 py-1.5 rounded-lg border text-xs font-mono font-bold transition flex items-center gap-2 ${
                  isScanning
                    ? "bg-cyan-500/20 border-cyan-500 text-cyan-300 animate-pulse"
                    : "bg-zinc-950 border-zinc-700/80 text-zinc-200 hover:bg-zinc-800 hover:border-zinc-600"
                }`}
              >
                <span>{ticker}{config?.symbol_suffix}</span>
                <span className="text-[10px] text-cyan-400 bg-cyan-950/80 px-1.5 py-0.5 rounded border border-cyan-800/50">
                  {timeframe}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* MAIN SECTION 1: LIVE OPEN TRADES (ETKİN İŞLEMLER) */}
      <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
              Açık Sanal İşlemler ({openPositions.length})
            </h2>
          </div>
          <span className="text-xs text-zinc-500 font-mono">Bakiye üzerinden çalışan aktif işlemler</span>
        </div>

        {openPositions.length === 0 ? (
          <div className="text-center py-8 text-zinc-500 text-xs border border-dashed border-zinc-800/80 rounded-lg">
            Şu an açık bir sanal pozisyon bulunmuyor. Yukarıdan bir parite analiz ederek yeni bir işlem başlatabilirsiniz.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {openPositions.map((pos) => (
              <div
                key={pos.id}
                className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 flex flex-col justify-between space-y-3"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-extrabold font-mono ${
                        pos.side === "BUY"
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                          : "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                      }`}
                    >
                      {pos.side}
                    </span>
                    <div>
                      <span className="font-bold text-zinc-100 font-mono">{pos.symbol}</span>
                      <span className="text-[10px] text-zinc-500 ml-1.5 font-mono">[{pos.timeframe}]</span>
                    </div>
                  </div>

                  <div className="text-right font-mono">
                    <span className="text-xs font-bold text-cyan-400">{pos.lot} LOT</span>
                    <span className="text-[10px] text-zinc-500 block">Risk: ${pos.risk_amount}</span>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 bg-zinc-900/60 p-2.5 rounded-lg text-[11px] font-mono text-center">
                  <div>
                    <span className="text-zinc-500 block text-[10px]">Giriş</span>
                    <span className="text-zinc-200 font-bold">${pos.entry_price}</span>
                  </div>
                  <div>
                    <span className="text-rose-400 block text-[10px]">Stop Loss</span>
                    <span className="text-rose-300 font-bold">${pos.sl}</span>
                  </div>
                  <div>
                    <span className="text-emerald-400 block text-[10px]">Take Profit</span>
                    <span className="text-emerald-300 font-bold">${pos.tp}</span>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-[10px] text-zinc-500 font-mono">Açılış: {pos.opened_at.slice(11, 19)}</span>
                  <button
                    onClick={() => handleClosePaperPosition(pos.id)}
                    className="px-3 py-1 rounded text-xs font-bold bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition"
                  >
                    Pozisyonu Kapat
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* MAIN SECTION 2: PENDING SIGNALS & TRADE HISTORY */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Pending Strategy Signals */}
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-zinc-200 uppercase tracking-wider">
              📢 Üretilen Sinyaller ({signals.length})
            </h2>
            <span className="text-xs text-zinc-500 font-mono">Ajan Kararları</span>
          </div>

          {signals.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-xs border border-dashed border-zinc-800 rounded-lg">
              Henüz üretilmiş sinyal yok.
            </div>
          ) : (
            <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
              {signals.map((sig) => (
                <div
                  key={sig.id}
                  className={`p-3.5 rounded-xl border transition ${
                    sig.status === "paper_active" || sig.status === "executed"
                      ? "bg-zinc-950 border-emerald-500/30"
                      : sig.status === "rejected"
                      ? "bg-zinc-950/40 border-zinc-800/60 opacity-60"
                      : "bg-zinc-950 border-zinc-700 shadow"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`px-2 py-0.5 rounded text-[11px] font-extrabold font-mono ${
                          sig.side === "BUY"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : sig.side === "SELL"
                            ? "bg-rose-500/20 text-rose-400"
                            : "bg-amber-500/20 text-amber-400"
                        }`}
                      >
                        {sig.side}
                      </span>
                      <span className="font-bold text-zinc-100 font-mono text-sm">{sig.broker_symbol}</span>
                      <span className="text-[10px] text-zinc-500 font-mono">[{sig.timeframe || "H1"}]</span>
                    </div>

                    <div className="text-right font-mono text-xs">
                      <span className="text-cyan-400 font-bold">{sig.calculated_lot} LOT</span>
                    </div>
                  </div>

                  <div className="text-[11px] font-mono text-zinc-400 mt-2 flex items-center justify-between">
                    <span>Giriş: ${sig.entry_price}</span>
                    <span className="text-rose-400">SL: ${sig.sl}</span>
                    <span className="text-emerald-400">TP: ${sig.tp}</span>
                  </div>

                  {sig.reasoning && (
                    <p className="text-[11px] text-zinc-400 mt-2 pt-2 border-t border-zinc-900 line-clamp-2">
                      {sig.reasoning}
                    </p>
                  )}

                  {sig.status === "pending" && (
                    <div className="mt-3 flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleExecute(sig.id)}
                        className="px-2.5 py-1 rounded text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-slate-950"
                      >
                        MT5'e İlet
                      </button>
                      <button
                        onClick={() => handleReject(sig.id)}
                        className="px-2.5 py-1 rounded text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-400"
                      >
                        Pas Geç
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Closed Trades History (Geçmiş İşlemler & Verim) */}
        <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-zinc-200 uppercase tracking-wider">
              📜 Kapanan İşlem Geçmişi ({closedPositions.length})
            </h2>
            <span className="text-xs text-zinc-500 font-mono">Net Kâr Takibi</span>
          </div>

          {closedPositions.length === 0 ? (
            <div className="text-center py-10 text-zinc-500 text-xs border border-dashed border-zinc-800 rounded-lg">
              Henüz kapanmış bir işlem geçmişi bulunmuyor.
            </div>
          ) : (
            <div className="space-y-2.5 max-h-96 overflow-y-auto pr-1">
              {closedPositions.map((cp) => (
                <div
                  key={cp.id}
                  className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 flex items-center justify-between font-mono text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        cp.side === "BUY" ? "text-emerald-400 bg-emerald-500/10" : "text-rose-400 bg-rose-500/10"
                      }`}
                    >
                      {cp.side}
                    </span>
                    <span className="text-zinc-200 font-bold">{cp.symbol}</span>
                    <span className="text-[10px] text-zinc-500">[{cp.timeframe}]</span>
                  </div>

                  <div className="flex items-center gap-4">
                    <span className="text-zinc-400">{cp.lot} Lot</span>
                    <span className={`font-bold ${cp.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {cp.pnl >= 0 ? "+" : ""}${cp.pnl.toFixed(2)}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* MODAL 1: SETTINGS / PARAMETERS MODAL */}
      {showConfigModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <h3 className="font-bold text-zinc-100 text-sm uppercase">⚙️ Strateji & Kasa Parametreleri</h3>
              <button onClick={() => setShowConfigModal(false)} className="text-zinc-500 hover:text-zinc-300">
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveConfig} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Hesap Bakiyesi ($)</label>
                <input
                  type="number"
                  step="any"
                  value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
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
                    className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-zinc-400 mb-1">Hedef R:R</label>
                  <input
                    type="number"
                    step="0.1"
                    value={minRR}
                    onChange={(e) => setMinRR(e.target.value)}
                    className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-zinc-400 mb-1">Broker Sembol Eki</label>
                <input
                  type="text"
                  value={suffix}
                  onChange={(e) => setSuffix(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                />
              </div>

              <div className="space-y-2 pt-2 border-t border-zinc-800">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={paperTrading}
                    onChange={(e) => setPaperTrading(e.target.checked)}
                    className="w-4 h-4 rounded bg-zinc-950 border-zinc-700 text-cyan-500"
                  />
                  <span className="text-xs text-zinc-200">Sanal Alım-Satım (Paper Trading) Aktif</span>
                </label>

                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={autoExec}
                    onChange={(e) => setAutoExec(e.target.checked)}
                    className="w-4 h-4 rounded bg-zinc-950 border-zinc-700 text-cyan-500"
                  />
                  <span className="text-xs text-zinc-200">Gerçek MT5'e Otomatik İlet</span>
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowConfigModal(false)}
                  className="px-4 py-2 rounded-lg text-xs font-medium bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                >
                  İptal
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-slate-950"
                >
                  Kaydet
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* MODAL 2: ACG MARKETS SYMBOLS CATALOG & FAVORITES PICKER */}
      {showCatalogModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-3xl w-full space-y-4 shadow-2xl max-h-[85vh] flex flex-col">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="font-bold text-zinc-100 text-sm uppercase">⭐ ACG Markets Parite & Metal Kataloğu</h3>
                <p className="text-xs text-zinc-400">Yıldızlayarak favori hızlı analiz listesine ekleyin veya çıkarın.</p>
              </div>
              <button onClick={() => setShowCatalogModal(false)} className="text-zinc-500 hover:text-zinc-300">
                ✕
              </button>
            </div>

            <div className="flex items-center gap-3">
              <input
                type="text"
                placeholder="Parite veya Metal Ara..."
                value={symbolSearch}
                onChange={(e) => setSymbolSearch(e.target.value)}
                className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-100 font-mono focus:border-cyan-500 flex-1"
              />
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
                className="bg-zinc-950 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs text-zinc-300 focus:border-cyan-500"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>{c === "ALL" ? "Tüm Kategoriler" : c}</option>
                ))}
              </select>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 overflow-y-auto flex-1 pr-1">
              {filteredSymbols.map((item) => {
                const isFav = favorites.includes(item.ticker);
                return (
                  <div
                    key={item.ticker}
                    onClick={() => toggleFavorite(item.ticker)}
                    className={`p-2.5 rounded-lg border flex items-center justify-between cursor-pointer transition ${
                      isFav
                        ? "bg-amber-950/20 border-amber-500/40 text-amber-200"
                        : "bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="font-mono font-bold text-xs text-zinc-100">{item.ticker}</div>
                      <div className="text-[10px] truncate">{item.name}</div>
                    </div>
                    <span className={`text-base ml-2 ${isFav ? "text-amber-400" : "text-zinc-600"}`}>★</span>
                  </div>
                );
              })}
            </div>

            <div className="flex justify-end pt-2 border-t border-zinc-800">
              <button
                onClick={() => setShowCatalogModal(false)}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-slate-950"
              >
                Tamam
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
