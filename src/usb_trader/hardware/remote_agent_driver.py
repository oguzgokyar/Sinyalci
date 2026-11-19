"""Remote Agent Touch Driver communicating with Android Termux over WebSocket RPC."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Iterable, Optional


class RemoteAgentTouchDriver:
    """Implements the touch driver interface over a reverse-tunneled phone agent WebSocket."""

    def __init__(
        self,
        agent_hub: Any,
        device_id: str,
        screen_width: int = 720,
        screen_height: int = 1560,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.agent_hub = agent_hub
        self.device_id = device_id
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._sleep = sleep_fn

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def tap_async(self, x_px: int, y_px: int, dwell_ms: int = 100) -> dict[str, Any]:
        x = max(0, min(self.screen_width - 1, int(x_px)))
        y = max(0, min(self.screen_height - 1, int(y_px)))
        return await self.agent_hub.send_command(
            self.device_id,
            "TAP",
            {"x": x, "y": y, "dwell_ms": max(40, int(dwell_ms))},
        )

    def tap(self, x_px: int, y_px: int, dwell_ms: int = 100) -> None:
        """Synchronous wrapper for tap."""
        try:
            loop = asyncio.get_running_loop()
            # If in running loop, schedule as task
            future = asyncio.run_coroutine_threadsafe(
                self.tap_async(x_px, y_px, dwell_ms), loop
            )
            future.result(timeout=10.0)
        except RuntimeError:
            asyncio.run(self.tap_async(x_px, y_px, dwell_ms))

    async def swipe_async(
        self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 250
    ) -> dict[str, Any]:
        return await self.agent_hub.send_command(
            self.device_id,
            "SWIPE",
            {
                "x1": int(x1),
                "y1": int(y1),
                "x2": int(x2),
                "y2": int(y2),
                "duration_ms": max(50, int(duration_ms)),
            },
        )

    def swipe_path(
        self, points: Iterable[tuple[int, int]], step_delay_ms: float = 12.0
    ) -> None:
        pts = list(points)
        if len(pts) < 2:
            return
        x1, y1 = pts[0]
        x2, y2 = pts[-1]
        total_ms = max(120, int(len(pts) * step_delay_ms))
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.swipe_async(x1, y1, x2, y2, total_ms), loop
            )
            future.result(timeout=10.0)
        except RuntimeError:
            asyncio.run(self.swipe_async(x1, y1, x2, y2, total_ms))

    async def type_text_async(self, text: str) -> dict[str, Any]:
        return await self.agent_hub.send_command(
            self.device_id, "TYPE", {"text": text}
        )

    def type_text(self, text: str, key_delay_ms: float = 65.0) -> None:
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.type_text_async(text), loop
            )
            future.result(timeout=10.0)
        except RuntimeError:
            asyncio.run(self.type_text_async(text))

    async def clear_and_type_async(self, text: str) -> dict[str, Any]:
        return await self.agent_hub.send_command(
            self.device_id, "CLEAR_AND_TYPE", {"text": text}
        )

    def clear_and_type(self, text: str, key_delay_ms: float = 45.0) -> None:
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.clear_and_type_async(text), loop
            )
            future.result(timeout=10.0)
        except RuntimeError:
            asyncio.run(self.clear_and_type_async(text))

    async def dismiss_keyboard_async(self) -> dict[str, Any]:
        return await self.agent_hub.send_command(
            self.device_id, "DISMISS_KEYBOARD", {}
        )

    def dismiss_keyboard(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(
                self.dismiss_keyboard_async(), loop
            )
            future.result(timeout=10.0)
        except RuntimeError:
            asyncio.run(self.dismiss_keyboard_async())

    async def wake_async(self) -> dict[str, Any]:
        return await self.agent_hub.send_command(self.device_id, "WAKE", {})

    async def launch_mt5_async(
        self, pkg: str = "net.metaquotes.metatrader5"
    ) -> dict[str, Any]:
        return await self.agent_hub.send_command(
            self.device_id, "LAUNCH_MT5", {"package": pkg}
        )
