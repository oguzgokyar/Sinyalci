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
from usb_trader.hardware.aoa_protocol import TOUCHSCREEN_HID_ID, build_touch_report
from usb_trader.hardware.usb_driver import AOAUSBDriver, find_usb_device
from usb_trader.vision.adb_capture import AdbSnapshotSource
from usb_trader.vision.ocr_verifier import OCRVerifier
from usb_trader.vision.state_machine import MTState, ScreenStateClassifier


def _find_bundled_adb() -> str:
    bundled = pathlib.Path(__file__).resolve().parents[3] / "tools" / "scrcpy" / "adb.exe"
    return str(bundled) if bundled.exists() else "adb"


class DeviceManager:
    def __init__(self, db: Any, ws_hub: Any) -> None:
        self.db = db
        self.ws = ws_hub
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
        try:
            adb_bin = _find_bundled_adb()
            res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=3)
            for line in res.stdout.strip().splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2:
                    adb_serials.add(parts[0])
                    items.append({
                        "serial": parts[0],
                        "usb_vid": "04e8",
                        "usb_pid": "6860",
                        "vendor": "Samsung / Android",
                        "adb_status": parts[1],
                        "aoa_status": "ready",
                        "battery": None,
                    })
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
                        })
        except Exception:
            pass

        return items

    def capture_screen(self, device_id: int) -> tuple[np.ndarray, str]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        serial = dev.get("serial")
        src = AdbSnapshotSource(adb_path=_find_bundled_adb(), serial=serial)
        frame = src.grab()
        # Save timestamped capture
        captures_dir = pathlib.Path("captures")
        captures_dir.mkdir(exist_ok=True)
        filename = f"device_{device_id}_latest.png"
        out_path = captures_dir / filename
        cv2.imwrite(str(out_path), frame)
        return frame, str(out_path)

    def test_aoa(self, device_id: int) -> dict[str, Any]:
        dev = self.db.get_device(device_id)
        if not dev:
            raise ValueError(f"Device {device_id} not found")
        vid = int(dev["usb_vid"], 16)
        pid = int(dev["usb_pid"], 16)
        usb_dev = find_usb_device(vendor_id=vid, product_id=pid)
        drv = AOAUSBDriver(usb_dev, screen_width=dev["screen_width"], screen_height=dev["screen_height"])
        ver = drv.get_aoa_version()
        drv.open()
        try:
            # Gentle test tap at center
            drv.tap(dev["screen_width"] // 2, dev["screen_height"] // 2, dwell_ms=60)
        finally:
            drv.close()
        self.db.update_device_status(device_id, "ready", aoa_version=ver)
        return {"status": "ok", "aoa_version": ver}

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
                vid = int(dev["usb_vid"], 16)
                pid = int(dev["usb_pid"], 16)
                usb_dev = find_usb_device(vendor_id=vid, product_id=pid)
                drv = AOAUSBDriver(usb_dev, screen_width=dev["screen_width"], screen_height=dev["screen_height"])
                src = AdbSnapshotSource(adb_path=_find_bundled_adb(), serial=dev.get("serial"))

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
                    sig = TradeSignal(
                        idempotency_key=order["idempotency_key"],
                        symbol=order["symbol"],
                        side=order["side"],
                        lot=order["lot"],
                    )
                    executor.execute(sig)
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
