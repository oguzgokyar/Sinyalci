from unittest.mock import MagicMock
import cv2
import numpy as np
import pytest
from usb_trader.vision.adb_capture import AdbSnapshotSource, AdbCaptureError


def _encode_png(bgr: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", bgr)
    assert ok
    return buf.tobytes()


def test_adb_snapshot_source_decodes_png_bytes():
    img = np.zeros((156, 72, 3), dtype=np.uint8)
    img[20:40, 10:30] = (10, 200, 30)
    png_bytes = _encode_png(img)

    runner = MagicMock(return_value=MagicMock(returncode=0, stdout=png_bytes, stderr=b""))
    src = AdbSnapshotSource(adb_path="adb.exe", serial="R9XN1234", runner=runner)
    frame = src.grab()

    assert frame.shape == (156, 72, 3)
    assert tuple(frame[30, 20]) == (10, 200, 30)
    cmd = runner.call_args.args[0]
    assert cmd == ["adb.exe", "-s", "R9XN1234", "exec-out", "screencap", "-p"]


def test_adb_snapshot_source_raises_on_adb_failure():
    runner = MagicMock(return_value=MagicMock(returncode=1, stdout=b"", stderr=b"error: no devices"))
    src = AdbSnapshotSource(adb_path="adb.exe", runner=runner)
    with pytest.raises(AdbCaptureError):
        src.grab()
