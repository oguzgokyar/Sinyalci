import pytest
from usb_trader.core.circuit_breaker import CircuitBreaker, ExecutionAbortedError
from usb_trader.vision.state_machine import MTState


def test_idempotency_blocks_duplicate_signal():
    cb = CircuitBreaker()
    assert cb.claim_signal("ord-001") is True
    assert cb.claim_signal("ord-001") is False


def test_circuit_breaker_trips_on_popup_or_kill_switch():
    cb = CircuitBreaker()
    with pytest.raises(ExecutionAbortedError):
        cb.assert_safe(MTState.POPUP_ERROR)
    assert cb.is_tripped is True

    cb.reset()
    assert cb.is_tripped is False
    cb.trigger_kill_switch("Manual emergency stop")
    with pytest.raises(ExecutionAbortedError):
        cb.assert_safe(MTState.ORDER_FORM)
