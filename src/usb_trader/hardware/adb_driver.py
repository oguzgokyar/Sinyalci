"""Humanized touch and keyboard input driver over active ADB USB channel."""

from __future__ import annotations

import subprocess
import time
from typing import Callable, Iterable, Optional


class AdbTouchDriver:
    """Implements the same driver interface as AOAUSBDriver over an active ADB USB session."""

    def __init__(
        self,
        adb_path: str,
        serial: Optional[str] = None,
        screen_width: int = 720,
        screen_height: int = 1560,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.adb_path = adb_path
        self.serial = serial
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._sleep = sleep_fn

    def _run(self, *args: str) -> None:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(["shell", *args])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ADB input failed: {err or res.returncode}")

    def open(self) -> None:
        pass

    def close(self) -> None:
        pass

    def tap(self, x_px: int, y_px: int, dwell_ms: int = 100) -> None:
        x = max(0, min(self.screen_width - 1, int(x_px)))
        y = max(0, min(self.screen_height - 1, int(y_px)))
        duration = max(40, int(dwell_ms))
        # Using touchscreen swipe with identical start/end simulates natural press dwell duration
        self._run("input", "touchscreen", "swipe", str(x), str(y), str(x), str(y), str(duration))

    def swipe_path(self, points: Iterable[tuple[int, int]], step_delay_ms: float = 12.0) -> None:
        pts = list(points)
        if len(pts) < 2:
            return
        x1, y1 = pts[0]
        x2, y2 = pts[-1]
        total_ms = max(120, int(len(pts) * step_delay_ms))
        self._run("input", "touchscreen", "swipe", str(x1), str(y1), str(x2), str(y2), str(total_ms))

    def type_text(self, text: str, key_delay_ms: float = 65.0) -> None:
        for ch in text:
            if ch == "\b":
                self._run("input", "keyevent", "67")
            elif ch == "\n":
                self._run("input", "keyevent", "66")
            else:
                self._run("input", "text", ch)
            self._sleep(key_delay_ms / 1000.0)

    def clear_and_type(self, text: str, key_delay_ms: float = 45.0) -> None:
        """Move cursor to end, clear existing digits reliably, type new text, hide keyboard."""
        self._run("input", "keyevent", "123")  # KEYCODE_MOVE_END
        for _ in range(10):
            self._run("input", "keyevent", "67")  # KEYCODE_DEL
        self._run("input", "text", text)
        self._sleep(key_delay_ms / 1000.0)
        self.dismiss_keyboard()

    def dismiss_keyboard(self) -> None:
        self._run("input", "keyevent", "111")  # KEYCODE_ESCAPE hides soft keyboard cleanly
