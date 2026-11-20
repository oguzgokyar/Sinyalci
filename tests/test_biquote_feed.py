import sys
import unittest
from pathlib import Path

# Ensure src is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from usb_trader.core.strategy_engine import StrategyEngine, to_biquote_ticker


class TestBiquoteFeed(unittest.TestCase):
    def test_biquote_ticker_mapping(self):
        self.assertEqual(to_biquote_ticker("XAUUSD"), "XAUUSD")
        self.assertEqual(to_biquote_ticker("XAUUSD.PRO"), "XAUUSD")
        self.assertEqual(to_biquote_ticker("NAS100"), "USTEC")
        self.assertEqual(to_biquote_ticker("NAS100.PRO"), "USTEC")
        self.assertEqual(to_biquote_ticker("US30"), "US30")
        self.assertEqual(to_biquote_ticker("GER30"), "DE30")
        self.assertEqual(to_biquote_ticker("EURUSD"), "EURUSD")
        self.assertEqual(to_biquote_ticker("#USOIL"), "USOIL")

    def test_biquote_fetch_quote(self):
        class DummyDB:
            def get_setting(self, k, d=""):
                return d

        engine = StrategyEngine(DummyDB())
        res = engine.fetch_biquote_chart("XAUUSD")
        self.assertIsNotNone(res)
        self.assertGreater(res["price"], 0)
        self.assertEqual(res["symbol"], "XAUUSD")


if __name__ == "__main__":
    unittest.main()
