"""Multi-device coordinator with isolated queues and dry-run execution."""

from __future__ import annotations

import asyncio
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
from usb_trader.hardware.remote_agent_driver import RemoteAgentTouchDriver
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

    def _find_agent_id(self, dev: dict[str, Any]) -> Optional[str]:
        if not self.agent_hub:
            return None
        candidates = [
            dev.get("serial") or "",
            str(dev.get("id") or ""),
            dev.get("name", "").lower().replace(" ", "_"),
            "galaxy_a11",
        ]
        for c in candidates:
            if c and self.agent_hub.is_connected(c):
                return c
        agents = self.agent_hub.list_agents()
        if len(agents) == 1:
            return str(agents[0]["device_id"])
        return None

    def get_driver_and_source(self, dev: dict[str, Any]) -> tuple[Any, Any, str]:
        agent_id = self._find_agent_id(dev)
        if agent_id:
            drv = RemoteAgentTouchDriver(
                agent_hub=self.agent_hub,
                device_id=agent_id,
                screen_width=dev.get("screen_width", 720),
                screen_height=dev.get("screen_height", 1560),
            )
            src = RemoteAgentSnapshotSource(agent_hub=self.agent_hub, device_id=agent_id)
            return drv, src, "remote_agent"
        drv, mode = self._get_touch_driver(dev)
        src = AdbSnapshotSource(adb_path=_find_bundled_adb(), serial=dev.get("serial"))
        return drv, src, mode

    async def capture_screen_async(self, device_id: int) -> tuple[np.ndarray, str]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        drv, src, mode = self.get_driver_and_source(dev)
        if mode == "remote_agent":
            await drv.wake_async()
            frame = await src.grab_async()
        else:
            serial = dev.get("serial")
            adb_bin = _find_bundled_adb()
            try:
                cmd = [adb_bin] + (["-s", serial] if serial else []) + ["shell", "input", "keyevent", "224"]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass
            frame = await asyncio.to_thread(src.grab)

        captures_dir = pathlib.Path("captures")
        captures_dir.mkdir(exist_ok=True)
        filename = f"device_{device_id}_latest.png"
        out_path = captures_dir / filename
        cv2.imwrite(str(out_path), frame)
        return frame, str(out_path)

    def capture_screen(self, device_id: int) -> tuple[np.ndarray, str]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        drv, src, mode = self.get_driver_and_source(dev)
        if mode == "remote_agent":
            frame = src.grab()
        else:
            serial = dev.get("serial")
            adb_bin = _find_bundled_adb()
            try:
                cmd = [adb_bin] + (["-s", serial] if serial else []) + ["shell", "input", "keyevent", "224"]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            except Exception:
                pass
            frame = src.grab()

        captures_dir = pathlib.Path("captures")
        captures_dir.mkdir(exist_ok=True)
        filename = f"device_{device_id}_latest.png"
        out_path = captures_dir / filename
        cv2.imwrite(str(out_path), frame)
        return frame, str(out_path)

    def sync_balance(self, account_id: int) -> dict[str, Any]:
        acc = self.db.get_account(account_id)
        if not acc:
            raise ValueError(f"Account {account_id} not found")
        dev = self.db.get_device(acc["device_id"])
        frame, _ = self.capture_screen(acc["device_id"])
        ocr = OCRVerifier()

        # 1. Try bottom Trade tab pill badge (visible on Quotes, Charts, Trade, History)
        val = ocr.read_number(frame, (295, 1380, 425, 1425))
        if val is None and dev and dev.get("serial"):
            # Possibly on New Order screen (no bottom tab bar) -> press Back and open Trade tab
            drv, _ = self._get_touch_driver(dev)
            drv.tap(40, 120, dwell_ms=75)
            time.sleep(0.8)
            drv.tap(360, 1395, dwell_ms=80)
            time.sleep(0.8)
            frame, _ = self.capture_screen(acc["device_id"])
            val = ocr.read_number(frame, (550, 192, 705, 232))
            if val is None:
                val = ocr.read_number(frame, (295, 1380, 425, 1425))
        if val is None:
            raise RuntimeError("MT5 ekranından bakiye okunamadı (MT5 açık olmalı).")
        updated = self.db.update_account(account_id, {"balance": val})
        self.db.add_log(f"Balance synced for {acc['label']}: ${val:.2f}", device_id=acc["device_id"])
        return updated

    def _get_touch_driver(self, dev: dict[str, Any]) -> tuple[Any, str]:
        """Prefer AOA HID when USB handle is free; fall back to ADB touch when ADB holds USB."""
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

    async def test_aoa_async(self, device_id: int) -> dict[str, Any]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        drv, src, mode = self.get_driver_and_source(dev)
        if mode == "remote_agent":
            await drv.tap_async(dev["screen_width"] // 2, dev["screen_height"] // 2, dwell_ms=85)
            agent_id = self._find_agent_id(dev) or "galaxy_a11"
            reply = await self.agent_hub.send_command(agent_id, "PING")
            bat = reply.get("battery")
            self.db.update_device_status(device_id, "ready", battery=bat, aoa_version=2)
            return {"status": "ok", "mode": "remote_agent", "aoa_version": 2, "battery": bat}
        return await asyncio.to_thread(self.test_aoa, device_id)

    def test_aoa(self, device_id: int) -> dict[str, Any]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        drv, src, mode = self.get_driver_and_source(dev)
        if mode == "remote_agent":
            drv.tap(dev["screen_width"] // 2, dev["screen_height"] // 2, dwell_ms=85)
            self.db.update_device_status(device_id, "ready", aoa_version=2)
            return {"status": "ok", "mode": "remote_agent", "aoa_version": 2}
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

    def _ensure_order_form(
        self, drv: Any, src: Any, clf: ScreenStateClassifier, prof: dict[str, Any], symbol: str
    ) -> None:
        """Navigate MT5 to the New Order screen for the requested symbol if not already there."""
        frame = src.grab()
        if clf.classify(frame) == MTState.ORDER_FORM:
            return

        # 1. Go to Fiyatlar (Quotes) tab
        nav = prof.get("navigation", {})
        q_tab = nav.get("tab_quotes", [80, 1395])
        drv.tap(q_tab[0], q_tab[1], dwell_ms=85)
        time.sleep(0.8)
        frame = src.grab()

        # 2. Locate target symbol row via RapidOCR
        target_clean = symbol.upper().replace(".PRO", "")
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
            return

        # Fallback: Open New Order from Trade tab [+] button
        t_tab = nav.get("tab_trade", [360, 1395])
        drv.tap(t_tab[0], t_tab[1], dwell_ms=85)
        time.sleep(0.7)
        plus_btn = nav.get("btn_new_order_header", [674, 127])
        drv.tap(plus_btn[0], plus_btn[1], dwell_ms=85)
        time.sleep(1.2)

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

            # 3. Dry-Run Execution Mode
            dry_run = self.db.get_setting("dry_run") == "1"
            if dry_run:
                await asyncio.sleep(0.4)
                self.db.update_order(
                    order_id,
                    status="filled",
                    executed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    latency_ms=420,
                    ocr_lot=order["lot"],
                )
                self.db.add_log(f"[DRY-RUN] Order #{order_id} filled: {order['side']} {order['lot']} {order['symbol']}", level="INFO", order_id=order_id)
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "filled", "dry_run": True}

            # 4. Live Physical Execution on Device
            t0 = time.perf_counter()
            dev = self.db.get_device(device_id)
            try:
                prof_path = pathlib.Path(dev["profile_path"])
                prof = json.loads(prof_path.read_text(encoding="utf-8"))

                # Connect driver & frame source
                drv, src, drv_mode = self.get_driver_and_source(dev)

                # Load template classifier
                tmpl_dir = pathlib.Path("templates/galaxy_a11")
                clf = ScreenStateClassifier({
                    MTState.QUOTES_TAB: cv2.imread(str(tmpl_dir / "quotes_tab.png")),
                    MTState.ORDER_FORM: cv2.imread(str(tmpl_dir / "order_form.png")),
                }, threshold=0.85)

                layout = OrderLayout(
                    lot_field=tuple(prof["new_order_screen"]["lot_field"]),
                    lot_roi=tuple(prof["new_order_screen"]["lot_roi"]),
                    buy_button=tuple(prof["new_order_screen"]["buy_button"]),
                    sell_button=tuple(prof["new_order_screen"]["sell_button"]),
                    sl_field=tuple(prof["new_order_screen"].get("sl_field", [187, 482])),
                    sl_roi=tuple(prof["new_order_screen"].get("sl_roi", [110, 455, 260, 510])),
                    tp_field=tuple(prof["new_order_screen"].get("tp_field", [534, 483])),
                    tp_roi=tuple(prof["new_order_screen"].get("tp_roi", [460, 455, 610, 510])),
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

                # Execute order
                drv.open()
                try:
                    self._ensure_order_form(drv, src, clf, prof, order["symbol"])
                    sig = TradeSignal(
                        idempotency_key=order["idempotency_key"],
                        symbol=order["symbol"],
                        side=order["side"],
                        lot=order["lot"],
                        sl=order.get("sl"),
                        tp=order.get("tp"),
                    )
                    await executor.execute_async(sig)
                finally:
                    drv.close()

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
                err_msg = str(exc)
                self.db.update_order(order_id, status="failed", error=err_msg, latency_ms=latency)
                self.db.add_log(f"Order #{order_id} FAILED: {err_msg}", level="ERROR", order_id=order_id)
                await self.ws.broadcast("order_updated", self.db.get_order(order_id))
                return {"status": "failed", "error": err_msg}
