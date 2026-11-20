"""Remote touch and keyboard input driver routing over 4.5G Reverse-Tunnel WebSocket."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Iterable, Optional


class RemoteAgentDriver:
    """Implements touch and typing driver interface by dispatching commands

    to remote phone agents over WebSocket RPC.
    """

    def __init__(
        self,
        agent_hub: Any,
        device_id: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        screen_width: int = 720,
        screen_height: int = 1560,
    ) -> None:
        self.agent_hub = agent_hub
        self.device_id = device_id
        self.loop = loop or asyncio.get_event_loop()
        self.screen_width = screen_width
        self.screen_height = screen_height

    def _call(self, action: str, params: Optional[dict[str, Any]] = None, timeout: float = 25.0) -> dict[str, Any]:
        fut = asyncio.run_coroutine_threadsafe(
            self.agent_hub.send_command(self.device_id, action, params or {}, timeout=timeout),
            self.loop,
        )
        return fut.result(timeout=timeout)

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def wake(self) -> None:
        self._call("WAKE", timeout=20.0)

    def launch_mt5(self, pkg: str = "net.metaquotes.metatrader5") -> None:
        self._call("LAUNCH_MT5", {"package": pkg}, timeout=20.0)

    def tap(self, x_px: int, y_px: int, dwell_ms: int = 100) -> None:
        x = max(0, min(self.screen_width - 1, int(x_px)))
        y = max(0, min(self.screen_height - 1, int(y_px)))
        self._call("TAP", {"x": x, "y": y, "dwell_ms": max(40, int(dwell_ms))})

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._call("SWIPE", {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms})

    def long_press(self, x_px: int, y_px: int, duration_ms: int = 900) -> None:
        x = max(0, min(self.screen_width - 1, int(x_px)))
        y = max(0, min(self.screen_height - 1, int(y_px)))
        self._call("LONG_PRESS", {"x": x, "y": y, "duration_ms": int(duration_ms)})

    def type_text(self, text: str, key_delay_ms: float = 65.0) -> None:
        self._call("TYPE", {"text": text})

    def clear_and_type(self, text: str, key_delay_ms: float = 45.0) -> None:
        """Clear existing digits reliably, type new text, and dismiss keyboard."""
        self._call("CLEAR_AND_TYPE", {"text": text})

    def dismiss_keyboard(self) -> None:
        self._call("DISMISS_KEYBOARD")

    def key_back(self) -> None:
        self._call("KEY_BACK")

    def key_home(self) -> None:
        self._call("KEY_HOME")
