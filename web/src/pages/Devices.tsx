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

  const refreshScreen = () => {
    if (selectedId === null) return;
    setScreenUrl(`/api/devices/${selectedId}/screenshot?t=${Date.now()}`);
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
      <div className="lg:col-span-7 space-y-6">
        <div className="flex items-center justify-between">
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
                <button
                  onClick={() => handleAdd(it)}
                  className="px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-zinc-950 font-semibold rounded text-[11px]"
                >
                  Sisteme Ekle
                </button>
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
          <div className="flex gap-2">
            <button
              onClick={runAoaTest}
              className="px-2.5 py-1 bg-zinc-800 hover:bg-zinc-700 text-xs text-zinc-200 rounded"
            >
              AOA Test
            </button>
            <button
              onClick={refreshScreen}
              className="px-2.5 py-1 bg-cyan-600 hover:bg-cyan-500 text-xs font-semibold text-zinc-950 rounded"
            >
              Kare Yakala
            </button>
          </div>
        </div>

        {aoaStatus && <div className="text-xs mono text-emerald-400 bg-emerald-500/10 p-2 rounded">{aoaStatus}</div>}

        {/* Live screenshot container with click listener */}
        <div className="relative aspect-[720/1560] max-h-[520px] mx-auto bg-black rounded border border-zinc-800 overflow-hidden flex items-center justify-center">
          {screenUrl ? (
            <img
              ref={imgRef}
              src={screenUrl}
              alt="Live Screen"
              onClick={handleImageClick}
              className="w-full h-full object-contain cursor-crosshair select-none"
            />
          ) : (
            <div className="text-xs text-zinc-600 text-center px-4">
              "Kare Yakala" butonuna basarak Galaxy A11'in ekranını çekin.
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
    </div>
  );
}
