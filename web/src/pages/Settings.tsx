import { useEffect, useState } from "react";
import { api } from "../api";
import type { EnvironmentInfo, GitHubCheckResult, GitHubInfo, GitHubPullResult, SystemState } from "../types";

export default function Settings({ onStateChange }: { onStateChange?: (s: SystemState) => void }) {
  const [envInfo, setEnvInfo] = useState<EnvironmentInfo | null>(null);
  const [ghInfo, setGhInfo] = useState<GitHubInfo | null>(null);

  // Form states
  const [modeOverride, setModeOverride] = useState<"auto" | "local" | "vps">("auto");
  const [agentToken, setAgentToken] = useState("");
  const [vpsUrl, setVpsUrl] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("master");
  const [ghToken, setGhToken] = useState("");
  const [marketDataSource, setMarketDataSource] = useState<"biquote" | "yahoo">("biquote");
  const [dataPollInterval, setDataPollInterval] = useState("10");

  // Action states
  const [saveMsg, setSaveMsg] = useState("");
  const [checking, setChecking] = useState(false);
  const [pulling, setPulling] = useState(false);
  const [checkRes, setCheckRes] = useState<GitHubCheckResult | null>(null);
  const [pullRes, setPullRes] = useState<GitHubPullResult | null>(null);
  const [errMsg, setErrMsg] = useState("");
  const [copied, setCopied] = useState(false);

  const loadAll = async () => {
    try {
      const [e, g, cfg] = await Promise.all([api.getEnvironment(), api.getGitHubStatus(), api.getStrategyConfig()]);
      setEnvInfo(e);
      setGhInfo(g);
      setModeOverride((e.env_mode_override as "auto" | "local" | "vps") || "auto");
      setAgentToken(e.agent_token || "");
      setVpsUrl(e.vps_public_url || "");
      setRepoUrl(g.repo_url || "");
      setBranch(g.branch || "master");
      const effectiveSource = (e as any).market_data_source || (cfg as any).market_data_source;
      if (effectiveSource) {
        setMarketDataSource(effectiveSource);
      }
      const effectiveInterval = (e as any).data_poll_interval || (cfg as any).data_poll_interval;
      if (effectiveInterval) {
        setDataPollInterval(String(effectiveInterval));
      }
    } catch (err: unknown) {
      setErrMsg(err instanceof Error ? err.message : String(err));
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveMsg("");
    setErrMsg("");
    try {
      const payload: Record<string, string> = {
        env_mode_override: modeOverride,
        agent_token: agentToken.trim(),
        vps_public_url: vpsUrl.trim(),
        github_repo_url: repoUrl.trim(),
        github_branch: branch.trim() || "master",
        market_data_source: marketDataSource,
        data_poll_interval: dataPollInterval,
      };
      if (ghToken.trim()) {
        payload.github_token = ghToken.trim();
      }
      const res = await api.updateSettings(payload);
      if (onStateChange && res.state) onStateChange(res.state);
      setSaveMsg("Ayarlar kaydedildi ve ortam yeniden değerlendirildi.");
      setGhToken("");
      loadAll();
    } catch (err: unknown) {
      setErrMsg(err instanceof Error ? err.message : String(err));
    }
  };

  const handleCheckUpdates = async () => {
    setChecking(true);
    setErrMsg("");
    setCheckRes(null);
    setPullRes(null);
    try {
      if (repoUrl.trim()) {
        await api.updateSettings({
          github_repo_url: repoUrl.trim(),
          github_branch: branch.trim() || "master",
          ...(ghToken.trim() ? { github_token: ghToken.trim() } : {}),
        });
      }
      const res = await api.checkGitHub();
      setCheckRes(res);
    } catch (err: unknown) {
      setErrMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setChecking(false);
    }
  };

  const handlePullUpdates = async () => {
    setPulling(true);
    setErrMsg("");
    setPullRes(null);
    try {
      const res = await api.pullGitHub();
      setPullRes(res);
      loadAll();
    } catch (err: unknown) {
      setErrMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setPulling(false);
    }
  };

  const activeMode = envInfo?.env.mode ?? "local";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold tracking-tight">Ayarlar, Ortam & GitHub Güncelleme</h1>
          <p className="text-xs text-zinc-400">
            Uygulama çalıştığı ortamı (Lokal PC / VPS Bulut) otomatik algılar ve gerekli bağlantı köprülerini doğrular.
          </p>
        </div>
        <span
          className={`px-3 py-1 rounded-full text-xs font-bold mono border ${
            activeMode === "vps"
              ? "bg-sky-500/15 text-sky-400 border-sky-500/40"
              : "bg-emerald-500/15 text-emerald-400 border-emerald-500/40"
          }`}
        >
          {activeMode === "vps" ? "AKTİF MOD: VPS (BULUT)" : "AKTİF MOD: LOKAL (PC)"}
        </span>
      </div>

      {errMsg && (
        <div className="p-3 rounded border border-rose-500/40 bg-rose-500/10 text-rose-300 text-xs">{errMsg}</div>
      )}
      {saveMsg && (
        <div className="p-3 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 text-xs">
          {saveMsg}
        </div>
      )}

      {/* 1. Ortam Teşhisi & Köprü Kontrol Listesi */}
      <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-100">1. Ortam Tespiti & Köprü Sağlık Kontrolü</h2>
          {envInfo && (
            <span className="text-xs text-zinc-400 mono">
              {envInfo.env.os} · Python {envInfo.env.python_version} ·{" "}
              {envInfo.env.is_docker ? "Docker Konteyner" : envInfo.env.hostname}
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {(envInfo?.checklist ?? []).map((item) => (
            <div
              key={item.key}
              className={`p-3 rounded border text-xs ${
                item.ok
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-rose-500/40 bg-rose-500/10"
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold text-zinc-200">{item.title}</span>
                <span className={`font-bold mono ${item.ok ? "text-emerald-400" : "text-rose-400"}`}>
                  {item.ok ? "HAZIR" : "EKSİK"}
                </span>
              </div>
              <p className="text-zinc-400">{item.message}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 2. Köprü & Ortam Yapılandırması + 4.5G Telefon Ajanları */}
      <form onSubmit={handleSaveSettings} className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
          <h2 className="text-sm font-semibold text-zinc-100">2. Bağlantı Köprüsü Yapılandırması</h2>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-zinc-400 mb-1">Çalışma Ortamı Modu</label>
              <select
                value={modeOverride}
                onChange={(e) => setModeOverride(e.target.value as "auto" | "local" | "vps")}
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100"
              >
                <option value="auto">Otomatik Algıla (Önerilen)</option>
                <option value="local">Lokal PC (USB / ADB Köprüsü)</option>
                <option value="vps">VPS Bulut (4.5G WebSocket Ajan Köprüsü)</option>
              </select>
            </div>

            <div>
              <label className="block text-zinc-400 mb-1">VPS Genel WebSocket Adresi (Örn: wss://bot.alanadiniz.com)</label>
              <input
                type="text"
                value={vpsUrl}
                onChange={(e) => setVpsUrl(e.target.value)}
                placeholder="wss://vps-adresiniz.com"
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100 mono"
              />
            </div>

            <div>
              <label className="block text-zinc-400 mb-1">4.5G Telefon Ajanı Güvenlik Anahtarı (Agent Token)</label>
              <input
                type="text"
                value={agentToken}
                onChange={(e) => setAgentToken(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100 mono"
              />
            </div>

            {/* Veri Kaynağı ve Güncelleme Sıklığı Seçimi */}
            <div className="p-3 rounded bg-zinc-950 border border-zinc-800 space-y-3">
              <div className="font-semibold text-zinc-200 flex items-center justify-between">
                <span>📡 Piyasa Veri Kaynağı & Canlı Besleme</span>
                <span className="text-[10px] text-cyan-400 font-mono">Biquote / Yahoo</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-zinc-400 mb-1">Veri Sağlayıcı</label>
                  <select
                    value={marketDataSource}
                    onChange={(e) => setMarketDataSource(e.target.value as "biquote" | "yahoo")}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                  >
                    <option value="biquote">Biquote (Canlı MT5 Feed - Önerilen)</option>
                    <option value="yahoo">Yahoo Finance (Klasik Spot)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-zinc-400 mb-1">Veri Çekme Sıklığı</label>
                  <select
                    value={dataPollInterval}
                    onChange={(e) => setDataPollInterval(e.target.value)}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded px-2.5 py-1.5 text-zinc-100 font-mono"
                  >
                    <option value="1">1 Saniye (Ultra Canlı)</option>
                    <option value="3">3 Saniye (Hızlı)</option>
                    <option value="5">5 Saniye (Dengeli)</option>
                    <option value="10">10 Saniye (Standart)</option>
                    <option value="15">15 Saniye (Geniş)</option>
                    <option value="30">30 Saniye (Tasarruf)</option>
                  </select>
                </div>
              </div>
              <p className="text-[10px] text-zinc-500">
                Biquote doğrudan MetaTrader 5 sunucularından anlık gerçek tick ve spread kotasyonlarını aktarır.
              </p>
            </div>
          </div>

          <button
            type="submit"
            className="w-full py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition"
          >
            Ayarları Kaydet
          </button>
        </section>

        {/* 3. GitHub Hızlı Güncelleme Bölümü */}
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-zinc-100">3. GitHub Hızlı Güncelleme</h2>
            {ghInfo?.local_git.short_sha && (
              <span className="text-xs mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
                Yerel: {ghInfo.local_git.short_sha} ({ghInfo.local_git.branch})
              </span>
            )}
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-zinc-400 mb-1">GitHub Depo Linki</label>
              <input
                type="text"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/kullanici/treader"
                className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100 mono"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-zinc-400 mb-1">Dal (Branch)</label>
                <input
                  type="text"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  placeholder="master"
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100 mono"
                />
              </div>
              <div>
                <label className="block text-zinc-400 mb-1">
                  GitHub Token {ghInfo?.has_token ? "(Kayıtlı)" : "(Private depo için)"}
                </label>
                <input
                  type="password"
                  value={ghToken}
                  onChange={(e) => setGhToken(e.target.value)}
                  placeholder="ghp_..."
                  className="w-full bg-zinc-950 border border-zinc-700 rounded px-3 py-2 text-zinc-100 mono"
                />
              </div>
            </div>

            {ghInfo?.local_git.commit_message && (
              <div className="p-3 rounded bg-zinc-950 border border-zinc-800 space-y-1">
                <div className="text-zinc-400">Mevcut Kurulu Sürüm</div>
                <div className="text-zinc-200 font-medium">{ghInfo.local_git.commit_message}</div>
                <div className="text-zinc-500 mono text-[11px]">{ghInfo.local_git.commit_date}</div>
              </div>
            )}

            <div className="flex gap-3 pt-1">
              <button
                type="button"
                disabled={checking}
                onClick={handleCheckUpdates}
                className="flex-1 py-2 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-semibold transition disabled:opacity-50"
              >
                {checking ? "Kontrol Ediliyor..." : "Güncellemeleri Kontrol Et"}
              </button>
              <button
                type="button"
                disabled={pulling}
                onClick={handlePullUpdates}
                className="flex-1 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-semibold transition disabled:opacity-50"
              >
                {pulling ? "Güncelleniyor..." : "Şimdi Güncelle (Git Pull)"}
              </button>
            </div>

            {checkRes && (
              <div
                className={`p-3 rounded border ${
                  !checkRes.ok
                    ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
                    : checkRes.has_update
                    ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
                    : "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                }`}
              >
                {!checkRes.ok ? (
                  <div>Hata: {checkRes.error}</div>
                ) : checkRes.has_update ? (
                  <div className="space-y-1">
                    <div className="font-bold">Yeni güncelleme bulundu! ({checkRes.remote_short_sha})</div>
                    <div>{checkRes.remote_message}</div>
                    <div className="text-[11px] opacity-80">
                      {checkRes.remote_author} · {checkRes.remote_date}
                    </div>
                  </div>
                ) : (
                  <div className="font-semibold">Sisteminiz güncel ({checkRes.remote_short_sha}).</div>
                )}
              </div>
            )}

            {pullRes && (
              <div className="p-3 rounded border border-sky-500/40 bg-sky-500/10 text-sky-200 space-y-1">
                <div className="font-bold">
                  {pullRes.updated
                    ? `Güncellendi: ${pullRes.previous_sha} -> ${pullRes.current_sha}`
                    : "Yeni değişiklik çekilmedi"}
                </div>
                <pre className="text-[11px] mono whitespace-pre-wrap text-zinc-300">{pullRes.output}</pre>
                {pullRes.restart_required && (
                  <div className="text-amber-300 font-medium">
                    Yeni kodun aktif olması için sunucuyu / konteyneri yeniden başlatın.
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </form>
    </div>
  );
}
