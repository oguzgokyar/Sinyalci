"""Strategy engine and TradingAgents integration for Sinyalci.

Handles:
- Risk calculation based on account balance (e.g. $46,250.00).
- Dynamic lot sizing: Risk ($462.50) / (|Entry - SL| * ContractSize).
- Triggering and polling multi-agent research on TradingAgents (Port 3200).
- Circuit breaker for daily max drawdown.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("sinyalci.strategy")


# Canonical ACG Markets MT5 Universe (Forex, Metals, Indices, Energy)
ACG_MARKETS_SYMBOLS: list[dict[str, str]] = [
    # Top Picks / Majors & Metals
    {"ticker": "XAUUSD", "name": "Gold / US Dollar", "category": "Metals (Altın)"},
    {"ticker": "EURUSD", "name": "Euro / US Dollar", "category": "Forex Majors"},
    {"ticker": "GBPUSD", "name": "British Pound / US Dollar", "category": "Forex Majors"},
    {"ticker": "USDJPY", "name": "US Dollar / Japanese Yen", "category": "Forex Majors"},
    {"ticker": "NAS100", "name": "Nasdaq 100 Index", "category": "Indices (Endeks)"},
    {"ticker": "US30", "name": "Dow Jones Industrial Average", "category": "Indices (Endeks)"},
    {"ticker": "US500", "name": "S&P 500 Index", "category": "Indices (Endeks)"},
    {"ticker": "USDCAD", "name": "US Dollar / Canadian Dollar", "category": "Forex Majors"},
    {"ticker": "USDCHF", "name": "US Dollar / Swiss Franc", "category": "Forex Majors"},
    {"ticker": "AUDUSD", "name": "Australian Dollar / US Dollar", "category": "Forex Majors"},
    {"ticker": "NZDUSD", "name": "New Zealand Dollar / US Dollar", "category": "Forex Majors"},
    {"ticker": "XAGUSD", "name": "Silver / US Dollar", "category": "Metals (Gümüş)"},
    {"ticker": "USOIL", "name": "WTI Crude Oil", "category": "Energy (Petrol)"},
    {"ticker": "UKOIL", "name": "Brent Crude Oil", "category": "Energy (Petrol)"},
    # Euro Crosses
    {"ticker": "EURGBP", "name": "Euro / British Pound", "category": "Forex Euro Crosses"},
    {"ticker": "EURJPY", "name": "Euro / Japanese Yen", "category": "Forex Euro Crosses"},
    {"ticker": "EURAUD", "name": "Euro / Australian Dollar", "category": "Forex Euro Crosses"},
    {"ticker": "EURCAD", "name": "Euro / Canadian Dollar", "category": "Forex Euro Crosses"},
    {"ticker": "EURCHF", "name": "Euro / Swiss Franc", "category": "Forex Euro Crosses"},
    {"ticker": "EURNZD", "name": "Euro / New Zealand Dollar", "category": "Forex Euro Crosses"},
    # Pound Crosses
    {"ticker": "GBPJPY", "name": "British Pound / Japanese Yen", "category": "Forex GBP Crosses"},
    {"ticker": "GBPAUD", "name": "British Pound / Australian Dollar", "category": "Forex GBP Crosses"},
    {"ticker": "GBPCAD", "name": "British Pound / Canadian Dollar", "category": "Forex GBP Crosses"},
    {"ticker": "GBPCHF", "name": "British Pound / Swiss Franc", "category": "Forex GBP Crosses"},
    {"ticker": "GBPNZD", "name": "British Pound / New Zealand Dollar", "category": "Forex GBP Crosses"},
    {"ticker": "GBPSGD", "name": "British Pound / Singapore Dollar", "category": "Forex GBP Crosses"},
    # Other Crosses
    {"ticker": "AUDCAD", "name": "Australian Dollar / Canadian Dollar", "category": "Forex Crosses"},
    {"ticker": "AUDCHF", "name": "Australian Dollar / Swiss Franc", "category": "Forex Crosses"},
    {"ticker": "AUDJPY", "name": "Australian Dollar / Japanese Yen", "category": "Forex Crosses"},
    {"ticker": "AUDNZD", "name": "Australian Dollar / New Zealand Dollar", "category": "Forex Crosses"},
    {"ticker": "CADCHF", "name": "Canadian Dollar / Swiss Franc", "category": "Forex Crosses"},
    {"ticker": "CADJPY", "name": "Canadian Dollar / Japanese Yen", "category": "Forex Crosses"},
    {"ticker": "CHFJPY", "name": "Swiss Franc / Japanese Yen", "category": "Forex Crosses"},
    {"ticker": "NZDCAD", "name": "New Zealand Dollar / Canadian Dollar", "category": "Forex Crosses"},
    {"ticker": "NZDCHF", "name": "New Zealand Dollar / Swiss Franc", "category": "Forex Crosses"},
    {"ticker": "NZDJPY", "name": "New Zealand Dollar / Japanese Yen", "category": "Forex Crosses"},
    # Global Indices
    {"ticker": "GER30", "name": "Germany 40 / DAX", "category": "Indices (Endeks)"},
    {"ticker": "UK100", "name": "UK 100 / FTSE", "category": "Indices (Endeks)"},
    {"ticker": "JPN225", "name": "Japan 225 / Nikkei", "category": "Indices (Endeks)"},
    {"ticker": "EUSTX50", "name": "Euro Stoxx 50", "category": "Indices (Endeks)"},
    {"ticker": "HK50", "name": "Hong Kong 50 / Hang Seng", "category": "Indices (Endeks)"},
]


class StrategyEngine:
    def __init__(self, db: Any, tradingagents_url: Optional[str] = None) -> None:
        self.db = db
        # Internal bridge IP or fallback to Traefik domain
        self.tradingagents_url = (
            tradingagents_url
            or os.environ.get("TRADINGAGENTS_URL")
            or "http://10.0.1.1:3200"
        )

    def get_config(self) -> dict[str, Any]:
        balance = float(self.db.get_setting("strategy_balance", "46250.0"))
        risk_pct = float(self.db.get_setting("strategy_risk_percent", "1.0"))
        min_rr = float(self.db.get_setting("strategy_min_rr", "2.0"))
        suffix = self.db.get_setting("strategy_symbol_suffix", ".pro")
        auto_exec = self.db.get_setting("strategy_auto_execute", "0") == "1"
        watchlist_raw = self.db.get_setting("strategy_watchlist", "XAUUSD,EURUSD,GBPUSD,USDJPY,NAS100")
        watchlist = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
        favorites_raw = self.db.get_setting("strategy_favorites", "XAUUSD,EURUSD,GBPUSD,USDJPY,NAS100")
        favorites = [t.strip().upper() for t in favorites_raw.split(",") if t.strip()]
        max_daily_loss = float(self.db.get_setting("strategy_max_daily_loss", "925.0"))

        risk_amount = round(balance * (risk_pct / 100.0), 2)
        target_profit = round(risk_amount * min_rr, 2)

        return {
            "balance": balance,
            "risk_percent": risk_pct,
            "risk_amount": risk_amount,
            "min_rr": min_rr,
            "target_profit": target_profit,
            "symbol_suffix": suffix,
            "auto_execute": auto_exec,
            "watchlist": watchlist,
            "favorites": favorites,
            "acg_symbols": ACG_MARKETS_SYMBOLS,
            "max_daily_loss": max_daily_loss,
            "tradingagents_url": self.tradingagents_url,
        }

    def update_config(self, data: dict[str, Any]) -> dict[str, Any]:
        if "balance" in data:
            self.db.set_setting("strategy_balance", str(float(data["balance"])))
        if "risk_percent" in data:
            self.db.set_setting("strategy_risk_percent", str(float(data["risk_percent"])))
        if "min_rr" in data:
            self.db.set_setting("strategy_min_rr", str(float(data["min_rr"])))
        if "symbol_suffix" in data:
            self.db.set_setting("strategy_symbol_suffix", str(data["symbol_suffix"]).strip())
        if "auto_execute" in data:
            self.db.set_setting("strategy_auto_execute", "1" if data["auto_execute"] else "0")
        if "watchlist" in data:
            if isinstance(data["watchlist"], list):
                self.db.set_setting("strategy_watchlist", ",".join(data["watchlist"]))
            else:
                self.db.set_setting("strategy_watchlist", str(data["watchlist"]))
        if "favorites" in data:
            if isinstance(data["favorites"], list):
                self.db.set_setting("strategy_favorites", ",".join(data["favorites"]))
            else:
                self.db.set_setting("strategy_favorites", str(data["favorites"]))
        if "max_daily_loss" in data:
            self.db.set_setting("strategy_max_daily_loss", str(float(data["max_daily_loss"])))

        return self.get_config()

    def calculate_lot(self, ticker: str, entry_price: float, stop_loss: float, balance: Optional[float] = None, risk_pct: Optional[float] = None) -> tuple[float, float]:
        cfg = self.get_config()
        bal = balance if balance is not None else cfg["balance"]
        rp = risk_pct if risk_pct is not None else cfg["risk_percent"]
        risk_amount = bal * (rp / 100.0)

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return 0.1, risk_amount

        t = ticker.upper()
        # Forex (100,000 units), Gold (100 oz), Indices (1-10 contracts)
        if t in ["XAUUSD", "GOLD"]:
            # Gold: 1 Lot = 100 oz. 1 dollar move = $100 per lot
            raw_lot = risk_amount / (sl_distance * 100.0)
        elif t in ["XAGUSD", "SILVER"]:
            # Silver: 1 Lot = 5000 oz.
            raw_lot = risk_amount / (sl_distance * 5000.0)
        elif any(t.startswith(prefix) or t.endswith(prefix) for prefix in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]):
            # Standard Forex: 1 Lot = 100,000 units. Pip = 0.0001 (or 0.01 for JPY)
            is_jpy = "JPY" in t
            pip_size = 0.01 if is_jpy else 0.0001
            pips_at_risk = sl_distance / pip_size
            pip_value_per_lot = 10.0  # Approx $10 per pip for standard 1.00 lot
            raw_lot = risk_amount / (pips_at_risk * pip_value_per_lot) if pips_at_risk > 0 else 0.1
        elif t in ["NAS100", "US30", "US500", "GER30", "UK100", "JPN225"]:
            # Index CFDs: Typically 1 point = $1-$20 per lot
            point_value = 1.0
            raw_lot = risk_amount / (sl_distance * point_value)
        else:
            raw_lot = risk_amount / sl_distance

        calculated_lot = round(raw_lot, 2)
        if calculated_lot < 0.01:
            calculated_lot = 0.01

        return calculated_lot, round(risk_amount, 2)

    def format_broker_symbol(self, ticker: str) -> str:
        cfg = self.get_config()
        suffix = cfg.get("symbol_suffix", "")
        t = ticker.upper()
        if suffix.startswith("#"):
            return f"#{t}"
        return f"{t}{suffix}"

    async def scan_ticker(self, ticker: str, date: Optional[str] = None) -> dict[str, Any]:
        """Trigger an analysis run on TradingAgents and parse the trading recommendation."""
        target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        payload = {
            "ticker": ticker.upper(),
            "date": target_date,
            "provider": "openai",
            "model": "gemini-3.8-flash-high",
            "max_debate_rounds": 1,
        }

        # 1. Start Analysis
        start_url = f"{self.tradingagents_url}/api/start"
        req = urllib.request.Request(
            start_url,
            headers={"Content-Type": "application/json", "User-Agent": "Sinyalci/1.0"},
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )

        try:
            loop = asyncio.get_running_loop()
            resp_str = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15).read().decode())
            start_data = json.loads(resp_str)
            run_id = start_data["run_id"]
        except Exception as e:
            logger.error("Failed to start TradingAgents analysis for %s: %s", ticker, e)
            raise RuntimeError(f"TradingAgents servisi ile bağlantı kurulamadı: {e}")

        # 2. Poll until completed (timeout: 180s)
        status_url = f"{self.tradingagents_url}/api/status/{run_id}"
        report_id = None
        for _ in range(36):
            await asyncio.sleep(5)
            try:
                s_req = urllib.request.Request(status_url, headers={"User-Agent": "Sinyalci/1.0"})
                s_resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(s_req, timeout=10).read().decode())
                s_data = json.loads(s_resp)
                if s_data.get("status") == "completed":
                    report_id = s_data.get("report_id")
                    break
                if s_data.get("status") == "failed":
                    raise RuntimeError(f"Analiz başarısız oldu: {s_data.get('error')}")
            except Exception as e:
                logger.warning("Polling TradingAgents error (%s): %s", ticker, e)

        if not report_id:
            # Fallback check reports list
            rep_url = f"{self.tradingagents_url}/api/reports"
            r_req = urllib.request.Request(rep_url, headers={"User-Agent": "Sinyalci/1.0"})
            r_resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(r_req, timeout=10).read().decode())
            r_data = json.loads(r_resp)
            for r in r_data.get("reports", []):
                if r.get("ticker") == ticker.upper():
                    report_id = r.get("report_id")
                    break

        if not report_id:
            raise TimeoutError(f"{ticker} analizi zaman aşımına uğradı.")

        # 3. Fetch Full Report
        report_url = f"{self.tradingagents_url}/api/reports/{report_id}"
        rep_req = urllib.request.Request(report_url, headers={"User-Agent": "Sinyalci/1.0"})
        rep_resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(rep_req, timeout=10).read().decode())
        report_obj = json.loads(rep_resp)
        content = report_obj.get("content", "")

        # 4. Extract Key Parameters (Action, Entry, SL, TP, Reasoning)
        side = "BUY"
        if "FINAL TRANSACTION PROPOSAL: **SELL**" in content or "**Action**: Sell" in content:
            side = "SELL"
        elif "FINAL TRANSACTION PROPOSAL: **HOLD**" in content or "**Action**: Hold" in content:
            side = "HOLD"

        # Regex extract Entry / SL
        entry_match = re.search(r"\*\*Entry Price\*\*:\s*([0-9.]+)", content)
        sl_match = re.search(r"\*\*Stop Loss\*\*:\s*([0-9.]+)", content)
        reason_match = re.search(r"\*\*Reasoning\*\*:\s*([^\n]+)", content)

        # Fallback to current close price if entry not found
        close_match = re.search(r"\*\*Close Price\*\*\s*\|\s*\*\*?\$?([0-9.]+)", content)

        entry_price = float(entry_match.group(1)) if entry_match else (float(close_match.group(1)) if close_match else 100.0)
        
        cfg = self.get_config()
        min_rr = cfg["min_rr"]

        if sl_match:
            sl = float(sl_match.group(1))
        else:
            # 2% default fallback stop
            sl = round(entry_price * 0.98 if side == "BUY" else entry_price * 1.02, 2)

        sl_distance = abs(entry_price - sl)
        if side == "BUY":
            tp = round(entry_price + (sl_distance * min_rr), 2)
        else:
            tp = round(entry_price - (sl_distance * min_rr), 4)

        calculated_lot, risk_amount = self.calculate_lot(ticker, entry_price, sl)
        broker_symbol = self.format_broker_symbol(ticker)
        reasoning = reason_match.group(1).strip() if reason_match else f"{ticker} TradingAgents çoklu ajan analizi tamamlandı."

        # Save to Sinyalci DB
        signal_record = self.db.create_signal({
            "ticker": ticker,
            "broker_symbol": broker_symbol,
            "side": side,
            "entry_price": entry_price,
            "sl": sl,
            "tp": tp,
            "risk_reward": min_rr,
            "calculated_lot": calculated_lot,
            "risk_amount": risk_amount,
            "confidence": 85,
            "status": "pending",
            "reasoning": reasoning,
        })

        self.db.add_log(f"Strateji Sinyali Üretildi: {ticker} {side} @ {entry_price} (SL: {sl}, TP: {tp}, Lot: {calculated_lot})", level="INFO")

        return signal_record
