"""Background worker for scheduled and queued order execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


class OrderScheduler:
    def __init__(self, db: Any, device_manager: Any, ws_hub: Any = None, poll_interval_s: float = 1.0) -> None:
        self.db = db
        self.dm = device_manager
        self.ws_hub = ws_hub
        self.interval = poll_interval_s
        self._task: asyncio.Task | None = None
        self._autopilot_task: asyncio.Task | None = None
        self._running = False
        self._is_scanning = False
        self._last_scan_time = 0.0

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            self._autopilot_task = asyncio.create_task(self._run_autopilot_loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
        if self._autopilot_task:
            self._autopilot_task.cancel()

    async def _run_loop(self) -> None:
        while self._running:
            try:
                now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                due_orders = self.db.due_scheduled_orders(now_iso)
                for ord_data in due_orders:
                    # Fire and forget into device worker queue
                    asyncio.create_task(self.dm.execute_order_async(ord_data["id"]))
            except asyncio.CancelledError:
                break
            except Exception:
                pass
            await asyncio.sleep(self.interval)

    async def _run_autopilot_loop(self) -> None:
        """Autopilot background loop: updates live paper trades and scans for market setups."""
        from usb_trader.core.strategy_engine import StrategyEngine
        import time

        engine = StrategyEngine(self.db)
        ticks = 0

        # Wait 5 seconds after startup before first tick
        await asyncio.sleep(5.0)

        while self._running:
            try:
                ticks += 1

                # 1. Every 15 seconds: update live paper positions (prices, floating PnL, TP/SL triggers)
                if ticks % 3 == 0:
                    await engine.update_live_paper_positions(ws_hub=self.ws_hub)

                # 2. Every 60 seconds: check Autopilot for new setups
                if ticks % 12 == 0:
                    cfg = engine.get_config()
                    if cfg.get("autopilot_enabled") and not self._is_scanning:
                        # Cooldown: at least 15 minutes between deep AI scans to prevent excessive calls
                        now = time.time()
                        if now - self._last_scan_time >= 900:
                            # Check active open positions
                            open_pos = self.db.list_paper_positions(status="open")
                            if len(open_pos) < 3:
                                # Run lightweight technical prescreener
                                candidates = engine.prescreen_favorites()
                                best = next((c for c in candidates if c["score"] >= 60 and c["setup"] in ["BUY", "SELL"]), None)
                                if best:
                                    self._is_scanning = True
                                    self._last_scan_time = now
                                    try:
                                        await engine.run_autopilot_tick(ws_hub=self.ws_hub)
                                    finally:
                                        self._is_scanning = False

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log warning and keep worker resilient
                try:
                    self.db.add_log(f"Otopilot Döngü Uyarısı: {e}", level="WARN")
                except Exception:
                    pass

            await asyncio.sleep(5.0)

