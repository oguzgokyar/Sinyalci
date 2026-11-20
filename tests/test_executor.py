from unittest.mock import MagicMock
import numpy as np
import pytest
from usb_trader.config import TraderConfig
from usb_trader.core.circuit_breaker import CircuitBreaker, ExecutionAbortedError
from usb_trader.core.executor import TradeExecutor, TradeSignal, OrderLayout
from usb_trader.vision.ocr_verifier import OCRVerifier
from usb_trader.vision.state_machine import MTState


def _make_sequence_source(frames: list[np.ndarray]):
    it = iter(frames)
    src = MagicMock()
    src.grab.side_effect = lambda: next(it)
    return src


def test_executor_runs_closed_loop_buy_order():
    dummy = np.zeros((200, 200, 3), dtype=np.uint8)
    frames = _make_sequence_source([dummy, dummy, dummy])
    classifier = MagicMock()
    classifier.classify.side_effect = [MTState.ORDER_FORM, MTState.ORDER_FORM, MTState.ORDER_DONE]
    driver = MagicMock(spec=["tap", "type_text"])
    # Initial read returns 0.05 (differs from 0.10), verify read returns 0.10
    ocr = OCRVerifier(reader_fn=MagicMock(side_effect=["0.05", "0.10"]))
    cb = CircuitBreaker()

    layout = OrderLayout(
        lot_field=(540, 420),
        lot_roi=(10, 10, 80, 40),
        buy_button=(780, 2100),
        sell_button=(300, 2100),
    )
    executor = TradeExecutor(
        config=TraderConfig(reaction_min_s=0.0, reaction_max_s=0.0),
        driver=driver,
        frame_source=frames,
        classifier=classifier,
        ocr=ocr,
        circuit_breaker=cb,
        layout=layout,
        sleep_fn=lambda _: None,
    )

    result = executor.execute(TradeSignal(idempotency_key="sig-1", symbol="EURUSD", side="BUY", lot=0.10))
    assert result is True
    assert driver.tap.call_count == 3  # lot field + BUY button + trade tab
    driver.type_text.assert_called_once()


def test_executor_aborts_if_ocr_lot_mismatch():
    dummy = np.zeros((200, 200, 3), dtype=np.uint8)
    frames = _make_sequence_source([dummy, dummy])
    classifier = MagicMock()
    classifier.classify.return_value = MTState.ORDER_FORM
    driver = MagicMock()
    ocr = OCRVerifier(reader_fn=lambda _: "9.99")  # Mismatch!
    cb = CircuitBreaker()
    layout = OrderLayout((540, 420), (10, 10, 80, 40), (780, 2100), (300, 2100))

    executor = TradeExecutor(
        config=TraderConfig(reaction_min_s=0.0, reaction_max_s=0.0),
        driver=driver,
        frame_source=frames,
        classifier=classifier,
        ocr=ocr,
        circuit_breaker=cb,
        layout=layout,
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ExecutionAbortedError):
        executor.execute(TradeSignal(idempotency_key="sig-2", symbol="EURUSD", side="BUY", lot=0.10))
    # Must NEVER tap BUY button when lot OCR fails
    assert driver.tap.call_count == 1


def test_executor_populates_sl_and_tp():
    dummy = np.zeros((200, 200, 3), dtype=np.uint8)
    frames = _make_sequence_source([dummy, dummy, dummy, dummy])
    classifier = MagicMock()
    classifier.classify.side_effect = [MTState.ORDER_FORM, MTState.ORDER_FORM, MTState.ORDER_DONE, MTState.UNKNOWN]
    driver = MagicMock(spec=["tap", "clear_and_type", "type_text", "dismiss_keyboard"])
    ocr = OCRVerifier(reader_fn=lambda _: "0.10")  # Lot matches immediately
    cb = CircuitBreaker()

    layout = OrderLayout(
        lot_field=(349, 314),
        lot_roi=(300, 290, 400, 340),
        buy_button=(540, 1436),
        sell_button=(180, 1436),
        sl_field=(187, 482),
        tp_field=(534, 483),
    )
    executor = TradeExecutor(
        config=TraderConfig(reaction_min_s=0.0, reaction_max_s=0.0),
        driver=driver,
        frame_source=frames,
        classifier=classifier,
        ocr=ocr,
        circuit_breaker=cb,
        layout=layout,
        sleep_fn=lambda _: None,
    )

    sig = TradeSignal(
        idempotency_key="sig-sltp",
        symbol="XAUUSD",
        side="SELL",
        lot=0.10,
        sl=3580.50,
        tp=3500.00,
    )
    result = executor.execute(sig)
    assert result is True
    # Driver should tap sl_field, tp_field, sell_button, and verify Trade tab tap
    # taps: sl_field (1), tp_field (2), sell_button (3), trade_tab (4)
    assert driver.tap.call_count == 4
    assert driver.clear_and_type.call_count == 2
    driver.dismiss_keyboard.assert_called_once()
