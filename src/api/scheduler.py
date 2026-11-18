"""Background worker for scheduled and queued order execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


class OrderScheduler:
    def __init__(self, db: Any, device_manager: Any, poll_interval_s: float = 1.0) -> None:
        self.db = db
        self.dm = device_manager
        self.interval = poll_interval_s
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

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
