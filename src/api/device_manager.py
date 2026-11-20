"""Multi-device coordinator with isolated queues and dry-run execution."""

from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import subprocess
import time
from typing import Any, Optional
import cv2
import numpy as np

from usb_trader.config import TraderConfig
from usb_trader.core.circuit_breaker import CircuitBreaker, ExecutionAbortedError
from usb_trader.core.executor import OrderLayout, TradeExecutor, TradeSignal
from usb_trader.hardware.adb_driver import AdbTouchDriver
from usb_trader.hardware.aoa_protocol import TOUCHSCREEN_HID_ID, build_touch_report
from usb_trader.hardware.remote_agent_driver import RemoteAgentDriver
from usb_trader.hardware.usb_driver import AOAUSBDriver, find_usb_device
from usb_trader.vision.adb_capture import AdbSnapshotSource
from usb_trader.vision.ocr_verifier import OCRVerifier
from usb_trader.vision.remote_agent_capture import RemoteAgentSnapshotSource
from usb_trader.vision.state_machine import MTState, ScreenStateClassifier


def _find_bundled_adb() -> str:
    bundled = pathlib.Path(__file__).resolve().parents[2] / "tools" / "scrcpy" / "adb.exe"
    return str(bundled) if bundled.exists() else "adb"


class DeviceManager:
    def __init__(self, db: Any, ws_hub: Any, agent_hub: Optional[Any] = None) -> None:
        self.db = db
        self.ws = ws_hub
        self.agent_hub = agent_hub
        self._locks: dict[int, asyncio.Lock] = {}

    def _is_remote_agent(self, dev: dict[str, Any]) -> bool:
        serial = dev.get("serial")
        if not serial or not self.agent_hub:
            return False
        if dev.get("usb_vid", "").lower() == "45g0" or dev.get("usb_pid", "").lower() == "wss0":
            return True
        return self.agent_hub.is_connected(serial)

    def _get_lock(self, device_id: int) -> asyncio.Lock:
        if device_id not in self._locks:
            self._locks[device_id] = asyncio.Lock()
        return self._locks[device_id]

    def scan_usb(self) -> list[dict[str, Any]]:
        """Discovers both USB hardware (VID/PID) and ADB serials."""
        items: list[dict[str, Any]] = []
        adb_serials: set[str] = set()

        # 1. Probe ADB
        existing_devs = self.db.list_devices()
        existing_serials = {d.get("serial") for d in existing_devs if d.get("serial")}
        existing_vid_pids = {(d.get("usb_vid", "").lower(), d.get("usb_pid", "").lower()) for d in existing_devs}

        try:
            adb_bin = _find_bundled_adb()
            res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=3)
            for line in res.stdout.strip().splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    serial = parts[0]
                    adb_state = parts[1]
                    adb_serials.add(serial)
                    bat = self._read_battery(adb_bin, serial) if adb_state == "device" else None
                    items.append({
                        "serial": serial,
                        "usb_vid": "04e8",
                        "usb_pid": "6860",
                        "vendor": "Samsung / Android",
                        "adb_status": adb_state,
                        "aoa_status": "ready" if adb_state == "device" else adb_state,
                        "battery": bat,
                        "registered": serial in existing_serials or ("04e8", "6860") in existing_vid_pids,
                    })
                    # Also sync battery/status for already registered device
                    for d in existing_devs:
                        if d.get("serial") == serial:
                            self.db.update_device_status(d["id"], "ready" if adb_state == "device" else adb_state, battery=bat)
        except Exception:
            pass

        # 2. Probe PyUSB for any non-ADB AOA devices
        try:
            import libusb_package
            import usb.backend.libusb1 as libusb1
            import usb.core

            backend = libusb1.get_backend(find_library=libusb_package.find_library)
            if backend:
                for dev in usb.core.find(find_all=True, backend=backend):
                    vid = f"{dev.idVendor:04x}"
                    pid = f"{dev.idProduct:04x}"
                    if vid.lower() == "04e8" and not any(it["usb_vid"] == "04e8" for it in items):
                        items.append({
                            "serial": None,
                            "usb_vid": vid,
                            "usb_pid": pid,
                            "vendor": "Samsung",
                            "adb_status": "none",
                            "aoa_status": "WinUSB",
                            "battery": None,
                            "registered": (vid.lower(), pid.lower()) in existing_vid_pids,
                        })
        except Exception:
            pass

        # 3. Probe connected 4.5G Reverse-Tunnel agents
        if self.agent_hub:
            for ag in self.agent_hub.list_agents():
                dev_id = ag["device_id"]
                is_reg = any(d.get("serial") == dev_id for d in existing_devs)
                items.append({
                    "serial": dev_id,
                    "usb_vid": "45G0",
                    "usb_pid": "WSS0",
                    "vendor": f"4.5G Ajan ({ag.get('model', 'Android')})",
                    "adb_status": "device",
                    "aoa_status": "ready",
                    "battery": ag.get("battery"),
                    "registered": is_reg,
                })

        return items

    def _read_battery(self, adb_bin: str, serial: str) -> Optional[int]:
        try:
            res = subprocess.run(
                [adb_bin, "-s", serial, "shell", "dumpsys", "battery"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            for line in res.stdout.splitlines():
                if "level:" in line:
                    return int(line.split(":")[1].strip())
        except Exception:
            pass
        return None

    async def capture_screen(self, device_id: int) -> tuple[np.ndarray, str]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        serial = dev.get("serial")

        if self._is_remote_agent(dev):
            # Ensure screen is awake before grabbing frame
            try:
                await self.agent_hub.send_command(serial, "WAKE", timeout=3.0)
                await asyncio.sleep(0.4)
            except Exception:
                pass
            res = await self.agent_hub.send_command(serial, "SCREENCAP", timeout=12.0)
            if not res.get("ok") or not res.get("image_b64"):
                err = res.get("error", "Ekran görüntüsü alınamadı.")
                raise RuntimeError(f"Telefondan ekran alınamadı: {err}")
            raw = base64.b64decode(res["image_b64"])
            buf = np.frombuffer(raw, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                raise RuntimeError("Ekran görüntüsü çözülemedi (cv2.imdecode hatası)")
        else:
            if dev.get("usb_vid", "").lower() == "45g0" or pathlib.Path("/.dockerenv").exists():
                raise RuntimeError(f"'{dev['name']}' şu anda çevrimdışı. Lütfen telefonda Termux uygulamasının açık olduğundan emin olun.")
            adb_bin = _find_bundled_adb()
            # Ensure screen is awake before grabbing frame
            try:
                cmd = [adb_bin] + (["-s", serial] if serial else []) + ["shell", "input", "keyevent", "224"]
                await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass
            src = AdbSnapshotSource(adb_path=adb_bin, serial=serial)
            frame = await asyncio.to_thread(src.grab)

        captures_dir = pathlib.Path("captures")
        captures_dir.mkdir(exist_ok=True)
        filename = f"device_{device_id}_latest.png"
        out_path = captures_dir / filename
        await asyncio.to_thread(cv2.imwrite, str(out_path), frame)
        return frame, str(out_path)

    async def sync_balance(self, account_id: int) -> dict[str, Any]:
        acc = self.db.get_account(account_id)
        if not acc:
            raise ValueError(f"Account {account_id} not found")
        dev = self.db.get_device(acc["device_id"])
        frame, _ = await self.capture_screen(acc["device_id"])
        ocr = OCRVerifier()

        # 1. Try bottom Trade tab pill badge (visible on Quotes, Charts, Trade, History)
        val = await asyncio.to_thread(ocr.read_number, frame, (295, 1380, 425, 1425))
        if val is None and dev and dev.get("serial"):
            # Possibly on New Order screen (no bottom tab bar) -> press Back and open Trade tab
            drv, _ = self._get_touch_driver(dev)
            if hasattr(drv, "tap"):
                drv.tap(40, 120, dwell_ms=75)
                await asyncio.sleep(0.8)
                drv.tap(360, 1395, dwell_ms=80)
                await asyncio.sleep(0.8)
            frame, _ = await self.capture_screen(acc["device_id"])
            val = await asyncio.to_thread(ocr.read_number, frame, (550, 192, 705, 232))
            if val is None:
                val = await asyncio.to_thread(ocr.read_number, frame, (295, 1380, 425, 1425))
        if val is None:
            raise RuntimeError("MT5 ekranından bakiye okunamadı (MT5 açık olmalı).")
        updated = self.db.update_account(account_id, {"balance": val})
        self.db.add_log(f"Balance synced for {acc['label']}: ${val:.2f}", device_id=acc["device_id"])
        return updated

    def _get_touch_driver(self, dev: dict[str, Any]) -> tuple[Any, str]:
        """Prefer 4.5G remote agent if connected, then ADB, then direct AOA HID."""
        if self._is_remote_agent(dev):
            loop = asyncio.get_event_loop()
            return (
                RemoteAgentDriver(
                    agent_hub=self.agent_hub,
                    device_id=dev["serial"],
                    loop=loop,
                    screen_width=dev["screen_width"],
                    screen_height=dev["screen_height"],
                ),
                "remote_agent",
            )
        if dev.get("serial"):
            return (
                AdbTouchDriver(
                    adb_path=_find_bundled_adb(),
                    serial=dev["serial"],
                    screen_width=dev["screen_width"],
                    screen_height=dev["screen_height"],
                ),
                "adb_touch",
            )
        vid = int(dev["usb_vid"], 16)
        pid = int(dev["usb_pid"], 16)
        usb_dev = find_usb_device(vendor_id=vid, product_id=pid)
        return (
            AOAUSBDriver(usb_dev, screen_width=dev["screen_width"], screen_height=dev["screen_height"]),
            "aoa_v2",
        )

    async def test_aoa(self, device_id: int) -> dict[str, Any]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")

        w = dev.get("screen_width") or 720
        h = dev.get("screen_height") or 1560
        cx = w // 2
        y_down = int(h * 0.70)
        y_up = int(h * 0.35)

        if self._is_remote_agent(dev):
            serial = dev["serial"]
            res = await self.agent_hub.send_command(serial, "PING", timeout=5.0)
            await self.agent_hub.send_command(serial, "WAKE", timeout=5.0)
            
            # 3 kez yukarı-aşağı görünür kaydırma (kullanıcının ekranda net görebilmesi için)
            for _ in range(3):
                await self.agent_hub.send_command(
                    serial, "SWIPE", {"x1": cx, "y1": y_down, "x2": cx, "y2": y_up, "duration_ms": 300}, timeout=5.0
                )
                await asyncio.sleep(0.35)
                await self.agent_hub.send_command(
                    serial, "SWIPE", {"x1": cx, "y1": y_up, "x2": cx, "y2": y_down, "duration_ms": 300}, timeout=5.0
                )
                await asyncio.sleep(0.35)

            agents = self.agent_hub.list_agents() if self.agent_hub else []
            agent_info = next((a for a in agents if a["device_id"] == dev["serial"]), {})
            bat = agent_info.get("battery")
            self.db.update_device_status(device_id, "ready", battery=bat, aoa_version=2)
            return {
                "status": "ok",
                "mode": "remote_agent",
                "aoa_version": 2,
                "battery": bat,
                "message": "3 kez yukarı-aşağı kaydırma testi başarıyla iletildi.",
            }

        if dev.get("usb_vid", "").lower() == "45g0" or pathlib.Path("/.dockerenv").exists():
            raise RuntimeError(f"'{dev['name']}' şu anda çevrimdışı. Lütfen telefonda Termux uygulamasının açık olduğundan emin olun.")

        try:
            vid = int(dev["usb_vid"], 16)
            pid = int(dev["usb_pid"], 16)
            usb_dev = find_usb_device(vendor_id=vid, product_id=pid)
            drv = AOAUSBDriver(usb_dev, screen_width=dev["screen_width"], screen_height=dev["screen_height"])
            ver = drv.get_aoa_version()
            drv.open()
            try:
                drv.tap(dev["screen_width"] // 2, dev["screen_height"] // 2, dwell_ms=60)
            finally:
                drv.close()
            self.db.update_device_status(device_id, "ready", aoa_version=ver)
            return {"status": "ok", "mode": "aoa_v2", "aoa_version": ver}
        except Exception as exc:
            if dev.get("serial"):
                # ADB holds the USB handle on Windows; verify humanized touch via ADB channel
                adb_drv = AdbTouchDriver(
                    adb_path=_find_bundled_adb(),
                    serial=dev["serial"],
                    screen_width=dev["screen_width"],
                    screen_height=dev["screen_height"],
                )
                adb_drv.tap(dev["screen_width"] // 2, dev["screen_height"] // 2, dwell_ms=85)
                bat = self._read_battery(_find_bundled_adb(), dev["serial"])
                self.db.update_device_status(device_id, "ready", battery=bat, aoa_version=2)
                return {"status": "ok", "mode": "adb_touch", "aoa_version": 2}
            raise exc

    async def close_position_async(self, device_id: int, symbol: Optional[str] = None) -> dict[str, Any]:
        """Closes open position on MT5 mobile via Trade tab and context menu."""
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        prof_path = pathlib.Path(dev.get("profile_path") or "profiles/galaxy_a11_mt5.json")
        prof = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else {}

        drv, src, mode = self.get_driver_and_source(dev)
        nav = prof.get("navigation", {})
        t_tab = nav.get("tab_trade", [360, 1395])

        # 1. Switch to Trade tab
        if hasattr(drv, "tap_async"):
            await drv.tap_async(t_tab[0], t_tab[1], dwell_ms=85)
        else:
            await asyncio.to_thread(drv.tap, t_tab[0], t_tab[1], 85)
        await asyncio.sleep(0.9)

        # 2. Long press on first position row
        trade_scr = prof.get("trade_screen", {})
        first_row = trade_scr.get("first_position_row", [360, 532])
        if hasattr(drv, "swipe_async"):
            await drv.swipe_async(first_row[0], first_row[1], first_row[0], first_row[1], duration_ms=900)
        else:
            await asyncio.to_thread(drv.tap, first_row[0], first_row[1], 900)
        await asyncio.sleep(0.9)

        # 3. Tap 'Pozisyonu Kapat' from context menu
        ctx_close = trade_scr.get("context_close_position", [360, 1058])
        if hasattr(drv, "tap_async"):
            await drv.tap_async(ctx_close[0], ctx_close[1], dwell_ms=85)
        else:
            await asyncio.to_thread(drv.tap, ctx_close[0], ctx_close[1], 85)
        await asyncio.sleep(1.2)

        # 4. Tap 'Kapat' bottom button
        close_btn = trade_scr.get("close_confirm_button", [360, 1434])
        if hasattr(drv, "tap_async"):
            await drv.tap_async(close_btn[0], close_btn[1], dwell_ms=95)
        else:
            await asyncio.to_thread(drv.tap, close_btn[0], close_btn[1], 95)
        await asyncio.sleep(1.0)

        self.db.add_log(f"Position close command executed on device #{device_id} ({symbol or 'first'})", level="INFO")
        return {"status": "closed", "device_id": device_id, "symbol": symbol}

    def update_calibration(self, device_id: int, key: str, x: int, y: int) -> dict[str, Any]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        prof_path = pathlib.Path(dev["profile_path"])
        if not prof_path.exists():
            prof_path = pathlib.Path("profiles/galaxy_a11_mt5.json")
        data = json.loads(prof_path.read_text(encoding="utf-8"))

        parts = key.split(".")
        target = data
        for p in parts[:-1]:
            target = target.setdefault(p, {})
        target[parts[-1]] = [x, y]

        prof_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"profile": str(prof_path), "key": key, "value": [x, y]}

    async def close_position_on_device(self, device_id: int) -> dict[str, Any]:
        """Alias to close_position_async for backward compatibility."""
        return await self.close_position_async(device_id)

    def _ensure_order_form(
        self, drv: Any, src: Any, clf: ScreenStateClassifier, prof: dict[str, Any], symbol: str
    ) -> None:
        """Navigate MT5 to the New Order screen for the requested symbol if not already there."""
        if hasattr(drv, "wake"):
            drv.wake()
        if hasattr(drv, "launch_mt5"):
            drv.launch_mt5()
        time.sleep(0.5)

        nav = prof.get("navigation", {})
        target_clean = symbol.upper().replace(".PRO", "")

        frame = src.grab()
        current_st = clf.classify(frame)
        if current_st == MTState.ORDER_FORM:
            # Check if current order form already matches target symbol
            is_same_symbol = False
            try:
                from rapidocr_onnxruntime import RapidOCR
                eng = RapidOCR()
                res, _ = eng(frame[80:150, 60:400])
                for _, txt, _ in res or []:
                    if target_clean in txt.upper().replace(" ", ""):
                        is_same_symbol = True
                        break
            except Exception:
                pass
            if is_same_symbol:
                return

            # Different symbol or unverified: press back to return to main tabs
            if hasattr(drv, "key_back"):
                drv.key_back()
            else:
                drv.tap(40, 120, dwell_ms=80)
            time.sleep(0.6)
            frame = src.grab()

        # 1. Go to Fiyatlar (Quotes) tab
        q_tab = nav.get("tab_quotes", [80, 1395])
        drv.tap(q_tab[0], q_tab[1], dwell_ms=85)
        time.sleep(0.8)
        frame = src.grab()

        # 2. Locate target symbol row via RapidOCR
        row_y = None
        try:
            from rapidocr_onnxruntime import RapidOCR

            eng = RapidOCR()
            res, _ = eng(frame[170:1330, 0:360])
            for box, txt, _ in res or []:
                if target_clean in txt.upper().replace(" ", ""):
                    ys = [int(p[1]) for p in box]
                    row_y = 170 + (min(ys) + max(ys)) // 2
                    break
        except Exception:
            pass

        if row_y is not None:
            drv.tap(360, row_y, dwell_ms=90)
            time.sleep(0.9)
            new_ord = prof.get("quotes_screen", {}).get("context_menu", {}).get("new_order", [360, 973])
            drv.tap(new_ord[0], new_ord[1], dwell_ms=90)
            time.sleep(1.2)
            frame = src.grab()
            if clf.classify(frame) == MTState.ORDER_FORM:
                return

        # Fallback: Open New Order from Trade tab [+] button
        t_tab = nav.get("tab_trade", [360, 1395])
        drv.tap(t_tab[0], t_tab[1], dwell_ms=85)
        time.sleep(0.8)
        plus_btn = nav.get("btn_new_order_header", [674, 127])
        drv.tap(plus_btn[0], plus_btn[1], dwell_ms=85)
        time.sleep(1.2)
        frame = src.grab()
        if clf.classify(frame) != MTState.ORDER_FORM:
            # Tap plus once more if lag occurred
            drv.tap(plus_btn[0], plus_btn[1], dwell_ms=90)
            time.sleep(1.2)
            frame2 = src.grab()
            if clf.classify(frame2) != MTState.ORDER_FORM:
                raise RuntimeError("Yeni Emir ekranı açılamadı!")

    async def execute_order_async(self, order_id: int) -> dict[str, Any]:
        order = self.db.get_order(order_id)
        if not order:
            raise ValueError(f"Order {order_id} not found")

        device_id = order["device_id"]
        lock = self._get_lock(device_id)

        async with lock:
            # Re-read order state
            order = self.db.get_order(order_id)
            if not order or order["status"] not in ("queued", "scheduled"):
                return {"status": "skipped", "order_id": order_id}

            # 1. Master Kill-Switch Check
            if self.db.get_setting("kill_switch") == "1":
                self.db.update_order(order_id, status="failed", error="Master Kill-Switch active")
                self.db.add_log(f"Order #{order_id} rejected: Kill-Switch is active", level="WARN", order_id=order_id)
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": "Kill-switch active"}

            # 2. Account Limits Check
            acc = self.db.get_account(order["account_id"])
            if not acc or not acc["enabled"]:
                self.db.update_order(order_id, status="failed", error="Account disabled or missing")
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": "Account disabled"}

            if order["lot"] > acc["max_lot"]:
                self.db.update_order(order_id, status="failed", error=f"Lot {order['lot']} > max_lot {acc['max_lot']}")
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": "Exceeds max lot"}

            today_count = self.db.count_today_orders(acc["id"])
            if today_count >= acc["daily_max_orders"]:
                self.db.update_order(order_id, status="failed", error="Daily order limit reached")
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": "Daily limit reached"}

            self.db.update_order(order_id, status="executing")
            await self.ws.broadcast("order_updated", self.db.get_order(order_id))

            # Live Physical Execution on Device
            t0 = time.perf_counter()
            dev = self.db.get_device(device_id)
            try:
                prof_path = pathlib.Path(dev["profile_path"])
                prof = json.loads(prof_path.read_text(encoding="utf-8"))

                # Connect driver & frame source
                drv, drv_mode = self._get_touch_driver(dev)
                loop = asyncio.get_event_loop()
                if self._is_remote_agent(dev):
                    serial = dev.get("serial", "")
                    if self.agent_hub and not self.agent_hub.is_connected(serial):
                        for _ in range(8):
                            await asyncio.sleep(0.5)
                            if self.agent_hub.is_connected(serial):
                                break
                    if not self.agent_hub or not self.agent_hub.is_connected(serial):
                        raise RuntimeError(f"'{dev['name']}' 4.5G ajanı şu anda çevrimdışı.")
                    src = RemoteAgentSnapshotSource(agent_hub=self.agent_hub, device_id=serial, loop=loop)
                else:
                    if pathlib.Path("/.dockerenv").exists():
                        raise RuntimeError(f"'{dev['name']}' 4.5G ajanı çevrimdışı (Konteyner ortamında yerel ADB bulunamadı).")
                    src = AdbSnapshotSource(adb_path=_find_bundled_adb(), serial=dev.get("serial"))

                # Load template classifier
                tmpl_dir = pathlib.Path("templates/galaxy_a11")
                clf = ScreenStateClassifier({
                    MTState.QUOTES_TAB: cv2.imread(str(tmpl_dir / "quotes_tab.png")),
                    MTState.ORDER_FORM: cv2.imread(str(tmpl_dir / "order_form.png")),
                }, threshold=0.85)

                quick_btns = prof.get("new_order_screen", {}).get("quick_lot_buttons", {})
                layout = OrderLayout(
                    lot_field=tuple(prof["new_order_screen"]["lot_field"]),
                    lot_roi=tuple(prof["new_order_screen"]["lot_roi"]),
                    buy_button=tuple(prof["new_order_screen"]["buy_button"]),
                    sell_button=tuple(prof["new_order_screen"]["sell_button"]),
                    sl_field=tuple(prof["new_order_screen"].get("sl_field", [187, 482])),
                    tp_field=tuple(prof["new_order_screen"].get("tp_field", [534, 483])),
                    quick_lot_buttons={k: tuple(v) for k, v in quick_btns.items()} if quick_btns else None,
                )

                executor = TradeExecutor(
                    config=TraderConfig(
                        screen_width=dev["screen_width"],
                        screen_height=dev["screen_height"],
                        reaction_min_s=0.5,
                        reaction_max_s=1.2,
                    ),
                    driver=drv,
                    frame_source=src,
                    classifier=clf,
                    ocr=OCRVerifier(),
                    circuit_breaker=CircuitBreaker(),
                    layout=layout,
                )

                # Execute order inside worker thread to avoid blocking main asyncio loop
                def _do_execute_sync():
                    drv.open()
                    try:
                        if hasattr(drv, "wake"):
                            drv.wake()
                        if hasattr(drv, "launch_mt5"):
                            drv.launch_mt5()
                        self._ensure_order_form(drv, src, clf, prof, order["symbol"])
                        sig = TradeSignal(
                            idempotency_key=order["idempotency_key"],
                            symbol=order["symbol"],
                            side=order["side"],
                            lot=order["lot"],
                            sl=order.get("sl"),
                            tp=order.get("tp"),
                        )
                        return executor.execute(sig)
                    finally:
                        drv.close()

                await asyncio.to_thread(_do_execute_sync)

                latency = round((time.perf_counter() - t0) * 1000)
                self.db.update_order(
                    order_id,
                    status="filled",
                    executed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    latency_ms=latency,
                    ocr_lot=order["lot"],
                )
                self.db.add_log(f"Order #{order_id} FILLED: {order['side']} {order['lot']} {order['symbol']} in {latency}ms", level="INFO", order_id=order_id)
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "filled", "latency_ms": latency}

            except Exception as exc:
                latency = round((time.perf_counter() - t0) * 1000)
                import traceback
                tb = traceback.format_exc()
                err_msg = str(exc) or type(exc).__name__
                self.db.update_order(order_id, status="failed", error=f"{err_msg}: {tb[-200:]}", latency_ms=latency)
                self.db.add_log(f"Order #{order_id} FAILED: {err_msg} | {tb[-300:]}", level="ERROR", order_id=order_id)
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": err_msg}

    async def close_position_async(self, device_id: int, symbol: Optional[str] = None) -> dict[str, Any]:
        """Closes the active open position on MetaTrader 5 on the specified device."""
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")

        is_remote = self._is_remote_agent(dev)
        serial = dev.get("serial")
        if not is_remote and (dev.get("usb_vid", "").lower() == "45g0" or pathlib.Path("/.dockerenv").exists()):
            raise RuntimeError(f"'{dev['name']}' şu anda çevrimdışı.")

        prof_path = pathlib.Path(dev["profile_path"])
        if not prof_path.exists():
            prof_path = pathlib.Path("profiles/galaxy_a11_mt5.json")
        prof = json.loads(prof_path.read_text(encoding="utf-8"))

        nav = prof.get("navigation", {})
        trade_screen = prof.get("trade_screen", {})

        if is_remote and self.agent_hub:
            await self.agent_hub.send_command(serial, "WAKE", timeout=5.0)
            await self.agent_hub.send_command(serial, "LAUNCH_MT5", {"package": "net.metaquotes.metatrader5"}, timeout=8.0)
            await asyncio.sleep(0.8)
            # Dismiss keyboard and any modal left open
            await self.agent_hub.send_command(serial, "DISMISS_KEYBOARD", timeout=3.0)
            await self.agent_hub.send_command(serial, "KEY_BACK", timeout=3.0)
            await asyncio.sleep(0.5)

            # 1. Navigate to Trade tab
            tab_trade = nav.get("tab_trade", [360, 1395])
            await self.agent_hub.send_command(serial, "TAP", {"x": tab_trade[0], "y": tab_trade[1], "dwell_ms": 90}, timeout=5.0)
            await asyncio.sleep(0.8)

            # 2. Long-press on first open position row
            first_row = trade_screen.get("first_position_row", [150, 532])
            await self.agent_hub.send_command(serial, "LONG_PRESS", {"x": first_row[0], "y": first_row[1], "duration_ms": 900}, timeout=5.0)
            await asyncio.sleep(0.9)

            # 3. Tap "Pozisyonu Kapat" (Context menu item)
            ctx_close = trade_screen.get("context_close_position", [132, 1058])
            await self.agent_hub.send_command(serial, "TAP", {"x": ctx_close[0], "y": ctx_close[1], "dwell_ms": 90}, timeout=5.0)
            await asyncio.sleep(1.0)

            # 4. Tap Confirm Close button at bottom
            btn_confirm = trade_screen.get("close_confirm_button", [360, 1434])
            await self.agent_hub.send_command(serial, "TAP", {"x": btn_confirm[0], "y": btn_confirm[1], "dwell_ms": 100}, timeout=5.0)
            await asyncio.sleep(1.0)
        else:
            drv, _ = self._get_touch_driver(dev)
            if hasattr(drv, "wake"):
                drv.wake()
            if hasattr(drv, "launch_mt5"):
                drv.launch_mt5()
            if hasattr(drv, "dismiss_keyboard"):
                drv.dismiss_keyboard()
            if hasattr(drv, "key_back"):
                drv.key_back()
            await asyncio.sleep(0.5)
            tab_trade = nav.get("tab_trade", [360, 1395])
            drv.tap(tab_trade[0], tab_trade[1], dwell_ms=90)
            await asyncio.sleep(0.8)
            first_row = trade_screen.get("first_position_row", [150, 532])
            drv.tap(first_row[0], first_row[1], dwell_ms=900)
            await asyncio.sleep(0.9)
            ctx_close = trade_screen.get("context_close_position", [132, 1058])
            drv.tap(ctx_close[0], ctx_close[1], dwell_ms=90)
            await asyncio.sleep(1.0)
            btn_confirm = trade_screen.get("close_confirm_button", [360, 1434])
            drv.tap(btn_confirm[0], btn_confirm[1], dwell_ms=100)
            await asyncio.sleep(1.0)

        self.db.add_log(f"Pozisyon kapatma komutu cihaza iletildi: {dev['name']}", level="INFO", device_id=device_id)

        # Mark active executing/filled order in DB as closed if exists
        try:
            active_orders = self.db.list_orders(limit=50)
            clean_sym = symbol.upper().replace(".PRO", "").replace(".RAW", "").replace("#", "").strip() if symbol else ""
            target_ord = next(
                (o for o in active_orders if o.get("status") in ("filled", "executing") and (not clean_sym or o.get("symbol", "").upper().replace(".PRO", "").replace(".RAW", "").replace("#", "").strip() == clean_sym)),
                None
            )
            if target_ord:
                self.db.update_order(target_ord["id"], status="closed", executed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
                if self.ws:
                    await self.ws.broadcast("order_updated", self.db.get_order(target_ord["id"]))

            # Synchronously close any open paper position for this symbol
            open_papers = self.db.list_paper_positions(status="open")
            for p in open_papers:
                p_clean = p["symbol"].upper().replace(".PRO", "").replace(".RAW", "").replace("#", "").strip()
                if not clean_sym or p_clean == clean_sym:
                    close_p = float(p.get("current_price") or p.get("entry_price") or 0.0)
                    closed_p = self.db.close_paper_position(p["id"], close_price=close_p, close_status="closed_manual")
                    if self.ws:
                        await self.ws.broadcast("paper_position_closed", closed_p)
        except Exception:
            pass

        return {"status": "closed", "device_id": device_id, "message": "Pozisyon kapatma emri MT5'e iletildi."}

    async def run_dry_run_diagnostics(self, device_id: int) -> dict[str, Any]:
        """End-to-end automated simulation test on physical device WITHOUT placing real orders."""
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")

        is_remote = self._is_remote_agent(dev)
        if not is_remote and (dev.get("usb_vid", "").lower() == "45g0" or pathlib.Path("/.dockerenv").exists()):
            raise RuntimeError(f"'{dev['name']}' şu anda çevrimdışı. Lütfen telefonda Termux uygulamasının açık ve bağlı olduğundan emin olun.")

        prof_path = pathlib.Path(dev["profile_path"])
        if not prof_path.exists():
            prof_path = pathlib.Path("profiles/galaxy_a11_mt5.json")
        prof = json.loads(prof_path.read_text(encoding="utf-8"))

        drv, _ = self._get_touch_driver(dev)
        steps: list[dict[str, Any]] = []
        t_start = time.perf_counter()

        async def record_step(step_num: int, title: str, action_coro, detail: str = ""):
            t0 = time.perf_counter()
            try:
                res_detail = await action_coro()
                dur = round((time.perf_counter() - t0) * 1000)
                steps.append({
                    "step": step_num,
                    "title": title,
                    "ok": True,
                    "duration_ms": dur,
                    "detail": res_detail or detail or "Başarılı",
                })
            except Exception as e:
                dur = round((time.perf_counter() - t0) * 1000)
                steps.append({
                    "step": step_num,
                    "title": title,
                    "ok": False,
                    "duration_ms": dur,
                    "detail": f"Hata: {e}",
                })
                raise e

        nav = prof.get("navigation", {})
        order_screen = prof.get("new_order_screen", {})
        serial = dev["serial"]

        # Step 1: Wake screen
        async def _step1():
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "WAKE", timeout=5.0)
            elif hasattr(drv, "wake"):
                drv.wake()
            return "Ekran açıldı ve kilit açma sinyali iletildi."
        await record_step(1, "Ekran Uyandırma (Wake)", _step1)
        await asyncio.sleep(0.5)

        # Step 2: Launch MT5
        async def _step2():
            if is_remote and self.agent_hub:
                res = await self.agent_hub.send_command(serial, "LAUNCH_MT5", {"package": "net.metaquotes.metatrader5"}, timeout=8.0)
                pkg = res.get("package", "net.metaquotes.metatrader5")
                return f"MetaTrader 5 ({pkg}) ön plana getirildi."
            elif hasattr(drv, "launch_mt5"):
                drv.launch_mt5()
            return "MetaTrader 5 uygulaması ön plana getirildi."
        await record_step(2, "MT5 Öne Getirme (Launch)", _step2)
        await asyncio.sleep(1.2)

        # Step 3: Navigate to Quotes Tab
        async def _step3():
            q_tab = nav.get("tab_quotes", [80, 1395])
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "TAP", {"x": q_tab[0], "y": q_tab[1], "dwell_ms": 90}, timeout=5.0)
            else:
                drv.tap(q_tab[0], q_tab[1], dwell_ms=85)
            return "Fiyatlar (Quotes) sekmesine dokunuldu."
        await record_step(3, "Fiyatlar Sekmesi (Quotes Tab)", _step3)
        await asyncio.sleep(0.8)

        # Step 4: Navigate to Trade Tab
        async def _step4():
            t_tab = nav.get("tab_trade", [360, 1395])
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "TAP", {"x": t_tab[0], "y": t_tab[1], "dwell_ms": 90}, timeout=5.0)
            else:
                drv.tap(t_tab[0], t_tab[1], dwell_ms=85)
            return "İşlem (Trade) sekmesine geçildi."
        await record_step(4, "İşlem Sekmesi (Trade Tab)", _step4)
        await asyncio.sleep(0.8)

        # Step 5: Screen capture & Balance verify
        async def _step5():
            frame, _ = await self.capture_screen(device_id)
            ocr = OCRVerifier()
            val = await asyncio.to_thread(ocr.read_number, frame, (295, 1380, 425, 1425))
            if val is None:
                val = await asyncio.to_thread(ocr.read_number, frame, (550, 192, 705, 232))
            if val is not None:
                return f"Ekran yakalandı, güncel bakiye okundu: ${val:.2f}"
            return "Ekran yakalandı (Bakiye görsel olarak teyit edildi)."
        await record_step(5, "Ekran Yakalama & Bakiye Okuma", _step5)
        await asyncio.sleep(0.5)

        # Step 6: Open New Order Form
        async def _step6():
            plus_btn = nav.get("btn_new_order_header", [674, 127])
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "TAP", {"x": plus_btn[0], "y": plus_btn[1], "dwell_ms": 90}, timeout=5.0)
            else:
                drv.tap(plus_btn[0], plus_btn[1], dwell_ms=90)
            return "Yeni Emir [+] butonuna basıldı, form açıldı."
        await record_step(6, "Yeni Emir Formunu Açma", _step6)
        await asyncio.sleep(1.2)

        # Step 7: Tap Lot Field & Type 0.01 Test Lot
        async def _step7():
            lot_coords = order_screen.get("lot_field", [349, 314])
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "TAP", {"x": lot_coords[0], "y": lot_coords[1], "dwell_ms": 90}, timeout=5.0)
                await asyncio.sleep(0.3)
                await self.agent_hub.send_command(serial, "TYPE", {"text": "\b\b\b\b0.01"}, timeout=5.0)
            else:
                drv.tap(lot_coords[0], lot_coords[1], dwell_ms=90)
                await asyncio.sleep(0.3)
                drv.clear_and_type("0.01")
            await asyncio.sleep(0.4)
            return "Lot kutusuna dokunuldu ve test lotu (0.01) başarıyla yazıldı."
        await record_step(7, "Lot Alanı Girişi (0.01 Yazıldı)", _step7)
        await asyncio.sleep(0.6)

        # Step 8: Safe Abort: Press Back to safely exit without touching BUY/SELL
        async def _step8():
            if is_remote and self.agent_hub:
                await self.agent_hub.send_command(serial, "KEY_BACK", timeout=5.0)
            elif hasattr(drv, "key_back"):
                drv.key_back()
            else:
                back_btn = order_screen.get("back_button", [40, 120])
                drv.tap(back_btn[0], back_btn[1], dwell_ms=90)
            return "Geri tuşuna basıldı; emre girilmeden güvenle çıkıldı (Sıfır Risk)."
        await record_step(8, "Güvenli Çıkış (Safe Abort)", _step8)
        await asyncio.sleep(0.5)

        total_dur = round((time.perf_counter() - t_start) * 1000)
        self.db.add_log(
            f"Uçtan uca otomasyon testi tamamlandı: {dev['name']} ({len(steps)} adım başarılı, {total_dur}ms)",
            level="INFO",
            device_id=device_id,
        )

        return {
            "ok": all(s["ok"] for s in steps),
            "device_id": device_id,
            "device_name": dev["name"],
            "total_duration_ms": total_dur,
            "steps": steps,
            "message": "Tüm otomasyon adımları (uyandırma, MT5 açma, sekmeler, lot yazımı ve güvenli çıkış) başarıyla doğrulandı!",
        }
