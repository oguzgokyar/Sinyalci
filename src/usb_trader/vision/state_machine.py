"""MetaTrader screen state definitions and priority-based classifier."""

from enum import Enum
import numpy as np
from usb_trader.vision.template_matcher import find_template


class MTState(str, Enum):
    UNKNOWN = "unknown"
    POPUP_ERROR = "popup_error"
    QUOTES_TAB = "quotes_tab"
    ORDER_FORM = "order_form"
    ORDER_DONE = "order_done"


STATE_PRIORITY = (
    MTState.POPUP_ERROR,
    MTState.ORDER_DONE,
    MTState.ORDER_FORM,
    MTState.QUOTES_TAB,
)


class ScreenStateClassifier:
    def __init__(self, templates: dict[MTState, np.ndarray], threshold: float = 0.85) -> None:
        self._templates = templates
        self._threshold = threshold

    def classify(self, frame: np.ndarray) -> MTState:
        for state in STATE_PRIORITY:
            tmpl = self._templates.get(state)
            if tmpl is not None and find_template(frame, tmpl, threshold=self._threshold) is not None:
                return state
        return MTState.UNKNOWN
