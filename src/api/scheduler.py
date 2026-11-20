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
        self._in_flight: set[int] = set()
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
                # 1. Pick up any queued orders for immediate execution
                orders = self.db.list_orders(limit=10)
                for ord_data in orders:
                    oid = ord_data.get("id")
                    if ord_data.get("status") == "queued" and oid and oid not in self._in_flight:
                        self._in_flight.add(oid)

                        async def _exec_task(o_id: int):
                            try:
                                await self.dm.execute_order_async(o_id)
                            finally:
                                self._in_flight.discard(o_id)

                        asyncio.create_task(_exec_task(oid))

                # 2. Pick up due scheduled orders
                now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                due_orders = self.db.due_scheduled_orders(now_iso)
                for ord_data in due_orders:
                    oid = ord_data.get("id")
                    if oid and oid not in self._in_flight:
                        self._in_flight.add(oid)

                        async def _exec_task_due(o_id: int):
                            try:
                                await self.dm.execute_order_async(o_id)
                            finally:
                                self._in_flight.discard(o_id)

                        asyncio.create_task(_exec_task_due(oid))
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
        engine.dm = self.dm
        ticks = 0

        # Wait 5 seconds after startup before first tick
        await asyncio.sleep(5.0)

        while self._running:
            try:
                ticks += 1
                cfg = engine.get_config()
                poll_interval = int(cfg.get("data_poll_interval", 10))
                # Base tick is 5 seconds; calculate modulo based on user configured poll interval
                poll_ticks = max(1, poll_interval // 5)

                # 1. Update live paper positions based on user selected interval
                if ticks % poll_ticks == 0:
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
                                    # Verify TradingAgents health before triggering deep research
                                    health = await engine.check_tradingagents_health(timeout=2.0)
                                    if not health.get("healthy"):
                                        self.db.add_log("Otopilot duraklatıldı: TradingAgents AI motoru çevrimdışı.", level="WARN")
                                        continue

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

