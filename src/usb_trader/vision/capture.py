"""Frame source interfaces for UVC capture cards and test mocks."""

from typing import Protocol
import cv2
import numpy as np


class FrameSource(Protocol):
    def grab(self) -> np.ndarray: ...


class StaticFrameSource:
    def __init__(self, frame: np.ndarray) -> None:
        self._frame = frame

    def grab(self) -> np.ndarray:
        return self._frame.copy()


class UVCCaptureSource:
    """On-demand snapshot capture from a UVC HDMI capture card or webcam."""

    def __init__(self, device_index: int = 0) -> None:
        self._cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW)
        if not self._cap.isOpened():
            raise RuntimeError(f"Unable to open capture device index {device_index}")

    def grab(self) -> np.ndarray:
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("Failed to read frame from capture source")
        return frame

    def release(self) -> None:
        self._cap.release()
