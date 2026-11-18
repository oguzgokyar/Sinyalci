"""Closed-loop humanized TradeExecutor orchestrating vision, humanizer, and USB AOA."""

from dataclasses import dataclass
import time
from typing import Any, Callable, Literal
from usb_trader.config import TraderConfig
from usb_trader.core.circuit_breaker import CircuitBreaker, ExecutionAbortedError
from usb_trader.humanizer.jitter import apply_gaussian_jitter
from usb_trader.humanizer.timing import sample_dwell_ms, sample_reaction_delay_s
from usb_trader.vision.ocr_verifier import OCRVerifier
from usb_trader.vision.state_machine import MTState


@dataclass(frozen=True)
class TradeSignal:
    idempotency_key: str
    symbol: str
    side: Literal["BUY", "SELL"]
    lot: float


@dataclass(frozen=True)
class OrderLayout:
    lot_field: tuple[int, int]
    lot_roi: tuple[int, int, int, int]
    buy_button: tuple[int, int]
    sell_button: tuple[int, int]


class TradeExecutor:
    def __init__(
        self,
        config: TraderConfig,
        driver: Any,
        frame_source: Any,
        classifier: Any,
        ocr: OCRVerifier,
        circuit_breaker: CircuitBreaker,
        layout: OrderLayout,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._cfg = config
        self._driver = driver
        self._frames = frame_source
        self._classifier = classifier
        self._ocr = ocr
        self._cb = circuit_breaker
        self._layout = layout
        self._sleep = sleep_fn

    def _human_tap(self, coords: tuple[int, int]) -> None:
        tx, ty = apply_gaussian_jitter(
            coords[0],
            coords[1],
            sigma=self._cfg.jitter_sigma_px,
            max_offset=self._cfg.jitter_max_offset_px,
        )
        dwell = sample_dwell_ms(self._cfg.dwell_min_ms, self._cfg.dwell_max_ms)
        self._driver.tap(tx, ty, dwell_ms=dwell)

    def execute(self, signal: TradeSignal) -> bool:
        if not self._cb.claim_signal(signal.idempotency_key):
            raise ExecutionAbortedError(f"Duplicate signal ignored: {signal.idempotency_key}")

        self._sleep(sample_reaction_delay_s(self._cfg.reaction_min_s, self._cfg.reaction_max_s))

        # 1. Verify we are on the Order Form and no popup is blocking
        frame = self._frames.grab()
        state = self._classifier.classify(frame)
        self._cb.assert_safe(state)
        if state != MTState.ORDER_FORM:
            raise ExecutionAbortedError(f"Expected ORDER_FORM, observed {state.value}")

        # 2. Enter lot size via HID keyboard
        self._human_tap(self._layout.lot_field)
        self._driver.type_text("\b\b\b\b" + f"{signal.lot:.2f}")

        # 3. Closed-loop OCR confirmation before pressing BUY/SELL
        verify_frame = self._frames.grab()
        verify_state = self._classifier.classify(verify_frame)
        self._cb.assert_safe(verify_state)
        if not self._ocr.verify_value(verify_frame, self._layout.lot_roi, expected=signal.lot):
            self._cb.trigger_kill_switch("OCR lot verification mismatch")
            raise ExecutionAbortedError("Aborted before execution: lot size mismatch on screen")

        # 4. Execute humanized BUY or SELL tap
        target_btn = self._layout.buy_button if signal.side == "BUY" else self._layout.sell_button
        self._human_tap(target_btn)

        # 5. Confirm post-trade screen state
        done_frame = self._frames.grab()
        done_state = self._classifier.classify(done_frame)
        self._cb.assert_safe(done_state)
        return done_state == MTState.ORDER_DONE
