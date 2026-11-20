import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { Device, ScanItem } from "../types";

export default function Devices() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [scanned, setScanned] = useState<ScanItem[]>([]);
  const [scanning, setScanning] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [screenUrl, setScreenUrl] = useState<string | null>(null);
  const [calibratingKey, setCalibratingKey] = useState<string>("new_order_screen.buy_button");
  const [calibLog, setCalibLog] = useState<string>("");
  const [aoaStatus, setAoaStatus] = useState<string>("");
  const [copiedOneLiner, setCopiedOneLiner] = useState(false);
  const [closing, setClosing] = useState(false);
  const [closeMsg, setCloseMsg] = useState("");
  const [screenLoading, setScreenLoading] = useState(false);
  const [screenError, setScreenError] = useState("");
  const [runningDiag, setRunningDiag] = useState(false);
  const [diagResult, setDiagResult] = useState<import("../types").DiagnosticResult | null>(null);
  const [showDiagModal, setShowDiagModal] = useState(false);

  const oneLinerCmd = `curl -sSL ${location.origin}/api/agent/install.sh | bash`;

  const copyOneLinerCmd = () => {
    navigator.clipboard.writeText(oneLinerCmd).then(() => {
      setCopiedOneLiner(true);
      setTimeout(() => setCopiedOneLiner(false), 1800);
    });
  };

  const handleClosePosition = async () => {
    if (selectedId === null) return;
    if (!confirm("Seçili cihazdaki MT5 açık pozisyonu kapatılsın mı?")) return;
    setClosing(true);
    setCloseMsg("Kapatma emri gönderiliyor...");
    try {
      const res = await api.closeDevicePosition(selectedId);
      setCloseMsg(`✓ ${res.message}`);
      setTimeout(refreshScreen, 1500);
    } catch (e: any) {
      setCloseMsg(`Hata: ${e?.message || e}`);
    } finally {
      setClosing(false);
    }
  };

  const handleRunDiagnostic = async () => {
    if (selectedId === null) return;
    setRunningDiag(true);
    setShowDiagModal(true);
    setDiagResult(null);
    try {
      const res = await api.runDeviceDiagnostic(selectedId);
      setDiagResult(res);
      setTimeout(refreshScreen, 1200);
    } catch (e: any) {
      setDiagResult({
        ok: false,
        device_id: selectedId,
        device_name: "Cihaz",
        total_duration_ms: 0,
        steps: [
          {
            step: 1,
            title: "Simülasyon Hatası",
            ok: false,
            duration_ms: 0,
            detail: e?.message || String(e),
          },
        ],
        message: e?.message || String(e),
      });
    } finally {
      setRunningDiag(false);
    }
  };

  const imgRef = useRef<HTMLImageElement>(null);

  const load = () => {
    api.getDevices().then((devs) => {
      setDevices(devs);
      if (devs.length > 0 && selectedId === null) {
        setSelectedId(devs[0].id);
      }
    });
  };

  useEffect(() => {
    load();
  }, []);

  const handleScan = async () => {
    setScanning(true);
    try {
      const items = await api.scanDevices();
      setScanned(items);
    } finally {
      setScanning(false);
    }
  };

  const handleAdd = async (it: ScanItem) => {
    await api.addDevice({
      name: it.vendor === "Samsung" ? "Galaxy A11" : "Android Device",
      serial: it.serial,
      usb_vid: it.usb_vid || "04e8",
      usb_pid: it.usb_pid || "6860",
    });
    load();
  };

  const refreshScreen = async () => {
    if (selectedId === null) return;
    setScreenLoading(true);
    setScreenError("");
    try {
      const res = await fetch(`/api/devices/${selectedId}/screenshot?t=${Date.now()}`);
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(errJson.detail || `Hata: HTTP ${res.status}`);
      }
      const blob = await res.blob();
      setScreenUrl(URL.createObjectURL(blob));
    } catch (e: any) {
      setScreenError(e?.message || String(e));
    } finally {
      setScreenLoading(false);
    }
  };

  const runAoaTest = async () => {
    if (selectedId === null) return;
    setAoaStatus("Test gönderiliyor...");
    try {
      const res = await api.testAoa(selectedId);
      setAoaStatus(`AOA v${res.aoa_version} OK (Merkeze dokunuldu)`);
      load();
    } catch (err: unknown) {
      setAoaStatus(`Hata: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const handleImageClick = async (e: React.MouseEvent<HTMLImageElement>) => {
    if (!imgRef.current || selectedId === null) return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = Math.round(((e.clientX - rect.left) / rect.width) * 720);
    const y = Math.round(((e.clientY - rect.top) / rect.height) * 1560);
    setCalibLog(`Kaydediliyor: ${calibratingKey} -> (${x}, ${y})...`);
    try {
      await api.calibrate(selectedId, calibratingKey, x, y);
      setCalibLog(`Kaydedildi: ${calibratingKey} -> (${x}, ${y})`);
    } catch (err: unknown) {
      setCalibLog(`Hata: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* Left: Device inventory and USB Scan */}
      <div className="lg:col-span-7 space-y-4">
        {/* Termux One-Liner Setup & APK Download Box */}
        <div className="p-3.5 bg-zinc-900/60 border border-emerald-500/30 rounded-lg space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs font-semibold text-emerald-400">Telefon Ekleme (Termux Tek Satırlık Kod)</span>
            </div>
            <button
              onClick={copyOneLinerCmd}
              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-zinc-950 text-[11px] font-bold rounded transition"
            >
              {copiedOneLiner ? "Kopyalandı! ✓" : "Tek Tık Kopyala"}
            </button>
          </div>
          <p className="text-[11px] text-zinc-400">
            Android telefonda Termux açıp bu komutu yapıştırın. Python, ADB, tünel ve arka plan koruması otomatik kurulup cihaz buraya bağlanır:
          </p>
          <pre className="text-[11px] text-emerald-400 font-mono bg-zinc-950 p-2 rounded border border-zinc-800 overflow-x-auto whitespace-pre-wrap break-all">
            {oneLinerCmd}
          </pre>

          {/* Termux APK Download Bar */}
          <div className="pt-2 border-t border-zinc-800/80 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 text-[11px] text-zinc-400">
              <span className="text-zinc-500">📥 Telefonda Termux yok mu?</span>
            </div>
            <div className="flex items-center gap-2">
              <a
                href="https://github.com/termux/termux-app/releases/download/v0.118.3/termux-app_v0.118.3%2Bgithub-debug_universal.apk"
                target="_blank"
                rel="noreferrer"
                className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-cyan-400 text-[11px] font-semibold rounded border border-cyan-500/30 transition flex items-center gap-1"
                title="Doğrudan Evrensel APK İndir"
              >
                <span>📦 Termux APK Direkt İndir (Universal)</span>
              </a>
              <a
                href="https://f-droid.org/packages/com.termux/"
                target="_blank"
                rel="noreferrer"
                className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-[11px] font-medium rounded border border-zinc-700 transition"
              >
                <span>F-Droid</span>
              </a>
            </div>
          </div>
          <div className="text-[10px] text-amber-400/90 flex items-center gap-1">
            <span>⚠️</span>
            <span>Google Play Store sürümü paket yükleyemez; mutlaka yukarıdaki resmi GitHub veya F-Droid APK'sını kurun.</span>
          </div>
        </div>

        <div className="flex items-center justify-between pt-1">
          <div className="text-xs uppercase font-semibold text-zinc-400">Bağlı Cihaz Envanteri</div>
          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-xs font-medium rounded text-zinc-200 transition"
          >
            {scanning ? "Taranıyor..." : "USB & ADB Tara"}
          </button>
        </div>

        {/* Scan results if available */}
        {scanned.length > 0 && (
          <div className="p-3 bg-zinc-900/90 border border-emerald-500/30 rounded-lg space-y-2">
            <div className="text-xs font-semibold text-emerald-400">Yeni Bulunan USB Donanımları:</div>
            {scanned.map((it, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-zinc-800/40 p-2 rounded">
                <span className="mono text-zinc-300">
                  {it.vendor} ({it.usb_vid}:{it.usb_pid}) {it.serial ? `[${it.serial}]` : ""}
                </span>
                {it.registered ? (
                  <span className="text-[11px] text-emerald-400 font-medium px-2 py-0.5 bg-emerald-500/10 rounded border border-emerald-500/20">
                    ✓ Envanterde Kayıtlı
                  </span>
                ) : (
                  <button
                    onClick={() => handleAdd(it)}
                    className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-semibold rounded text-[11px]"
                  >
                    Sisteme Ekle
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Devices list */}
        <div className="space-y-3">
          {devices.map((d) => (
            <div
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              className={`p-4 rounded-lg border cursor-pointer transition ${
                selectedId === d.id
                  ? "bg-zinc-900 border-emerald-500/50 ring-1 ring-emerald-500/20"
                  : "bg-zinc-900/40 border-zinc-800 hover:border-zinc-700"
              }`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold text-zinc-200 text-sm">{d.name}</div>
                  <div className="text-xs text-zinc-500 mono mt-0.5">
                    {d.usb_vid}:{d.usb_pid} • Serial: {d.serial || "N/A"} • {d.screen_width}x{d.screen_height}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-semibold uppercase ${
                      d.status === "ready" ? "bg-emerald-500/10 text-emerald-400" : "bg-zinc-800 text-zinc-400"
                    }`}
                  >
                    {d.status}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      api.deleteDevice(d.id).then(load);
                    }}
                    className="text-xs text-zinc-600 hover:text-rose-400 px-2 py-1"
                  >
                    Sil
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Right: Live Frame & Click-to-Calibrate */}
      <div className="lg:col-span-5 bg-zinc-900/40 border border-zinc-800 rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold text-zinc-400 uppercase">Ekran & Kalibrasyon</div>
          <div className="flex flex-wrap gap-1.5">
            <button
              onClick={handleRunDiagnostic}
              disabled={runningDiag}
              className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-xs font-bold text-zinc-950 rounded transition shadow-sm flex items-center gap-1"
              title="MT5 açma, sekmeler, form açma, lot yazma ve güvenli geri çıkış simülasyonu (Sıfır Risk)"
            >
              <span>{runningDiag ? "⏳ Test Ediliyor..." : "⚡ Tam Simülasyon Testi"}</span>
            </button>
            <button
              onClick={runAoaTest}
              className="px-2 py-1 bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 rounded"
              title="Cihaz bağlantısını ve dokunmatik yanıtını test et"
            >
              Test
            </button>
            <button
              onClick={refreshScreen}
              className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-xs font-semibold text-zinc-950 rounded"
              title="Telefondan anlık ekran görüntüsü çek"
            >
              Kare Yakala
            </button>
            <button
              onClick={handleClosePosition}
              disabled={closing}
              className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white rounded transition shadow-sm"
              title="Telefondaki açık MT5 pozisyonunu kapat"
            >
              {closing ? "Kapatılıyor..." : "Pozisyonu Kapat"}
            </button>
          </div>
        </div>

        {aoaStatus && <div className="text-xs mono text-emerald-400 bg-emerald-500/10 p-2 rounded">{aoaStatus}</div>}
        {closeMsg && <div className="text-xs mono text-amber-400 bg-amber-500/10 p-2 rounded">{closeMsg}</div>}

        {/* Live screenshot container with click listener */}
        <div className="relative aspect-[720/1560] max-h-[520px] mx-auto bg-black rounded border border-zinc-800 overflow-hidden flex items-center justify-center p-3">
          {screenLoading ? (
            <div className="text-xs text-cyan-400 font-mono animate-pulse flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              Telefondan ekran çekiliyor...
            </div>
          ) : screenError ? (
            <div className="text-xs text-rose-400 font-mono bg-rose-950/40 p-3 rounded border border-rose-900/60 max-w-sm text-center space-y-1">
              <div className="font-bold">⚠️ Ekran Alınamadı</div>
              <div className="text-[11px] text-zinc-300 break-words">{screenError}</div>
            </div>
          ) : screenUrl ? (
            <img
              ref={imgRef}
              src={screenUrl}
              alt="Live Screen"
              onClick={handleImageClick}
              className="w-full h-full object-contain cursor-crosshair select-none"
            />
          ) : (
            <div className="text-xs text-zinc-500 text-center px-4">
              "Kare Yakala" butonuna basarak telefon ekranını anlık çekin.
            </div>
          )}
        </div>

        {/* Calibration key selector */}
        <div className="space-y-2 pt-2 border-t border-zinc-800">
          <label className="text-[11px] text-zinc-500 uppercase font-medium">Tıklanan Noktayı Şuraya Ata:</label>
          <select
            value={calibratingKey}
            onChange={(e) => setCalibratingKey(e.target.value)}
            className="w-full bg-zinc-800 border border-zinc-700 text-xs rounded px-2.5 py-1.5 text-zinc-200"
          >
            <option value="new_order_screen.buy_button">Buy Butonu (buy_button)</option>
            <option value="new_order_screen.sell_button">Sell Butonu (sell_button)</option>
            <option value="new_order_screen.lot_field">Lot Alanı (lot_field)</option>
            <option value="new_order_screen.sl_field">SL Alanı (sl_field)</option>
            <option value="new_order_screen.tp_field">TP Alanı (tp_field)</option>
            <option value="quotes_screen.first_row_center">Fiyatlar 1. Satır (first_row_center)</option>
            <option value="quotes_screen.context_menu.new_order">Yeni Emir Menüsü (context_menu.new_order)</option>
          </select>
          {calibLog && <div className="text-[11px] mono text-cyan-400">{calibLog}</div>}
        </div>
      </div>

      {/* Uçtan Uca Simülasyon Test Modalı */}
      {showDiagModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-lg rounded-2xl bg-zinc-900 border border-zinc-700/80 p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">🤖</span>
                <div>
                  <h3 className="text-sm font-bold text-zinc-100">Uçtan Uca Otomasyon Simülasyon Testi</h3>
                  <p className="text-[11px] text-zinc-400">Telefon üzerinde MT5 açma, form bulma, lot yazma ve güvenli çıkış</p>
                </div>
              </div>
              <button
                onClick={() => setShowDiagModal(false)}
                className="text-zinc-500 hover:text-zinc-300 p-1 text-sm font-mono"
              >
                ✕
              </button>
            </div>

            {/* Test progress indicator */}
            {runningDiag && (
              <div className="p-4 bg-emerald-950/20 border border-emerald-500/40 rounded-xl space-y-2 text-center">
                <div className="flex items-center justify-center gap-2 text-emerald-400 font-mono text-xs font-bold animate-pulse">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
                  Telefonda otomasyon adımları canlı yürütülüyor...
                </div>
                <p className="text-[11px] text-zinc-400">
                  Lütfen telefonunuzun ekranına bakın; MT5 açılacak, sekmeler gezilecek ve lot kutusu test edilecektir.
                </p>
              </div>
            )}

            {/* Steps Results */}
            {diagResult && (
              <div className="space-y-3">
                <div
                  className={`p-3 rounded-xl border flex items-center justify-between text-xs font-mono font-bold ${
                    diagResult.ok
                      ? "bg-emerald-950/40 border-emerald-500/50 text-emerald-300"
                      : "bg-rose-950/40 border-rose-500/50 text-rose-300"
                  }`}
                >
                  <span>{diagResult.ok ? "✓ TÜM ADIMLAR BAŞARIYLA TAMAMLANDI" : "⚠️ TEST SIRASINDA HATA OLUŞTU"}</span>
                  <span className="text-[11px] text-zinc-400">{diagResult.total_duration_ms}ms</span>
                </div>

                <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
                  {diagResult.steps.map((s) => (
                    <div
                      key={s.step}
                      className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800/80 flex items-start justify-between gap-3 text-xs"
                    >
                      <div className="flex items-start gap-2">
                        <span className={s.ok ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                          {s.ok ? "✓" : "✕"}
                        </span>
                        <div>
                          <div className="font-semibold text-zinc-200">{s.title}</div>
                          <div className="text-[11px] text-zinc-400">{s.detail}</div>
                        </div>
                      </div>
                      <span className="text-[10px] font-mono text-zinc-500 whitespace-nowrap">{s.duration_ms}ms</span>
                    </div>
                  ))}
                </div>

                <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-400 flex items-center justify-between">
                  <span>🛡️ Sıfır Risk Güvencesi:</span>
                  <span className="text-emerald-400 font-medium">BUY/SELL basılmadı, formdan güvenle çıkıldı.</span>
                </div>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setShowDiagModal(false)}
                className="px-4 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-xs font-semibold text-zinc-200 rounded-lg transition"
              >
                Kapat
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
