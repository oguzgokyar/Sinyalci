import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from usb_trader.core.strategy_engine import StrategyEngine


@pytest.mark.anyio
async def test_paper_close_triggers_live_device_close():
    db = MagicMock()
    # Mock an open paper position that hits TP
    db.list_paper_positions.return_value = [
        {
            "id": 42,
            "signal_id": 101,
            "symbol": "XAUUSD.PRO",
            "side": "BUY",
            "lot": 0.15,
            "entry_price": 3700.0,
            "current_price": 3720.0,
            "sl": 3680.0,
            "tp": 3720.0,
            "risk_amount": 462.5,
            "pnl": 300.0,
            "status": "open",
        }
    ]
    db.close_paper_position.return_value = {
        "id": 42,
        "symbol": "XAUUSD.PRO",
        "status": "closed_tp",
    }
    # Mock matching active order
    db.list_orders.return_value = [
        {
            "id": 999,
            "device_id": 1,
            "symbol": "XAUUSD.PRO",
            "status": "filled",
        }
    ]

    engine = StrategyEngine(db=db)
    engine.dm = MagicMock()
    engine.dm.close_position_async = AsyncMock(return_value={"status": "closed"})

    # Mock market chart feed returning price at TP
    setattr(engine, "get_market_chart", MagicMock(return_value={"price": 3725.0}))

    updated = await engine.update_live_paper_positions()
    assert len(updated) == 1
    assert updated[0]["status"] == "closed_tp"

    # Give any spawned async task a microsecond to dispatch
    await asyncio.sleep(0.01)
    engine.dm.close_position_async.assert_called_once_with(1, symbol="XAUUSD.PRO")
