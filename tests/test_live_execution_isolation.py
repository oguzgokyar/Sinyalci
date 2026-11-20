import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Mock cv2 and numpy if not available locally
if "cv2" not in sys.modules:
    sys.modules["cv2"] = MagicMock()
if "numpy" not in sys.modules:
    sys.modules["numpy"] = MagicMock()

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from api.device_manager import DeviceManager


class TestLiveExecutionIsolation(unittest.TestCase):
    def test_execute_order_does_not_intercept_as_dry_run(self):
        db = MagicMock()
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        db.get_order.return_value = {
            "id": 1,
            "device_id": 1,
            "account_id": 1,
            "status": "queued",
            "symbol": "EURUSD.PRO",
            "side": "BUY",
            "lot": 0.1,
            "idempotency_key": "test-key-1",
        }
        db.get_setting.return_value = "0"  # kill switch 0
        db.get_account.return_value = {
            "id": 1,
            "enabled": True,
            "max_lot": 5.0,
            "daily_max_orders": 100,
        }
        db.count_today_orders.return_value = 0

        dm = DeviceManager(db, ws)
        # Verify execute_order_async attempts to get device rather than returning dry_run=True
        with patch.object(dm.db, "get_device", side_effect=RuntimeError("Device reached")):
            import asyncio

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(dm.execute_order_async(1))
            self.assertIn("Device reached", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
