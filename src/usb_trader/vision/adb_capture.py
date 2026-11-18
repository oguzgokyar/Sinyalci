"""Headless, on-demand ADB screencap frame grabber (no window, zero PC freeze)."""

from __future__ import annotations

import pathlib
import subprocess
from typing import Any, Callable, Optional
import cv2
import numpy as np


class AdbCaptureError(RuntimeError):
    """Raised when ADB screencap execution or decoding fails."""


def _find_bundled_adb() -> str:
    bundled = pathlib.Path(__file__).resolve().parents[3] / "tools" / "scrcpy" / "adb.exe"
    if bundled.exists():
        return str(bundled)
    return "adb"


class AdbSnapshotSource:
    """Grabs 720x1560 frames on demand via adb exec-out screencap -p in memory."""

    def __init__(
        self,
        adb_path: Optional[str] = None,
        serial: Optional[str] = None,
        runner: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.adb_path = adb_path or _find_bundled_adb()
        self.serial = serial
        self._runner = runner or subprocess.run

    def grab(self) -> np.ndarray:
        cmd = [self.adb_path]
        if self.serial:
            cmd.extend(["-s", self.serial])
        cmd.extend(["exec-out", "screencap", "-p"])

        res = self._runner(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="replace").strip() if res.stderr else "Unknown error"
            raise AdbCaptureError(f"ADB screencap failed (exit {res.returncode}): {err}")

        # Decode raw in-memory PNG bytes without touching disk
        buf = np.frombuffer(res.stdout, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise AdbCaptureError("Failed to decode screencap PNG buffer from device.")
        return frame
