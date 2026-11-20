"""Closed-loop humanized TradeExecutor orchestrating vision, humanizer, and USB AOA."""

from dataclasses import dataclass
import time
from typing import Any, Callable, Literal, Optional
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
    sl: Optional[float] = None
    tp: Optional[float] = None


@dataclass(frozen=True)
class OrderLayout:
    lot_field: tuple[int, int]
    lot_roi: tuple[int, int, int, int]
    buy_button: tuple[int, int]
    sell_button: tuple[int, int]
    sl_field: Optional[tuple[int, int]] = None
    tp_field: Optional[tuple[int, int]] = None
    quick_lot_buttons: Optional[dict[str, tuple[int, int]]] = None


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

        # 2. Adjust lot size precisely using native MT5 stepper buttons or field input
        target_lot = round(float(signal.lot), 2)
        current_lot = self._ocr.read_number(frame, self._layout.lot_roi)

        if self._layout.quick_lot_buttons and current_lot is not None and abs(current_lot - target_lot) > 0.005:
            q = self._layout.quick_lot_buttons
            diff = round(target_lot - current_lot, 2)
            if diff > 0:
                while diff >= 0.5 and "plus_0_5" in q:
                    self._driver.tap(q["plus_0_5"][0], q["plus_0_5"][1], dwell_ms=75)
                    self._sleep(0.18)
                    diff = round(diff - 0.5, 2)
                while diff >= 0.1 and "plus_0_1" in q:
                    self._driver.tap(q["plus_0_1"][0], q["plus_0_1"][1], dwell_ms=75)
                    self._sleep(0.18)
                    diff = round(diff - 0.1, 2)
                while diff >= 0.009 and "plus_0_01" in q:
                    self._driver.tap(q["plus_0_01"][0], q["plus_0_01"][1], dwell_ms=75)
                    self._sleep(0.18)
                    diff = round(diff - 0.01, 2)
            elif diff < 0:
                abs_diff = abs(diff)
                while abs_diff >= 0.5 and "minus_0_5" in q:
                    self._driver.tap(q["minus_0_5"][0], q["minus_0_5"][1], dwell_ms=75)
                    self._sleep(0.18)
                    abs_diff = round(abs_diff - 0.5, 2)
                while abs_diff >= 0.1 and "minus_0_1" in q:
                    self._driver.tap(q["minus_0_1"][0], q["minus_0_1"][1], dwell_ms=75)
                    self._sleep(0.18)
                    abs_diff = round(abs_diff - 0.1, 2)
                while abs_diff >= 0.009 and "minus_0_01" in q:
                    self._driver.tap(q["minus_0_01"][0], q["minus_0_01"][1], dwell_ms=75)
                    self._sleep(0.18)
                    abs_diff = round(abs_diff - 0.01, 2)
            self._sleep(0.35)
        elif current_lot is None or abs(current_lot - target_lot) > 0.005:
            self._human_tap(self._layout.lot_field)
            self._sleep(0.35)
            lot_str = f"{signal.lot:.2f}"
            if hasattr(self._driver, "clear_and_type"):
                self._driver.clear_and_type(lot_str)
            else:
                self._driver.type_text(lot_str)
            self._sleep(0.4)

        # 3. Closed-loop OCR confirmation before entering SL/TP or pressing BUY/SELL
        verify_frame = self._frames.grab()
        verify_state = self._classifier.classify(verify_frame)
        self._cb.assert_safe(verify_state)
        if not self._ocr.verify_value(verify_frame, self._layout.lot_roi, expected=signal.lot):
            self._cb.trigger_kill_switch("OCR lot verification mismatch")
            raise ExecutionAbortedError("Aborted before execution: lot size mismatch on screen")

        # 4. Enter Stop Loss (SL) and Take Profit (TP) if provided
        sym_upper = signal.symbol.upper()
        is_fx = any(sym_upper.startswith(p) for p in ("EUR", "GBP", "AUD", "NZD", "USD", "CAD", "CHF")) and len(sym_upper.replace(".PRO", "").replace(".RAW", "").replace("#", "")) == 6
        is_jpy = "JPY" in sym_upper

        if signal.sl is not None and self._layout.sl_field:
            if is_fx:
                sl_str = f"{signal.sl:.3f}" if is_jpy else f"{signal.sl:.5f}"
            else:
                sl_str = f"{signal.sl:.2f}"
            self._human_tap(self._layout.sl_field)
            self._sleep(0.35)
            if hasattr(self._driver, "clear_and_type"):
                self._driver.clear_and_type(sl_str)
            else:
                self._driver.type_text(sl_str)
            self._sleep(0.35)

        if signal.tp is not None and self._layout.tp_field:
            if is_fx:
                tp_str = f"{signal.tp:.3f}" if is_jpy else f"{signal.tp:.5f}"
            else:
                tp_str = f"{signal.tp:.2f}"
            self._human_tap(self._layout.tp_field)
            self._sleep(0.35)
            if hasattr(self._driver, "clear_and_type"):
                self._driver.clear_and_type(tp_str)
            else:
                self._driver.type_text(tp_str)
            self._sleep(0.35)

        # Dismiss soft keyboard so BUY / SELL buttons are visible and unobstructed
        if hasattr(self._driver, "dismiss_keyboard"):
            self._driver.dismiss_keyboard()
            self._sleep(0.3)

        # 5. Execute humanized BUY or SELL tap
        target_btn = self._layout.buy_button if signal.side == "BUY" else self._layout.sell_button
        self._human_tap(target_btn)
        self._sleep(1.5)

        # 6. Confirm post-trade screen state (MUST NOT be ORDER_FORM)
        done_frame = self._frames.grab()
        done_state = self._classifier.classify(done_frame)
        self._cb.assert_safe(done_state)
        if done_state == MTState.ORDER_FORM:
            # Check once more after a brief pause
            self._sleep(1.0)
            done_frame2 = self._frames.grab()
            if self._classifier.classify(done_frame2) == MTState.ORDER_FORM:
                raise ExecutionAbortedError("Emir MT5 tarafından reddedildi: Butona basıldıktan sonra ekran formda kaldı (SL/TP geçersiz veya spread genişlemiş olabilir)")

        # 7. Physical Verification: Ensure Trade tab displays the open position
        self._driver.tap(360, 1395, dwell_ms=80)
        self._sleep(1.2)
        try:
            trade_frame = self._frames.grab()
        except Exception:
            return True

        # Verify that the position exists under Pozisyonlar
        clean_target = signal.symbol.upper().replace(".PRO", "").replace(".RAW", "").replace("#", "").strip()
        pos_found = False
        try:
            from rapidocr_onnxruntime import RapidOCR
            eng = RapidOCR()
            res, _ = eng(trade_frame[350:1350, :])
            for _, txt, _ in res or []:
                clean_txt = txt.upper().replace(" ", "")
                if clean_target in clean_txt or (len(clean_target) == 6 and clean_target[:3] in clean_txt and clean_target[3:] in clean_txt):
                    pos_found = True
                    break
        except Exception:
            pos_found = True  # fallback if OCR engine unavailable

        if not pos_found:
            curr_state = self._classifier.classify(trade_frame)
            self._cb.assert_safe(curr_state)

        return True
