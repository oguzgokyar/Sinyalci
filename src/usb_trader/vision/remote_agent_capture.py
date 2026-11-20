"""Remote snapshot frame grabber fetching base64 screencaps from 4.5G phone agents."""

from __future__ import annotations

import asyncio
import base64
from typing import Any, Optional
import cv2
import numpy as np


class RemoteAgentSnapshotSource:
    """Grabs frames on demand by dispatching SCREENCAP RPC to remote phone agent."""

    def __init__(
        self,
        agent_hub: Any,
        device_id: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.agent_hub = agent_hub
        self.device_id = device_id
        self.loop = loop or asyncio.get_event_loop()

    def grab(self) -> np.ndarray:
        fut = asyncio.run_coroutine_threadsafe(
            self.agent_hub.send_command(self.device_id, "SCREENCAP", timeout=20.0),
            self.loop,
        )
        res = fut.result(timeout=20.0)
        if not res.get("ok") or not res.get("image_b64"):
            err = res.get("error", "Bilinmeyen screencap hatası")
            raise RuntimeError(f"Uzak telefon ajanı ekran görüntüsü alamadı: {err}")

        raw = base64.b64decode(res["image_b64"])
        buf = np.frombuffer(raw, dtype=np.uint8)
        frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError("Uzak ekran görüntüsü çözülemedi (cv2.imdecode hatası)")
        return frame
