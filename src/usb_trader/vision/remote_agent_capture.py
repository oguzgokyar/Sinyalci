"""Remote Agent Snapshot Source capturing frames from Android Termux via WebSocket RPC."""

from __future__ import annotations

import asyncio
import base64
from typing import Any
import cv2
import numpy as np


class RemoteAgentCaptureError(RuntimeError):
    """Raised when remote screencap or image decoding fails."""


class RemoteAgentSnapshotSource:
    """Grabs frames on demand from a remote 4.5G Android phone agent via WebSocket RPC."""

    def __init__(self, agent_hub: Any, device_id: str) -> None:
        self.agent_hub = agent_hub
        self.device_id = device_id

    async def grab_async(self, timeout: float = 20.0) -> np.ndarray:
        reply = await self.agent_hub.send_command(
            self.device_id, "SCREENCAP", timeout=timeout
        )
        if not reply.get("ok"):
            err = reply.get("error", "Unknown screencap error")
            raise RemoteAgentCaptureError(f"Remote agent screencap failed: {err}")

        b64_data = reply.get("image_b64")
        if not b64_data:
            raise RemoteAgentCaptureError("Remote agent returned empty image data.")

        try:
            raw_bytes = base64.b64decode(b64_data)
            buf = np.frombuffer(raw_bytes, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            if frame is None:
                raise RemoteAgentCaptureError("Failed to decode base64 PNG buffer into image.")
            return frame
        except Exception as exc:
            raise RemoteAgentCaptureError(f"Failed to decode screencap: {exc}") from exc

    def grab(self) -> np.ndarray:
        try:
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(self.grab_async(), loop)
            return future.result(timeout=20.0)
        except RuntimeError:
            return asyncio.run(self.grab_async())
