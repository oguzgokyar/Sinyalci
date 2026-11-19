import { useEffect, useState, useMemo } from "react";
import { api, connectWS } from "../api";
import type {
  StrategyConfig,
  StrategySignal,
  SignalStats,
  PaperPosition,
  PaperStats,
  PrescreenCandidate,
} from "../types";

export default function Strategy() {
  const [activeTab, setActiveTab] = useState<"trades" | "strategy">("trades");

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

  // Autopilot & Prescreener state
  const [autopilotEnabled, setAutopilotEnabled] = useState(true);
  const [prescreenList, setPrescreenList] = useState<PrescreenCandidate[]>([]);
  const [showRadarDetails, setShowRadarDetails] = useState(false);

  // Slide-Over Drawer state (Analiz Özeti & Geçmişi)
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [tickerSignals, setTickerSignals] = useState<StrategySignal[]>([]);
  const [tickerReports, setTickerReports] = useState<Array<{ report_id: string; ticker: string; date: string }>>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null);
  const [reportContent, setReportContent] = useState<string | null>(null);

  // Strategy Config Form state
  const [balance, setBalance] = useState("46250");
  const [riskPct, setRiskPct] = useState("1.0");
  const [minRR, setMinRR] = useState("2.0");
  const [suffix, setSuffix] = useState(".pro");
  const [autoExec, setAutoExec] = useState(false);
  const [paperTrading, setPaperTrading] = useState(true);
  const [favorites, setFavorites] = useState<string[]>(["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]);
  const [symbolSearch, setSymbolSearch] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");

  const showToast = (msg: string, type: "ok" | "err" = "ok") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 4000);
  };

  const loadPrescreen = async () => {
    try {
      const res = await api.getPrescreen();
      setPrescreenList(res.candidates || []);
    } catch {
      // ignore
    }
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
      setAutopilotEnabled(cfg.autopilot_enabled !== false);
      setTimeframe(cfg.timeframe || "H1");
      setFavorites(cfg.favorites || ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]);

      loadPrescreen();
    } catch (e: any) {
      showToast("Veri yüklenemedi: " + (e?.message || e), "err");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();

    const intervalId = setInterval(() => {
      loadPrescreen();
    }, 30000);

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
        loadPrescreen();
      } else if (event === "paper_positions_updated") {
        const payload = data as any;
        if (payload?.positions) setOpenPositions(payload.positions);
        if (payload?.stats) setPaperStats(payload.stats);
      } else if (event === "autopilot_triggered") {
        const cand = data as any;
        showToast(`🤖 Otopilot Fırsat Yakaladı: ${cand.ticker} (${cand.setup} Puan: ${cand.score}/100)!`);
      } else if (event === "scan_started") {
        const t = (data as any)?.ticker;
        if (t) setScanningTicker(t);
      } else if (event === "scan_failed") {
        setScanningTicker(null);
        showToast(`Tarama hatası: ${(data as any)?.error}`, "err");
      }
    });

    return () => {
      clearInterval(intervalId);
      unsub();
    };
  }, []);

  // Slide-Over Drawer Data Loader
  const openTickerDrawer = async (ticker: string) => {
    setSelectedTicker(ticker);
    setDrawerLoading(true);
    setSelectedReportId(null);
    setReportContent(null);
    try {
      const res = await api.getTickerReports(ticker);
      setTickerSignals(res.signals || []);
      setTickerReports(res.reports || []);
      if (res.reports && res.reports.length > 0) {
        // Load latest report content automatically
        loadReportContent(ticker, res.reports[0].report_id);
      }
    } catch (e: any) {
      showToast("Analiz geçmişi yüklenemedi: " + (e?.message || e), "err");
    } finally {
      setDrawerLoading(false);
    }
  };

  const loadReportContent = async (ticker: string, reportId: string) => {
    setSelectedReportId(reportId);
    try {
      const rep = await api.getReportDetail(ticker, reportId);
      setReportContent(rep.content || "");
    } catch (e: any) {
      showToast("Rapor içeriği alınamadı: " + (e?.message || e), "err");
    }
  };

  const handleToggleAutopilot = async () => {
    const next = !autopilotEnabled;
    setAutopilotEnabled(next);
    try {
      const updated = await api.updateStrategyConfig({ autopilot_enabled: next });
      setConfig(updated);
      showToast(next ? "🤖 Otopilot AKTİF: Piyasa ve seanslar otomatik taranıyor." : "⏸️ Otopilot DURDURULDU.");
    } catch (e: any) {
      showToast("Otopilot güncellenemedi: " + (e?.message || e), "err");
    }
  };

  const handleRunAutopilotNow = async () => {
    try {
      await api.triggerAutopilotNow();
      showToast("🚀 Otopilot anlık döngüsü tetiklendi! En yüksek puanlı fırsat analiz ediliyor...");
      loadPrescreen();
    } catch (e: any) {
      showToast("Tetikleme hatası: " + (e?.message || e), "err");
    }
  };

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
        autopilot_enabled: autopilotEnabled,
        favorites: favorites,
        watchlist: favorites,
      });
      setConfig(updated);
      showToast("Strateji parametreleri başarıyla kaydedildi.");
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
      loadPrescreen();
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
      loadPrescreen();
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

  const selectedCand = prescreenList.find((c) => c.ticker === selectedTicker);
  const latestSignal = tickerSignals.length > 0 ? tickerSignals[0] : null;

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

      {/* TOP BAR: RESPONSIVE TABS SWITCHER & MASTER STATUS */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 sm:gap-4 bg-zinc-900/90 p-3 sm:p-4 rounded-xl border border-zinc-800">
        <div className="flex items-center gap-3 w-full lg:w-auto">
          <div className="grid grid-cols-2 sm:flex items-center bg-zinc-950 p-1 rounded-xl border border-zinc-800 w-full sm:w-auto">
            <button
              onClick={() => setActiveTab("trades")}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs font-bold font-mono transition flex items-center justify-center gap-1.5 ${
                activeTab === "trades"
                  ? "bg-cyan-600 text-slate-950 shadow-md"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <span>⚡ İşlemler</span>
              {openPositions.length > 0 && (
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-500/50">
                  {openPositions.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("strategy")}
              className={`px-3 sm:px-4 py-2 rounded-lg text-xs font-bold font-mono transition flex items-center justify-center gap-1.5 ${
                activeTab === "strategy"
                  ? "bg-cyan-600 text-slate-950 shadow-md"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              <span>📐 Strateji & Kasa</span>
            </button>
          </div>
        </div>

        {/* Master Action Tools */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Autopilot Switch */}
          <button
            onClick={handleToggleAutopilot}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold font-mono transition flex items-center gap-1.5 border ${
              autopilotEnabled
                ? "bg-emerald-950/60 border-emerald-500 text-emerald-300 shadow-lg shadow-emerald-950/30"
                : "bg-zinc-950 border-zinc-700 text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span className={`w-2 h-2 rounded-full ${autopilotEnabled ? "bg-emerald-400 animate-pulse" : "bg-zinc-500"}`} />
            {autopilotEnabled ? "Otopilot Devrede" : "Otopilotu Başlat"}
          </button>

          {/* Quick Autopilot Run */}
          <button
            onClick={handleRunAutopilotNow}
            className="px-3 py-1.5 rounded-lg text-xs font-medium bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 border border-cyan-700/60 transition flex items-center gap-1.5"
            title="Sıradaki seansı beklemeden hemen radar taraması yap ve fırsatı işleme al"
          >
            <span>⚡ Şimdi Tara & İşle</span>
          </button>

          {/* Timeframe Selector */}
          <div className="bg-zinc-950 p-1 rounded-lg border border-zinc-800 flex items-center gap-1">
            {["H1", "H4", "D1"].map((tf) => (
              <button
                key={tf}
                onClick={() => handleTimeframeChange(tf)}
                className={`px-2.5 py-1 rounded text-xs font-mono font-bold transition ${
                  timeframe === tf
                    ? "bg-cyan-600 text-slate-950 shadow"
                    : "text-zinc-400 hover:text-zinc-200"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: İŞLEMLER MASASI (TRADING DESK)                                    */}
      {/* ========================================================================= */}
      {activeTab === "trades" && (
        <div className="space-y-6">
          {/* CORE KPI METRICS: Responsive Grid */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2.5 sm:gap-3.5">
            <div className="bg-zinc-900/80 border border-zinc-800/80 p-3 sm:p-4 rounded-xl">
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
              <div className="text-[10px] text-zinc-500 mt-1">{signals.filter((s) => s.status === "pending").length} Sinyal Beklemede</div>
            </div>
          </div>

          {/* TECHNICAL RADAR & PRESCREENER (Kartlara tıklandığında sol drawer açılır) */}
          <div className="bg-zinc-900/70 border border-zinc-800/80 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm">📡</span>
                <span className="text-xs font-bold text-zinc-200 uppercase tracking-wider font-mono">
                  Otopilot Teknik Radarı (Hafif Ön-Filtre • 10 EMA & 14 RSI)
                </span>
                <span className="text-[10px] text-cyan-400/80 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-800/40">
                  Karta tıklayarak analiz özetini açın
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowRadarDetails(!showRadarDetails)}
                  className="text-xs text-cyan-400 hover:text-cyan-300 font-mono"
                >
                  {showRadarDetails ? "▲ Tabloyu Gizle" : "▼ Radar Tablosunu Göster"}
                </button>
                <button
                  onClick={loadPrescreen}
                  className="px-2 py-0.5 rounded text-[11px] bg-zinc-800 hover:bg-zinc-700 text-zinc-300 font-mono transition"
                >
                  Yenile
                </button>
              </div>
            </div>

            {/* Radar Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5">
              {prescreenList.map((cand) => {
                const hasSignal = cand.score >= 60;
                const isSelected = selectedTicker === cand.ticker;
                return (
                  <div
                    key={cand.ticker}
                    onClick={() => openTickerDrawer(cand.ticker)}
                    className={`p-3 rounded-xl border cursor-pointer transition relative group ${
                      isSelected
                        ? "ring-2 ring-cyan-500 bg-zinc-800 border-cyan-400"
                        : hasSignal
                        ? cand.setup === "BUY"
                          ? "bg-emerald-950/30 border-emerald-500/50 hover:bg-emerald-950/50"
                          : "bg-rose-950/30 border-rose-500/50 hover:bg-rose-950/50"
                        : "bg-zinc-950/60 border-zinc-800 hover:border-zinc-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-xs text-zinc-200">{cand.ticker}</span>
                      <span
                        className={`text-[10px] font-bold font-mono px-1.5 py-0.5 rounded ${
                          cand.setup === "BUY"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : cand.setup === "SELL"
                            ? "bg-rose-500/20 text-rose-400"
                            : "bg-zinc-800 text-zinc-400"
                        }`}
                      >
                        {cand.setup} {cand.score}/100
                      </span>
                    </div>
                    <div className="text-xs text-zinc-300 mt-1 font-mono font-bold">${cand.price}</div>
                    <div className="text-[10px] text-zinc-500 mt-0.5 truncate">{cand.reason}</div>
                    <div className="mt-2 pt-1 border-t border-zinc-800/60 flex items-center justify-between text-[10px] text-cyan-400 opacity-80 group-hover:opacity-100">
                      <span>Analiz İncele</span>
                      <span>→</span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Detailed Radar Table */}
            {showRadarDetails && (
              <div className="overflow-x-auto pt-2 border-t border-zinc-800/80">
                <table className="w-full text-left text-xs font-mono">
                  <thead className="text-[10px] uppercase text-zinc-400 bg-zinc-950/60">
                    <tr>
                      <th className="py-2 px-3">Parite</th>
                      <th className="py-2 px-3">Güncel Fiyat</th>
                      <th className="py-2 px-3">14 RSI</th>
                      <th className="py-2 px-3">10 EMA</th>
                      <th className="py-2 px-3">50 SMA</th>
                      <th className="py-2 px-3">Teknik Durum</th>
                      <th className="py-2 px-3">Radar Puanı</th>
                      <th className="py-2 px-3 text-right">İşlem</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60">
                    {prescreenList.map((c) => (
                      <tr key={c.ticker} className="hover:bg-zinc-800/30">
                        <td className="py-2 px-3 font-bold text-zinc-100">{c.ticker}</td>
                        <td className="py-2 px-3 text-zinc-200">${c.price}</td>
                        <td className="py-2 px-3 text-cyan-400">{c.rsi}</td>
                        <td className="py-2 px-3 text-zinc-300">{c.ema10}</td>
                        <td className="py-2 px-3 text-zinc-400">{c.sma50}</td>
                        <td className="py-2 px-3 text-zinc-300 text-[11px]">{c.reason}</td>
                        <td className="py-2 px-3">
                          <span
                            className={`font-bold ${
                              c.score >= 60 ? (c.setup === "BUY" ? "text-emerald-400" : "text-rose-400") : "text-zinc-500"
                            }`}
                          >
                            {c.score}/100
                          </span>
                        </td>
                        <td className="py-2 px-3 text-right">
                          <button
                            onClick={() => openTickerDrawer(c.ticker)}
                            className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-cyan-600 hover:text-slate-950 text-zinc-300 text-[11px] transition"
                          >
                            Özeti Aç
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* MAIN SECTION 1: LIVE OPEN TRADES WITH REALTIME FLOATING PNL & WORKING CLOSE */}
          <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
                  Açık Sanal İşlemler ({openPositions.length})
                </h2>
              </div>
              <span className="text-xs text-zinc-500 font-mono">
                Anlık Piyasa Fiyatı & Otomatik TP/SL İzleme
              </span>
            </div>

            {openPositions.length === 0 ? (
              <div className="text-center py-8 text-zinc-500 text-xs border border-dashed border-zinc-800/80 rounded-lg">
                Şu an açık bir sanal pozisyon bulunmuyor. Otopilot radarındaki fırsatları bekleyebilir veya radardan analiz başlatabilirsiniz.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {openPositions.map((pos) => (
                  <div
                    key={pos.id}
                    className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 flex flex-col justify-between space-y-3 shadow-lg"
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
                        <span
                          className={`text-xs font-bold block ${
                            pos.pnl >= 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {pos.pnl >= 0 ? "+" : ""}${pos.pnl ? pos.pnl.toFixed(2) : "0.00"}
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-zinc-900/60 p-2.5 rounded-lg text-[11px] font-mono text-center">
                      <div>
                        <span className="text-zinc-500 block text-[10px]">Giriş</span>
                        <span className="text-zinc-200 font-bold">${pos.entry_price}</span>
                      </div>
                      <div>
                        <span className="text-cyan-400 block text-[10px]">Güncel</span>
                        <span className="text-zinc-100 font-bold">${pos.current_price || pos.entry_price}</span>
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
                        className="px-3 py-1.5 rounded-lg text-xs font-bold bg-rose-950/60 hover:bg-rose-900 text-rose-300 border border-rose-700/60 transition"
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
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: STRATEJİ & KASA YÖNETİMİ (STRATEGY & PLAYBOOK)                      */}
      {/* ========================================================================= */}
      {activeTab === "strategy" && (
        <div className="space-y-6">
          {/* SECTION 1: CANLI PARAMETRE YÖNETİM FORMU */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 space-y-6">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
              <div>
                <h2 className="text-base font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-2">
                  <span>⚙️</span> Canlı Parametreler & Kasa Ayarları
                </h2>
                <p className="text-xs text-zinc-400 mt-0.5">
                  Buradan yaptığınız değişiklikler otopilot ve canlı sinyal motoruna anında uygulanır.
                </p>
              </div>

              <button
                onClick={handleSaveConfig}
                className="px-5 py-2 rounded-lg text-xs font-bold bg-cyan-600 hover:bg-cyan-500 text-slate-950 transition shadow-lg shadow-cyan-950/40"
              >
                💾 Değişiklikleri Kaydet
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">Hesap Başlangıç Bakiyesi ($)</label>
                <input
                  type="number"
                  step="any"
                  value={balance}
                  onChange={(e) => setBalance(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                />
                <span className="text-[10px] text-zinc-500 block mt-1">Sabit referans: $46.250,00</span>
              </div>

              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">İşlem Başı Risk Oranı (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={riskPct}
                  onChange={(e) => setRiskPct(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                />
                <span className="text-[10px] text-rose-400/80 block mt-1">İşlem başı: ${((parseFloat(balance || "46250") * parseFloat(riskPct || "1.0")) / 100).toFixed(2)}</span>
              </div>

              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">Risk : Reward (R:R)</label>
                <input
                  type="number"
                  step="0.1"
                  value={minRR}
                  onChange={(e) => setMinRR(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                />
                <span className="text-[10px] text-emerald-400/80 block mt-1">Hedef kâr: ${((parseFloat(balance || "46250") * parseFloat(riskPct || "1.0") * parseFloat(minRR || "2.0")) / 100).toFixed(2)}</span>
              </div>

              <div>
                <label className="block text-xs font-bold text-zinc-300 mb-1.5">Broker Sembol Suffix</label>
                <input
                  type="text"
                  value={suffix}
                  onChange={(e) => setSuffix(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 font-mono focus:border-cyan-500"
                />
                <span className="text-[10px] text-zinc-500 block mt-1">ACG Markets: .pro / .raw</span>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4 border-t border-zinc-800/80">
              <label className="flex items-center gap-3 p-3 rounded-lg bg-zinc-950 border border-zinc-800 cursor-pointer hover:border-zinc-700">
                <input
                  type="checkbox"
                  checked={autopilotEnabled}
                  onChange={(e) => setAutopilotEnabled(e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-900 border-zinc-700 text-cyan-500"
                />
                <div>
                  <div className="text-xs font-bold text-zinc-200">Otobot (Otopilot) Modu</div>
                  <div className="text-[10px] text-zinc-500">Seans saatlerinde otomatik analiz ve icra</div>
                </div>
              </label>

              <label className="flex items-center gap-3 p-3 rounded-lg bg-zinc-950 border border-zinc-800 cursor-pointer hover:border-zinc-700">
                <input
                  type="checkbox"
                  checked={paperTrading}
                  onChange={(e) => setPaperTrading(e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-900 border-zinc-700 text-cyan-500"
                />
                <div>
                  <div className="text-xs font-bold text-zinc-200">Sanal Alım-Satım (Paper)</div>
                  <div className="text-[10px] text-zinc-500">Bakiyeyi simüle ederek kâr/zararı canlı izle</div>
                </div>
              </label>

              <label className="flex items-center gap-3 p-3 rounded-lg bg-zinc-950 border border-zinc-800 cursor-pointer hover:border-zinc-700">
                <input
                  type="checkbox"
                  checked={autoExec}
                  onChange={(e) => setAutoExec(e.target.checked)}
                  className="w-4 h-4 rounded bg-zinc-900 border-zinc-700 text-cyan-500"
                />
                <div>
                  <div className="text-xs font-bold text-zinc-200">Gerçek MT5 Telefonuna İlet</div>
                  <div className="text-[10px] text-zinc-500">Galaxy A11 üzerindeki MT5 uygulamasında aç</div>
                </div>
              </label>
            </div>
          </div>

          {/* SECTION 2: GÜVENLİK VE DEVRE KESİCİ KURALLARI */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2 text-rose-400 font-mono font-bold text-xs uppercase">
                <span>🛡️</span> Açık Pozisyon Sınırı (Max 3)
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Aynı anda en fazla <strong>3 aktif işlem</strong> açılabilir. Toplam kasa riski hiçbir zaman %3'ü ($1.387,50) aşamaz. 3 pozisyon doluyken otopilot yeni arama yapmaz.
              </p>
            </div>

            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2 text-amber-400 font-mono font-bold text-xs uppercase">
                <span>⚡</span> Günlük Devre Kesici ($925)
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Günde art arda <strong>2 kayıp yaşanırsa (-$925,00)</strong>, bot günün geri kalanındaki tüm otopilot işlemlerini durdurur. Kasa asla intikam trade'ine (revenge trading) kurban edilmez.
              </p>
            </div>

            <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-5 space-y-2">
              <div className="flex items-center gap-2 text-cyan-400 font-mono font-bold text-xs uppercase">
                <span>⏳</span> 15 Dakika Cooldown
              </div>
              <p className="text-xs text-zinc-300 leading-relaxed">
                Bir enstrüman TradingAgents derin analizine girdikten sonra en az <strong>15 dakika soğuma süresi</strong> uygulanır. Gereksiz yapay zeka sorguları ve mükerrer sinyaller önlenir.
              </p>
            </div>
          </div>

          {/* SECTION 3: GÜNLÜK BAKİYE BÜYÜTME MATEMATİĞİ (COMPOUNDING PLAYBOOK) */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-2">
                  <span>📈</span> Günlük Kasa Büyütme Modeli & Matematiği
                </h3>
                <p className="text-xs text-zinc-400">1:2 R:R asimetrisi sayesinde %50 başarı oranında bile net kâr garantileyen kurumsal matematik.</p>
              </div>
              <span className="text-xs font-mono font-bold text-cyan-400 bg-cyan-950/60 px-3 py-1 rounded-lg border border-cyan-800/40">
                Hedef: Aylık +%20 Kasa Büyümesi
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-1">
              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase block font-mono">1 Kayıp İşlem Maliyeti</span>
                <span className="text-lg font-bold text-rose-400 font-mono block mt-1">-$462,50 (%1,0)</span>
                <span className="text-[10px] text-zinc-400 mt-1 block">Katı Stop-Loss ile sınırlandırılmış risk.</span>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase block font-mono">1 Kazanç İşlem Getirisi</span>
                <span className="text-lg font-bold text-emerald-400 font-mono block mt-1">+$925,00 (%2,0)</span>
                <span className="text-[10px] text-zinc-400 mt-1 block">1:2 Risk-Reward hedefiyle alınan kâr.</span>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase block font-mono">Günlük 2 İşlem (1W - 1L)</span>
                <span className="text-lg font-bold text-cyan-400 font-mono block mt-1">+$462,50 NET / Gün</span>
                <span className="text-[10px] text-zinc-400 mt-1 block">%50 Win-rate ile günlük kâr büyümesi.</span>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
                <span className="text-[10px] text-zinc-500 uppercase block font-mono">Aylık Kasa Projeksiyonu</span>
                <span className="text-lg font-bold text-zinc-100 font-mono block mt-1">~$55.500 (+%20)</span>
                <span className="text-[10px] text-zinc-400 mt-1 block">20 işlem gününde beklenen kasa büyümesi.</span>
              </div>
            </div>
          </div>

          {/* SECTION 4: GÜNLÜK İDEAL TRADE ARALIKLARI (ALTIN SAATLER) */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 space-y-4">
            <div className="border-b border-zinc-800 pb-3">
              <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-2">
                <span>⏰</span> Günlük İdeal Trade Aralıkları (Altın Seans Saatleri)
              </h3>
              <p className="text-xs text-zinc-400">Piyasanın yönlü ve hacimli aktığı kurumsal saat dilimleri.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-zinc-950 p-4 rounded-xl border border-cyan-500/30">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-cyan-400 uppercase font-mono">1. Seans: Londra Açılışı</span>
                  <span className="text-[10px] bg-cyan-950 text-cyan-300 px-2 py-0.5 rounded border border-cyan-800/50 font-mono font-bold">TSİ 10:00 - 12:30</span>
                </div>
                <div className="text-xs text-zinc-200 font-bold mt-2 font-mono">Odak: EURUSD.pro, GBPUSD.pro</div>
                <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">
                  Avrupa bankalarının devreye girdiği, spreadlerin en dar olduğu ve trend kırılımlarının başladığı saatler.
                </p>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-amber-500/30">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-amber-400 uppercase font-mono">2. Seans: New York Açılışı</span>
                  <span className="text-[10px] bg-amber-950 text-amber-300 px-2 py-0.5 rounded border border-amber-800/50 font-mono font-bold">TSİ 15:30 - 19:30</span>
                </div>
                <div className="text-xs text-zinc-200 font-bold mt-2 font-mono">Odak: XAUUSD.pro (Altın), NAS100.pro</div>
                <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">
                  ABD verilerinin açıklandığı, dünyadaki en yüksek işlem hacminin ve trend uzantılarının yaşandığı ana pencere.
                </p>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-xs text-rose-400 uppercase font-mono">3. Seans: Gece Yasağı</span>
                  <span className="text-[10px] bg-zinc-900 text-zinc-400 px-2 py-0.5 rounded border border-zinc-800 font-mono font-bold">TSİ 23:00 - 08:00</span>
                </div>
                <div className="text-xs text-zinc-300 font-bold mt-2 font-mono">Durum: İşlem Yapılmaz (Beklemede)</div>
                <p className="text-[11px] text-zinc-400 mt-1 leading-relaxed">
                  Asya seansında düşük likidite, açılan spread makasları ve tuzak hareketler nedeniyle otopilot dinlenmeye geçer.
                </p>
              </div>
            </div>
          </div>

          {/* SECTION 5: TEKNİK GÖSTERGELER & GÜVENİLİRLİK MATRİSİ */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 space-y-4">
            <div className="border-b border-zinc-800 pb-3">
              <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-2">
                <span>🎯</span> İndikatör Rolleri & Güvenilirlik Matrisi
              </h3>
              <p className="text-xs text-zinc-400">10 EMA & 14 RSI göstergelerinin neden H1/H4 periyotlarında kullanıldığı ve kurumsal filtreler.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                <span className="text-cyan-400 font-bold block">10 EMA (Dinamik Değer Desteği/Direnci):</span>
                <p className="text-zinc-300 text-[11px] font-sans leading-relaxed">
                  Fiyat trend halindeyken 10 EMA'ya geri çekilme yaptığında (Pullback to Value), en düşük riskle en yüksek kazancı verir. Fiyat ortalamadan çok uzaksa yeni işleme girilmez.
                </p>
              </div>

              <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800 space-y-2">
                <span className="text-emerald-400 font-bold block">14 RSI (Momentum Toparlanma Filtresi):</span>
                <p className="text-zinc-300 text-[11px] font-sans leading-relaxed">
                  Boğa trendinde RSI 30-45 aralığına indiğinde aşırı satış değil, kaliteli bir toparlanma (dip) bölgesidir. Ayı trendinde ise RSI 55-70 aralığı tepe satış fırsatıdır.
                </p>
              </div>
            </div>
          </div>

          {/* SECTION 6: ACG MARKETS ENSTRÜMAN KATALOĞU & FAVORİ SEÇİCİ */}
          <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800 pb-3">
              <div>
                <h3 className="text-sm font-bold text-zinc-100 uppercase tracking-wider flex items-center gap-2">
                  <span>⭐</span> ACG Markets Enstrüman Portföyü ({config?.acg_symbols?.length || 41} Enstrüman)
                </h3>
                <p className="text-xs text-zinc-400">Yıldızladığınız pariteler radar ve otopilot tarama listesine otomatik dahil edilir.</p>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="text"
                  placeholder="Parite veya Metal Ara..."
                  value={symbolSearch}
                  onChange={(e) => setSymbolSearch(e.target.value)}
                  className="bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-1.5 text-xs text-zinc-100 font-mono focus:border-cyan-500 w-44"
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
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2.5 max-h-80 overflow-y-auto pr-1">
              {filteredSymbols.map((item) => {
                const isFav = favorites.includes(item.ticker);
                return (
                  <div
                    key={item.ticker}
                    onClick={() => toggleFavorite(item.ticker)}
                    className={`p-3 rounded-lg border flex items-center justify-between cursor-pointer transition ${
                      isFav
                        ? "bg-amber-950/20 border-amber-500/50 text-amber-200"
                        : "bg-zinc-950/60 border-zinc-800 text-zinc-400 hover:border-zinc-700"
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="font-mono font-bold text-xs text-zinc-100 flex items-center gap-1.5">
                        <span>{item.ticker}</span>
                        <span className="text-[10px] text-zinc-500">{config?.symbol_suffix}</span>
                      </div>
                      <div className="text-[10px] truncate text-zinc-400 mt-0.5">{item.name}</div>
                    </div>
                    <span className={`text-base ml-2 ${isFav ? "text-amber-400" : "text-zinc-600"}`}>★</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SLIDE-OVER DRAWER: SOLDA SABİT ANALİZ ÖZETİ & GEÇMİŞİ                    */}
      {/* ========================================================================= */}
      {selectedTicker && (
        <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-xs flex">
          {/* Drawer Body (Left Aligned, mobile full-width / desktop 440px) */}
          <div className="bg-zinc-900 border-r border-zinc-800 w-full max-w-[90vw] sm:max-w-md h-full flex flex-col shadow-2xl animate-in slide-in-from-left duration-200">
            {/* Drawer Header */}
            <div className="p-4 border-b border-zinc-800 flex items-center justify-between bg-zinc-950/80">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center font-mono font-bold text-cyan-400 text-xs">
                  {selectedCand?.timeframe || timeframe}
                </div>
                <div>
                  <h3 className="font-bold text-zinc-100 font-mono text-sm">
                    {selectedTicker}{config?.symbol_suffix}
                  </h3>
                  <span className="text-[10px] text-zinc-400 font-mono">
                    Canlı Fiyat: ${selectedCand?.price || "—"} • {selectedCand?.setup || "NÖTR"} ({selectedCand?.score || 0}/100)
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleScan(selectedTicker)}
                  disabled={scanningTicker !== null}
                  className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-slate-950 text-xs font-bold font-mono transition flex items-center gap-1"
                >
                  <span>🚀</span>
                  <span>{scanningTicker === selectedTicker ? "Analiz Ediliyor..." : "Yeniden Analiz Et"}</span>
                </button>
                <button
                  onClick={() => setSelectedTicker(null)}
                  className="p-1 rounded text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* Drawer Content Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {drawerLoading ? (
                <div className="text-center py-16 text-zinc-500 text-xs font-mono">
                  Analiz geçmişi yükleniyor...
                </div>
              ) : (
                <>
                  {/* Güncel Analiz Özeti */}
                  <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-3">
                    <span className="text-[11px] font-bold text-zinc-300 uppercase tracking-wider block font-mono">
                      📊 Güncel Değerlendirme & Karar
                    </span>

                    {latestSignal ? (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <span
                            className={`px-2.5 py-0.5 rounded text-xs font-extrabold font-mono ${
                              latestSignal.side === "BUY"
                                ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
                                : "bg-rose-500/20 text-rose-400 border border-rose-500/40"
                            }`}
                          >
                            {latestSignal.side} SİNYALİ
                          </span>
                          <span className="text-xs font-bold text-cyan-400 font-mono">{latestSignal.calculated_lot} LOT</span>
                        </div>

                        <div className="grid grid-cols-3 gap-2 bg-zinc-900/80 p-2 rounded text-[11px] font-mono text-center">
                          <div>
                            <span className="text-zinc-500 block text-[10px]">Giriş</span>
                            <span className="text-zinc-200 font-bold">${latestSignal.entry_price}</span>
                          </div>
                          <div>
                            <span className="text-rose-400 block text-[10px]">Stop Loss</span>
                            <span className="text-rose-300 font-bold">${latestSignal.sl}</span>
                          </div>
                          <div>
                            <span className="text-emerald-400 block text-[10px]">Take Profit</span>
                            <span className="text-emerald-300 font-bold">${latestSignal.tp}</span>
                          </div>
                        </div>

                        {latestSignal.reasoning && (
                          <div className="text-xs text-zinc-300 bg-zinc-900/50 p-2.5 rounded-lg border border-zinc-800/80 leading-relaxed">
                            <span className="text-[10px] text-zinc-500 block font-mono uppercase mb-1">Ajan Gerekçesi</span>
                            {latestSignal.reasoning}
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-center py-4 text-zinc-500 text-xs font-mono">
                        Bu parite için henüz üretilmiş bir sinyal yok. Yukarıdaki butondan analiz başlatabilirsiniz.
                      </div>
                    )}
                  </div>

                  {/* Geçmiş Raporlar & Analizler Listesi */}
                  <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-3">
                    <span className="text-[11px] font-bold text-zinc-300 uppercase tracking-wider block font-mono">
                      📜 Geçmiş TradingAgents Raporları ({tickerReports.length})
                    </span>

                    {tickerReports.length === 0 ? (
                      <div className="text-center py-4 text-zinc-500 text-xs font-mono">
                        Kayıtlı geçmiş rapor bulunmuyor.
                      </div>
                    ) : (
                      <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                        {tickerReports.map((rep) => {
                          const isSel = selectedReportId === rep.report_id;
                          return (
                            <div
                              key={rep.report_id}
                              onClick={() => loadReportContent(selectedTicker, rep.report_id)}
                              className={`p-2 rounded-lg border cursor-pointer font-mono text-xs flex items-center justify-between transition ${
                                isSel
                                  ? "bg-cyan-950/40 border-cyan-500 text-cyan-200"
                                  : "bg-zinc-900/60 border-zinc-800/80 text-zinc-400 hover:border-zinc-700"
                              }`}
                            >
                              <span className="truncate">{rep.report_id}</span>
                              <span className="text-[10px] text-zinc-500 ml-2">{rep.date}</span>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Rapor Detay İçeriği Görüntüleyici */}
                  {reportContent && (
                    <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 space-y-2">
                      <span className="text-[11px] font-bold text-cyan-400 uppercase tracking-wider block font-mono">
                        📝 Seçili Rapor Detayı
                      </span>
                      <pre className="text-[11px] text-zinc-300 bg-zinc-900/80 p-3 rounded-lg overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap font-mono leading-relaxed border border-zinc-800">
                        {reportContent}
                      </pre>
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Drawer Footer */}
            <div className="p-3 border-t border-zinc-800 bg-zinc-950 text-right">
              <button
                onClick={() => setSelectedTicker(null)}
                className="px-4 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300"
              >
                Kapat
              </button>
            </div>
          </div>

          {/* Backdrop Click Closes Drawer */}
          <div className="flex-1 cursor-pointer" onClick={() => setSelectedTicker(null)} />
        </div>
      )}
    </div>
  );
}
