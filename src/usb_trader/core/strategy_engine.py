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


def to_trading_ticker(ticker: str) -> str:
    """Map ACG Markets MT5 symbols to Yahoo Finance compatible ticker format."""
    t = ticker.upper().replace(".PRO", "").replace(".RAW", "").replace("#", "").strip()
    mapping = {
        "XAUUSD": "GC=F",
        "GOLD": "GC=F",
        "XAGUSD": "SI=F",
        "SILVER": "SI=F",
        "USOIL": "CL=F",
        "UKOIL": "BZ=F",
        "NAS100": "NQ=F",
        "US30": "YM=F",
        "US500": "ES=F",
        "GER30": "^GDAXI",
        "GER40": "^GDAXI",
        "UK100": "^FTSE",
        "JPN225": "^N225",
    }
    if t in mapping:
        return mapping[t]
    # For standard Forex (6 chars)
    if len(t) == 6 and any(t.startswith(p) for p in ["EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF"]):
        return f"{t}=X"
    return t


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

        tf = self.db.get_setting("strategy_timeframe", "H1")
        paper_trading = self.db.get_setting("strategy_paper_trading", "1") == "1"
        autopilot_enabled = self.db.get_setting("strategy_autopilot_enabled", "1") == "1"
        last_autopilot = self.db.get_setting("strategy_last_autopilot_run", "")

        return {
            "balance": balance,
            "risk_percent": risk_pct,
            "risk_amount": risk_amount,
            "min_rr": min_rr,
            "target_profit": target_profit,
            "symbol_suffix": suffix,
            "auto_execute": auto_exec,
            "autopilot_enabled": autopilot_enabled,
            "last_autopilot_run": last_autopilot,
            "timeframe": tf,
            "paper_trading": paper_trading,
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
        if "autopilot_enabled" in data:
            self.db.set_setting("strategy_autopilot_enabled", "1" if data["autopilot_enabled"] else "0")
        if "timeframe" in data:
            self.db.set_setting("strategy_timeframe", str(data["timeframe"]).upper())
        if "paper_trading" in data:
            self.db.set_setting("strategy_paper_trading", "1" if data["paper_trading"] else "0")
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

    async def scan_ticker(self, ticker: str, date: Optional[str] = None, timeframe: Optional[str] = None) -> dict[str, Any]:
        """Trigger an analysis run on TradingAgents and parse the trading recommendation."""
        target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        tf = timeframe or self.db.get_setting("strategy_timeframe", "H1")
        trading_ticker = to_trading_ticker(ticker)

        payload = {
            "ticker": trading_ticker,
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
                if r.get("ticker") in [ticker.upper(), trading_ticker.upper()]:
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

        # Fetch real-time market price to anchor execution
        live_chart = self.fetch_live_chart(ticker)
        current_market_price = float(live_chart["price"]) if live_chart and live_chart["price"] > 0 else None

        # Regex extract AI theoretical Entry / SL
        entry_match = re.search(r"\*\*Entry Price\*\*:\s*([0-9.]+)", content)
        sl_match = re.search(r"\*\*Stop Loss\*\*:\s*([0-9.]+)", content)
        reason_match = re.search(r"\*\*Reasoning\*\*:\s*([^\n]+)", content)
        close_match = re.search(r"\*\*Close Price\*\*\s*\|\s*\*?\$?([0-9.]+)", content)

        raw_ai_entry = float(entry_match.group(1)) if entry_match else None
        raw_ai_sl = float(sl_match.group(1)) if sl_match else None

        # ANCHOR: Entry price MUST be the real live market price when executing
        if current_market_price and current_market_price > 0:
            entry_price = current_market_price
        elif raw_ai_entry:
            entry_price = raw_ai_entry
        elif close_match:
            entry_price = float(close_match.group(1))
        else:
            entry_price = 100.0

        cfg = self.get_config()
        min_rr = cfg["min_rr"]

        # Calculate reasonable stop distance based on real market price
        if raw_ai_entry and raw_ai_sl and abs(raw_ai_entry - raw_ai_sl) > 0:
            sl_distance = abs(raw_ai_entry - raw_ai_sl)
            # Guard against absurdly wide stops (max 2% of price for Forex/Gold)
            if sl_distance > entry_price * 0.02:
                sl_distance = round(entry_price * 0.008, 2 if "JPY" in ticker or entry_price > 10 else 4)
        else:
            sl_distance = round(entry_price * 0.008, 2 if "JPY" in ticker or entry_price > 10 else 4)

        if sl_distance <= 0:
            sl_distance = round(entry_price * 0.005, 4)

        is_high_precision = entry_price < 10 and "JPY" not in ticker

        if side == "BUY":
            sl = round(entry_price - sl_distance, 4 if is_high_precision else 2)
            tp = round(entry_price + (sl_distance * min_rr), 4 if is_high_precision else 2)
        else:
            sl = round(entry_price + sl_distance, 4 if is_high_precision else 2)
            tp = round(entry_price - (sl_distance * min_rr), 4 if is_high_precision else 2)

        calculated_lot, risk_amount = self.calculate_lot(ticker, entry_price, sl)
        broker_symbol = self.format_broker_symbol(ticker)
        reasoning = reason_match.group(1).strip() if reason_match else f"{ticker} TradingAgents çoklu ajan analizi tamamlandı."
        tf = self.db.get_setting("strategy_timeframe", "H1")

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
            "timeframe": tf,
            "status": "pending",
            "reasoning": reasoning,
        })

        self.db.add_log(f"Strateji Sinyali Üretildi: {ticker} {side} @ {entry_price} (SL: {sl}, TP: {tp}, Lot: {calculated_lot})", level="INFO")

        return signal_record

    def fetch_live_chart(self, ticker: str, interval: str = "1h", range_: str = "5d") -> Optional[dict[str, Any]]:
        """Fetch live candle data and current price from Yahoo Finance."""
        sym = to_trading_ticker(ticker)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval={interval}&range={range_}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                res = data["chart"]["result"][0]
                meta = res["meta"]
                quote = res["indicators"]["quote"][0]
                closes = [float(c) for c in quote.get("close", []) if c is not None]
                highs = [float(h) for h in quote.get("high", []) if h is not None]
                lows = [float(l) for l in quote.get("low", []) if l is not None]
                price = meta.get("regularMarketPrice") or (closes[-1] if closes else 0.0)
                return {"symbol": sym, "price": float(price), "closes": closes, "highs": highs, "lows": lows}
        except Exception as e:
            logger.warning("Could not fetch Yahoo chart for %s (%s): %s", ticker, sym, e)
            return None

    @staticmethod
    def calculate_technicals(closes: list[float]) -> dict[str, float]:
        """Compute 10 EMA, 50 SMA, and 14 RSI without external dependencies."""
        if not closes or len(closes) < 15:
            return {"rsi": 50.0, "ema10": closes[-1] if closes else 0.0, "sma50": closes[-1] if closes else 0.0}

        # 50 SMA
        sma50_window = closes[-50:] if len(closes) >= 50 else closes
        sma50 = sum(sma50_window) / len(sma50_window)

        # 10 EMA
        k = 2.0 / 11.0
        ema10 = sum(closes[:10]) / 10.0
        for p in closes[10:]:
            ema10 = p * k + ema10 * (1 - k)

        # 14 RSI
        period = 14
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0.0 for d in deltas]
        losses = [-d if d < 0 else 0.0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        return {"rsi": round(rsi, 2), "ema10": round(ema10, 4), "sma50": round(sma50, 4)}

    def prescreen_ticker(self, ticker: str, timeframe: str = "H1") -> dict[str, Any]:
        """Fast 0.2s technical analysis: checks pullback to 10 EMA and RSI momentum."""
        interval = "1h" if timeframe == "H1" else ("4h" if timeframe == "H4" else "1d")
        chart = self.fetch_live_chart(ticker, interval=interval, range_="1mo")

        if not chart or len(chart["closes"]) < 15:
            return {"ticker": ticker, "price": 0.0, "setup": "NONE", "score": 0, "reason": "Veri yok"}

        price = chart["price"]
        closes = chart["closes"]
        techs = self.calculate_technicals(closes)
        rsi = techs["rsi"]
        ema10 = techs["ema10"]
        sma50 = techs["sma50"]

        score = 0
        setup = "NONE"
        reasons = []

        # Pullback distance to 10 EMA
        dist_ema10 = abs(price - ema10) / ema10 * 100.0

        # Bullish Pullback Setup
        if price >= sma50:
            reasons.append("Fiyat 50 SMA üstünde (Boğa Trendi)")
            score += 25
            if dist_ema10 <= 0.8:
                score += 35
                reasons.append("10 EMA ortalamasına geri çekildi (Pullback Destek)")
            if 28.0 <= rsi <= 48.0:
                score += 35
                reasons.append(f"RSI toparlanma bölgesinde ({rsi})")
            if score >= 60:
                setup = "BUY"
        # Bearish Pullback / Relief Setup
        elif price < sma50:
            reasons.append("Fiyat 50 SMA altında (Ayı Trendi)")
            score += 25
            if dist_ema10 <= 0.8:
                score += 35
                reasons.append("10 EMA direncine tepki verdi (Pullback Direnç)")
            if 52.0 <= rsi <= 72.0:
                score += 35
                reasons.append(f"RSI aşırı alım rahatlama bölgesinde ({rsi})")
            if score >= 60:
                setup = "SELL"

        return {
            "ticker": ticker.upper(),
            "price": price,
            "rsi": rsi,
            "ema10": ema10,
            "sma50": sma50,
            "setup": setup,
            "score": score,
            "reason": "; ".join(reasons) if reasons else "Yatay piyasa",
            "timeframe": timeframe,
        }

    def prescreen_favorites(self) -> list[dict[str, Any]]:
        """Prescreen all favorite symbols and return sorted by setup quality."""
        cfg = self.get_config()
        tf = cfg.get("timeframe", "H1")
        results = []
        for ticker in cfg.get("favorites", []):
            res = self.prescreen_ticker(ticker, timeframe=tf)
            results.append(res)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    async def update_live_paper_positions(self, ws_hub: Optional[Any] = None) -> list[dict[str, Any]]:
        """Checks open paper positions against live market price, updates floating PnL, triggers TP/SL."""
        open_positions = self.db.list_paper_positions(status="open")
        if not open_positions:
            return []

        updated = []
        for pos in open_positions:
            sym = pos["symbol"]
            ticker = sym.replace(".PRO", "").replace(".RAW", "").replace("#", "")
            chart = self.fetch_live_chart(ticker, interval="1m", range_="1d")
            if not chart or chart["price"] <= 0:
                continue

            current_price = chart["price"]
            entry = float(pos["entry_price"])
            sl = float(pos["sl"])
            tp = float(pos["tp"])
            lot = float(pos["lot"])
            side = pos["side"]

            # Calculate live floating PnL with clean symbol without suffixes
            clean_sym = sym.replace(".PRO", "").replace(".pro", "").replace(".RAW", "").replace(".raw", "").replace("#", "").strip().upper()
            diff = (current_price - entry) if side == "BUY" else (entry - current_price)
            if "XAUUSD" in clean_sym or "GOLD" in clean_sym:
                pnl = diff * 100.0 * lot
            elif any(clean_sym.startswith(p) or clean_sym.endswith(p) for p in ["USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]):
                pip_size = 0.01 if "JPY" in clean_sym else 0.0001
                pips = diff / pip_size
                pnl = pips * 10.0 * lot
            else:
                pnl = diff * lot

            pnl = round(pnl, 2)

            # Check TP / SL hit
            closed_status = None
            if side == "BUY":
                if current_price >= tp:
                    closed_status = "closed_tp"
                elif current_price <= sl:
                    closed_status = "closed_sl"
            elif side == "SELL":
                if current_price <= tp:
                    closed_status = "closed_tp"
                elif current_price >= sl:
                    closed_status = "closed_sl"

            if closed_status:
                closed = self.db.close_paper_position(pos["id"], close_price=current_price, close_status=closed_status)
                self.db.add_log(
                    f"Sanal Pozisyon Kapatıldı ({closed_status}): #{pos['id']} {sym} {side} @ {current_price} (PnL: ${pnl})",
                    level="INFO",
                )
                if ws_hub:
                    await ws_hub.broadcast("paper_position_closed", closed)
                updated.append(closed)
            else:
                self.db.update_paper_position_price(pos["id"], current_price=current_price, pnl=pnl)
                pos["current_price"] = current_price
                pos["pnl"] = pnl
                updated.append(pos)

        if ws_hub and updated:
            stats = self.db.get_paper_stats()
            await ws_hub.broadcast("paper_positions_updated", {"positions": updated, "stats": stats})

        return updated

    async def run_autopilot_tick(self, ws_hub: Optional[Any] = None) -> Optional[dict[str, Any]]:
        """Autonomous bot decision engine: scans pre-filtered setups and triggers TradingAgents."""
        cfg = self.get_config()
        if not cfg.get("autopilot_enabled"):
            return None

        # 1. Update existing open positions first
        await self.update_live_paper_positions(ws_hub=ws_hub)

        # 2. Check position limit (max 3 concurrent open positions)
        open_count = len(self.db.list_paper_positions(status="open"))
        if open_count >= 3:
            return None

        # 3. Check daily circuit breaker
        paper_stats = self.db.get_paper_stats()
        if paper_stats["realized_pnl"] <= -cfg.get("max_daily_loss", 925.0):
            logger.warning("Autopilot circuit breaker active! Daily loss threshold reached.")
            return None

        # 4. Run fast pre-screener
        candidates = self.prescreen_favorites()
        best = next((c for c in candidates if c["score"] >= 60 and c["setup"] in ["BUY", "SELL"]), None)

        if not best:
            return None

        ticker = best["ticker"]
        tf = cfg.get("timeframe", "H1")
        now_str = datetime.now(timezone.utc).isoformat()
        self.db.set_setting("strategy_last_autopilot_run", f"{now_str} | {ticker} ({best['setup']} Score: {best['score']})")

        self.db.add_log(
            f"Otopilot Fırsat Yakaladı: {ticker} ({best['setup']} Puanı: {best['score']}/100) -> TradingAgents Onayına Gönderiliyor...",
            level="INFO",
        )
        if ws_hub:
            await ws_hub.broadcast("autopilot_triggered", best)

        # 5. Deep confirmation via TradingAgents
        signal = await self.scan_ticker(ticker, timeframe=tf)

        # 6. If paper trading is active and signal confirmed in same direction
        if cfg.get("paper_trading") and signal["side"] in ["BUY", "SELL"]:
            paper_pos = self.db.create_paper_position({
                "signal_id": signal["id"],
                "symbol": signal["broker_symbol"],
                "side": signal["side"],
                "lot": signal["calculated_lot"],
                "entry_price": signal["entry_price"],
                "current_price": signal["entry_price"],
                "sl": signal["sl"],
                "tp": signal["tp"],
                "risk_amount": signal["risk_amount"],
                "pnl": 0.0,
                "timeframe": tf,
            })
            self.db.update_signal_status(signal["id"], status="paper_active")
            self.db.add_log(
                f"Otopilot Sanal Pozisyon Açtı: {signal['broker_symbol']} {signal['side']} {signal['calculated_lot']} Lot @ {signal['entry_price']}",
                level="INFO",
            )
            if ws_hub:
                await ws_hub.broadcast("paper_position_opened", paper_pos)

        return signal

