"""Numeric OCR parser and ROI value verifier for MetaTrader fields (lot, SL, TP)."""

import re
from typing import Callable, Optional
import numpy as np

_NUM_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def parse_numeric_text(text: str) -> Optional[float]:
    match = _NUM_RE.search(text.strip())
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


class _RapidOCRReader:
    def __init__(self) -> None:
        self._engine = None

    def __call__(self, roi: np.ndarray) -> str:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR

            self._engine = RapidOCR()
        res, _ = self._engine(roi)
        if not res:
            return ""
        return " ".join(item[1] for item in res)


class OCRVerifier:
    def __init__(
        self,
        reader_fn: Optional[Callable[[np.ndarray], str]] = None,
        tolerance: float = 1e-4,
    ) -> None:
        self._reader = reader_fn or _RapidOCRReader()
        self._tolerance = tolerance

    def read_number(self, frame: np.ndarray, roi: tuple[int, int, int, int]) -> Optional[float]:
        x1, y1, x2, y2 = roi
        crop = frame[y1:y2, x1:x2]
        raw_text = self._reader(crop)
        return parse_numeric_text(raw_text)

    def verify_value(
        self, frame: np.ndarray, roi: tuple[int, int, int, int], expected: float
    ) -> bool:
        observed = self.read_number(frame, roi)
        if observed is None:
            return False
        return abs(observed - expected) <= self._tolerance
