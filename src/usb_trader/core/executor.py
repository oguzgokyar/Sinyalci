"""Closed-loop humanized TradeExecutor orchestrating vision, humanizer, and USB AOA."""

from __future__ import annotations

import asyncio
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
    sl_roi: Optional[tuple[int, int, int, int]] = None
    tp_field: Optional[tuple[int, int]] = None
    tp_roi: Optional[tuple[int, int, int, int]] = None


def _format_price(price: float, symbol: str) -> str:
    sym = symbol.upper()
    if "JPY" in sym or "XAU" in sym or "GOLD" in sym or "OIL" in sym:
        return f"{price:.2f}"
    if price < 10.0:
        return f"{price:.4f}"
    return f"{price:.2f}"


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

    async def _human_tap_async(self, coords: tuple[int, int]) -> None:
        tx, ty = apply_gaussian_jitter(
            coords[0],
            coords[1],
            sigma=self._cfg.jitter_sigma_px,
            max_offset=self._cfg.jitter_max_offset_px,
        )
        dwell = sample_dwell_ms(self._cfg.dwell_min_ms, self._cfg.dwell_max_ms)
        tap_async_fn = getattr(self._driver, "tap_async", None)
        if asyncio.iscoroutinefunction(tap_async_fn):
            await self._driver.tap_async(tx, ty, dwell_ms=dwell)
        else:
            await asyncio.to_thread(self._driver.tap, tx, ty, dwell)

    def _type_value(self, text: str) -> None:
        if hasattr(self._driver, "clear_and_type"):
            self._driver.clear_and_type(text)
        else:
            self._driver.type_text("\b\b\b\b" + text)

    async def _type_value_async(self, text: str) -> None:
        cat_async_fn = getattr(self._driver, "clear_and_type_async", None)
        if asyncio.iscoroutinefunction(cat_async_fn):
            await self._driver.clear_and_type_async(text)
            return

        if hasattr(self._driver, "clear_and_type"):
            await asyncio.to_thread(self._driver.clear_and_type, text)
            return

        tt_async_fn = getattr(self._driver, "type_text_async", None)
        if asyncio.iscoroutinefunction(tt_async_fn):
            await self._driver.type_text_async(text)
            return

        await asyncio.to_thread(self._driver.type_text, "\b\b\b\b" + text)

    async def _grab_frame_async(self) -> Any:
        grab_async_fn = getattr(self._frames, "grab_async", None)
        if asyncio.iscoroutinefunction(grab_async_fn):
            return await self._frames.grab_async()
        return await asyncio.to_thread(self._frames.grab)

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

        # 2. Enter lot size only if screen lot differs from target lot
        if not self._ocr.verify_value(frame, self._layout.lot_roi, expected=signal.lot):
            self._human_tap(self._layout.lot_field)
            self._sleep(0.25)
            self._type_value(f"{signal.lot:.2f}")
            self._sleep(0.35)

        # 3. Enter Stop Loss if specified and layout supports it
        if signal.sl is not None and self._layout.sl_field:
            self._human_tap(self._layout.sl_field)
            self._sleep(0.25)
            self._type_value(_format_price(signal.sl, signal.symbol))
            self._sleep(0.30)

        # 4. Enter Take Profit if specified and layout supports it
        if signal.tp is not None and self._layout.tp_field:
            self._human_tap(self._layout.tp_field)
            self._sleep(0.25)
            self._type_value(_format_price(signal.tp, signal.symbol))
            self._sleep(0.30)

        # 5. Closed-loop OCR confirmation before pressing BUY/SELL
        verify_frame = self._frames.grab()
        verify_state = self._classifier.classify(verify_frame)
        self._cb.assert_safe(verify_state)
        if not self._ocr.verify_value(verify_frame, self._layout.lot_roi, expected=signal.lot):
            self._cb.trigger_kill_switch("OCR lot verification mismatch")
            raise ExecutionAbortedError("Aborted before execution: lot size mismatch on screen")

        # 6. Execute humanized BUY or SELL tap
        target_btn = self._layout.buy_button if signal.side == "BUY" else self._layout.sell_button
        self._human_tap(target_btn)

        # 7. Confirm post-trade screen state
        done_frame = self._frames.grab()
        done_state = self._classifier.classify(done_frame)
        self._cb.assert_safe(done_state)
        return done_state in (MTState.ORDER_DONE, MTState.QUOTES_TAB)

    async def execute_async(self, signal: TradeSignal) -> bool:
        if not self._cb.claim_signal(signal.idempotency_key):
            raise ExecutionAbortedError(f"Duplicate signal ignored: {signal.idempotency_key}")

        reaction_s = sample_reaction_delay_s(self._cfg.reaction_min_s, self._cfg.reaction_max_s)
        if reaction_s > 0:
            await asyncio.sleep(reaction_s)

        # 1. Verify we are on the Order Form and no popup is blocking
        frame = await self._grab_frame_async()
        state = self._classifier.classify(frame)
        self._cb.assert_safe(state)
        if state != MTState.ORDER_FORM:
            raise ExecutionAbortedError(f"Expected ORDER_FORM, observed {state.value}")

        # 2. Enter lot size only if screen lot differs from target lot
        if not self._ocr.verify_value(frame, self._layout.lot_roi, expected=signal.lot):
            await self._human_tap_async(self._layout.lot_field)
            await asyncio.sleep(0.25)
            await self._type_value_async(f"{signal.lot:.2f}")
            await asyncio.sleep(0.35)

        # 3. Enter Stop Loss if specified and layout supports it
        if signal.sl is not None and self._layout.sl_field:
            await self._human_tap_async(self._layout.sl_field)
            await asyncio.sleep(0.25)
            await self._type_value_async(_format_price(signal.sl, signal.symbol))
            await asyncio.sleep(0.30)

        # 4. Enter Take Profit if specified and layout supports it
        if signal.tp is not None and self._layout.tp_field:
            await self._human_tap_async(self._layout.tp_field)
            await asyncio.sleep(0.25)
            await self._type_value_async(_format_price(signal.tp, signal.symbol))
            await asyncio.sleep(0.30)

        # 5. Closed-loop OCR confirmation before pressing BUY/SELL
        verify_frame = await self._grab_frame_async()
        verify_state = self._classifier.classify(verify_frame)
        self._cb.assert_safe(verify_state)
        if not self._ocr.verify_value(verify_frame, self._layout.lot_roi, expected=signal.lot):
            self._cb.trigger_kill_switch("OCR lot verification mismatch")
            raise ExecutionAbortedError("Aborted before execution: lot size mismatch on screen")

        # 6. Execute humanized BUY or SELL tap
        target_btn = self._layout.buy_button if signal.side == "BUY" else self._layout.sell_button
        await self._human_tap_async(target_btn)

        # 7. Confirm post-trade screen state
        done_frame = await self._grab_frame_async()
        done_state = self._classifier.classify(done_frame)
        self._cb.assert_safe(done_state)
        return done_state in (MTState.ORDER_DONE, MTState.QUOTES_TAB)
