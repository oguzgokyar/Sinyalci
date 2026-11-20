import base64
from unittest.mock import AsyncMock
import cv2
import numpy as np
import pytest
from usb_trader.hardware.remote_agent_driver import RemoteAgentTouchDriver
from usb_trader.vision.remote_agent_capture import RemoteAgentSnapshotSource


@pytest.mark.anyio
async def test_remote_agent_touch_driver_actions():
    agent_hub = AsyncMock()
    agent_hub.send_command.return_value = {"ok": True}

    drv = RemoteAgentTouchDriver(agent_hub=agent_hub, device_id="galaxy_a11", screen_width=720, screen_height=1560)

    # 1. tap_async
    await drv.tap_async(360, 1200, dwell_ms=90)
    agent_hub.send_command.assert_called_with(
        "galaxy_a11", "TAP", {"x": 360, "y": 1200, "dwell_ms": 90}
    )

    # 2. clear_and_type_async
    await drv.clear_and_type_async("0.25")
    agent_hub.send_command.assert_called_with(
        "galaxy_a11", "CLEAR_AND_TYPE", {"text": "0.25"}
    )

    # 3. swipe_async
    await drv.swipe_async(360, 1200, 360, 400, duration_ms=250)
    agent_hub.send_command.assert_called_with(
        "galaxy_a11", "SWIPE", {"x1": 360, "y1": 1200, "x2": 360, "y2": 400, "duration_ms": 250}
    )

    # 4. dismiss_keyboard_async
    await drv.dismiss_keyboard_async()
    agent_hub.send_command.assert_called_with(
        "galaxy_a11", "DISMISS_KEYBOARD", {}
    )

    # 5. wake_async & launch_mt5_async
    await drv.wake_async()
    agent_hub.send_command.assert_called_with("galaxy_a11", "WAKE", {})
    await drv.launch_mt5_async("net.metaquotes.metatrader5")
    agent_hub.send_command.assert_called_with(
        "galaxy_a11", "LAUNCH_MT5", {"package": "net.metaquotes.metatrader5"}
    )


@pytest.mark.anyio
async def test_remote_agent_snapshot_source_grab():
    # Create a small valid test PNG
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    ok, png_bytes = cv2.imencode(".png", img)
    assert ok
    b64_str = base64.b64encode(png_bytes.tobytes()).decode("ascii")

    agent_hub = AsyncMock()
    agent_hub.send_command.return_value = {"ok": True, "image_b64": b64_str}

    src = RemoteAgentSnapshotSource(agent_hub=agent_hub, device_id="galaxy_a11")
    frame = await src.grab_async()
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (100, 100, 3)
