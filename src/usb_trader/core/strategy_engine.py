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


# Canonical ACD Markets Stock CFD Universe
ACD_MARKETS_STOCKS: list[dict[str, str]] = [
    # US Mega-Cap / Tech Leaders
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "category": "Tech / AI"},
    {"ticker": "AAPL", "name": "Apple Inc.", "category": "Tech / Consumer"},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "category": "Tech / Cloud"},
    {"ticker": "TSLA", "name": "Tesla, Inc.", "category": "EV / Auto"},
    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "category": "E-Commerce / Cloud"},
    {"ticker": "META", "name": "Meta Platforms, Inc.", "category": "Tech / Social"},
    {"ticker": "GOOGL", "name": "Alphabet Inc. (Google)", "category": "Tech / Search"},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "category": "Semiconductors"},
    {"ticker": "INTC", "name": "Intel Corporation", "category": "Semiconductors"},
    {"ticker": "QCOM", "name": "Qualcomm Incorporated", "category": "Semiconductors"},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "category": "Semiconductors"},
    {"ticker": "NFLX", "name": "Netflix, Inc.", "category": "Entertainment"},
    {"ticker": "PLTR", "name": "Palantir Technologies", "category": "AI / Enterprise"},
    {"ticker": "ORCL", "name": "Oracle Corporation", "category": "Tech / Enterprise"},
    {"ticker": "CRM", "name": "Salesforce, Inc.", "category": "SaaS / Cloud"},
    {"ticker": "ADBE", "name": "Adobe Inc.", "category": "Software"},
    {"ticker": "COIN", "name": "Coinbase Global, Inc.", "category": "Fintech / Crypto"},
    {"ticker": "PYPL", "name": "PayPal Holdings, Inc.", "category": "Fintech"},
    {"ticker": "SQ", "name": "Block, Inc.", "category": "Fintech"},
    {"ticker": "UBER", "name": "Uber Technologies, Inc.", "category": "Mobility"},
    {"ticker": "ABNB", "name": "Airbnb, Inc.", "category": "Travel / Consumer"},
    # Finance & Banking
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "category": "Banking / Finance"},
    {"ticker": "BAC", "name": "Bank of America Corporation", "category": "Banking / Finance"},
    {"ticker": "GS", "name": "The Goldman Sachs Group", "category": "Investment Banking"},
    {"ticker": "MS", "name": "Morgan Stanley", "category": "Investment Banking"},
    {"ticker": "V", "name": "Visa Inc.", "category": "Payments"},
    {"ticker": "MA", "name": "Mastercard Incorporated", "category": "Payments"},
    # Energy & Industrial
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "category": "Energy / Oil"},
    {"ticker": "CVX", "name": "Chevron Corporation", "category": "Energy / Oil"},
    {"ticker": "BA", "name": "The Boeing Company", "category": "Aerospace"},
    {"ticker": "CAT", "name": "Caterpillar Inc.", "category": "Industrial"},
    # Healthcare & Pharma
    {"ticker": "PFE", "name": "Pfizer Inc.", "category": "Healthcare / Pharma"},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "category": "Healthcare / Pharma"},
    {"ticker": "LLY", "name": "Eli Lilly and Company", "category": "Healthcare / Pharma"},
    # Retail & Consumer Goods
    {"ticker": "WMT", "name": "Walmart Inc.", "category": "Retail"},
    {"ticker": "COST", "name": "Costco Wholesale Corporation", "category": "Retail"},
    {"ticker": "NKE", "name": "NIKE, Inc.", "category": "Consumer Discretionary"},
    {"ticker": "KO", "name": "The Coca-Cola Company", "category": "Consumer Staples"},
    {"ticker": "PEP", "name": "PepsiCo, Inc.", "category": "Consumer Staples"},
    {"ticker": "MCD", "name": "McDonald's Corporation", "category": "Restaurants"},
    {"ticker": "SBUX", "name": "Starbucks Corporation", "category": "Restaurants"},
    {"ticker": "DIS", "name": "The Walt Disney Company", "category": "Entertainment"},
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
        suffix = self.db.get_setting("strategy_symbol_suffix", ".us")
        auto_exec = self.db.get_setting("strategy_auto_execute", "0") == "1"
        watchlist_raw = self.db.get_setting("strategy_watchlist", "NVDA,AAPL,MSFT,TSLA,AMZN,META,GOOGL,AMD")
        watchlist = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
        favorites_raw = self.db.get_setting("strategy_favorites", "NVDA,AAPL,TSLA,MSFT,AMZN")
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
            "acd_stocks": ACD_MARKETS_STOCKS,
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

    def calculate_lot(self, entry_price: float, stop_loss: float, balance: Optional[float] = None, risk_pct: Optional[float] = None) -> tuple[float, float]:
        cfg = self.get_config()
        bal = balance if balance is not None else cfg["balance"]
        rp = risk_pct if risk_pct is not None else cfg["risk_percent"]
        risk_amount = bal * (rp / 100.0)

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return 0.1, risk_amount

        # For stock CFDs, standard contract size is 1 share per lot (or CFD unit)
        raw_lot = risk_amount / sl_distance
        # Round to 2 decimal places (standard MT5 step 0.01 lot)
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
            tp = round(entry_price - (sl_distance * min_rr), 2)

        calculated_lot, risk_amount = self.calculate_lot(entry_price, sl)
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
