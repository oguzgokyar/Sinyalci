"""Safety circuit breaker with signal idempotency and popup kill-switch."""

from usb_trader.vision.state_machine import MTState


class ExecutionAbortedError(RuntimeError):
    """Raised whenever the safety circuit breaker blocks or halts execution."""


class CircuitBreaker:
    def __init__(self) -> None:
        self._processed_ids: set[str] = set()
        self._tripped = False
        self._trip_reason: str = ""

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    def claim_signal(self, idempotency_key: str) -> bool:
        if idempotency_key in self._processed_ids:
            return False
        self._processed_ids.add(idempotency_key)
        return True

    def trigger_kill_switch(self, reason: str) -> None:
        self._tripped = True
        self._trip_reason = reason

    def reset(self) -> None:
        self._tripped = False
        self._trip_reason = ""

    def assert_safe(self, current_state: MTState) -> None:
        if self._tripped:
            raise ExecutionAbortedError(f"Kill-switch active: {self._trip_reason}")
        if current_state == MTState.POPUP_ERROR:
            self.trigger_kill_switch("Unexpected popup / requote detected on screen")
            raise ExecutionAbortedError(self._trip_reason)
