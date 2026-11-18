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
    assert driver.tap.call_count == 2  # lot field + BUY button
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
