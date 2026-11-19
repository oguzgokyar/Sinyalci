"""Strategy & Signals API endpoints."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

from usb_trader.core.strategy_engine import StrategyEngine, to_trading_ticker

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class StrategyConfigUpdate(BaseModel):
    balance: Optional[float] = None
    risk_percent: Optional[float] = None
    min_rr: Optional[float] = None
    symbol_suffix: Optional[str] = None
    auto_execute: Optional[bool] = None
    timeframe: Optional[str] = None
    paper_trading: Optional[bool] = None
    autopilot_enabled: Optional[bool] = None
    watchlist: Optional[list[str]] = None
    favorites: Optional[list[str]] = None
    max_daily_loss: Optional[float] = None


class ScanRequest(BaseModel):
    ticker: str
    date: Optional[str] = None
    timeframe: Optional[str] = None


class ClosePaperRequest(BaseModel):
    close_price: Optional[float] = None
    status: Optional[str] = "closed_manual"


def get_engine(request: Request) -> StrategyEngine:
    db = request.app.state.db
    return StrategyEngine(db)


@router.get("/config")
async def get_strategy_config(request: Request):
    engine = get_engine(request)
    return engine.get_config()


@router.post("/config")
async def update_strategy_config(payload: StrategyConfigUpdate, request: Request):
    engine = get_engine(request)
    updated = engine.update_config(payload.model_dump(exclude_unset=True))
    # Broadcast to web clients
    ws_hub = request.app.state.ws
    await ws_hub.broadcast("strategy_config_updated", updated)
    return updated


@router.get("/prescreen")
async def prescreen_favorites(request: Request):
    """Fast technical prescreen of all favorites without triggering TradingAgents."""
    engine = get_engine(request)
    candidates = engine.prescreen_favorites()
    return {"candidates": candidates}


@router.post("/autopilot/run-now")
async def run_autopilot_now(request: Request, background_tasks: BackgroundTasks):
    """Trigger an immediate autopilot tick in the background."""
    engine = get_engine(request)
    ws_hub = request.app.state.ws
    background_tasks.add_task(engine.run_autopilot_tick, ws_hub=ws_hub)
    return {"status": "triggered", "message": "Otopilot döngüsü anlık tetiklendi."}


@router.get("/signals")
async def list_signals(request: Request, limit: int = 50):
    db = request.app.state.db
    signals = db.list_signals(limit=limit)
    stats = db.get_today_signal_stats()
    return {"signals": signals, "stats": stats}


@router.get("/paper-trades")
async def list_paper_trades(request: Request, limit: int = 50):
    db = request.app.state.db
    open_positions = db.list_paper_positions(status="open", limit=limit)
    closed_positions = db.list_paper_positions(limit=limit)
    closed_only = [p for p in closed_positions if p["status"] != "open"]
    stats = db.get_paper_stats()
    return {
        "open_positions": open_positions,
        "closed_positions": closed_only[:20],
        "stats": stats,
    }


@router.post("/paper-trades/{position_id}/close")
async def close_paper_trade(position_id: int, payload: ClosePaperRequest, request: Request):
    db = request.app.state.db
    ws_hub = request.app.state.ws
    positions = db.list_paper_positions()
    target = next((p for p in positions if p["id"] == position_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Sanal pozisyon bulunamadı.")
    
    close_price = payload.close_price if payload.close_price is not None else float(target.get("current_price") or target.get("entry_price") or 0.0)
    closed = db.close_paper_position(position_id, close_price=close_price, close_status=payload.status or "closed_manual")
    await ws_hub.broadcast("paper_position_closed", closed)
    return {"status": "closed", "position": closed}


@router.post("/scan")
async def scan_ticker(payload: ScanRequest, request: Request, background_tasks: BackgroundTasks):
    engine = get_engine(request)
    db = request.app.state.db
    ws_hub = request.app.state.ws
    ticker = payload.ticker.strip().upper()

    async def _do_scan():
        try:
            db.add_log(f"TradingAgents Taraması Başlatıldı: {ticker} ({payload.timeframe or 'H1'})", level="INFO")
            await ws_hub.broadcast("scan_started", {"ticker": ticker})
            signal = await engine.scan_ticker(ticker, date=payload.date, timeframe=payload.timeframe)
            await ws_hub.broadcast("signal_created", signal)
            
            cfg = engine.get_config()
            # If paper trading is active, create simulated position automatically
            if cfg.get("paper_trading") and signal["side"] in ["BUY", "SELL"]:
                paper_pos = db.create_paper_position({
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
                    "timeframe": signal.get("timeframe", "H1"),
                })
                db.update_signal_status(signal["id"], status="paper_active")
                db.add_log(f"Sanal Pozisyon Açıldı: {signal['broker_symbol']} {signal['side']} {signal['calculated_lot']} Lot @ {signal['entry_price']}", level="INFO")
                await ws_hub.broadcast("paper_position_opened", paper_pos)

            # If auto-execute on physical mobile device is enabled
            if cfg["auto_execute"] and signal["side"] in ["BUY", "SELL"]:
                await _execute_signal_internal(signal["id"], request.app)
        except Exception as e:
            db.add_log(f"TradingAgents Tarama Hatası ({ticker}): {e}", level="ERROR")
            await ws_hub.broadcast("scan_failed", {"ticker": ticker, "error": str(e)})

    background_tasks.add_task(_do_scan)
    return {"status": "scanning", "ticker": ticker, "message": "Analiz arka planda başlatıldı."}


async def _execute_signal_internal(signal_id: int, app: Any) -> dict[str, Any]:
    db = app.state.db
    ws_hub = app.state.ws
    dm = app.state.dm
    signal = db.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı.")

    if signal["status"] == "executed":
        return {"status": "already_executed", "order_id": signal["order_id"]}

    # Pick first ready device and account
    devices = db.list_devices()
    accounts = db.list_accounts()
    
    ready_device = next((d for d in devices if d["status"] in ["ready", "busy", "offline"]), None)
    enabled_account = next((a for a in accounts if a["enabled"]), None)

    dev_id = ready_device["id"] if ready_device else 1
    acc_id = enabled_account["id"] if enabled_account else 1

    import secrets
    order_data = {
        "account_id": acc_id,
        "device_id": dev_id,
        "symbol": signal["broker_symbol"],
        "side": signal["side"],
        "lot": signal["calculated_lot"],
        "sl": signal["sl"],
        "tp": signal["tp"],
        "idempotency_key": f"sig-{signal_id}-{secrets.token_hex(4)}",
    }

    order = db.create_order(order_data)
    db.update_signal_status(signal_id, status="executed", order_id=order["id"])
    db.add_log(f"Sinyal Emre Dönüştürüldü: #{order['id']} ({signal['broker_symbol']} {signal['side']} {signal['calculated_lot']} Lot)", level="INFO")

    await ws_hub.broadcast("signal_executed", {"signal_id": signal_id, "order": order})
    return {"status": "order_created", "order": order}


@router.post("/signals/{signal_id}/execute")
async def execute_signal(signal_id: int, request: Request):
    return await _execute_signal_internal(signal_id, request.app)


@router.post("/signals/{signal_id}/reject")
async def reject_signal(signal_id: int, request: Request):
    db = request.app.state.db
    signal = db.get_signal(signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail="Sinyal bulunamadı.")
    db.update_signal_status(signal_id, status="rejected")
    db.add_log(f"Sinyal Reddedildi: #{signal_id} ({signal['ticker']})", level="WARN")
    await request.app.state.ws.broadcast("signal_updated", {"signal_id": signal_id, "status": "rejected"})
    return {"status": "rejected", "signal_id": signal_id}


@router.get("/reports/{ticker}")
async def get_ticker_reports(ticker: str, request: Request):
    """Fetch all signals and TradingAgents reports for a specific ticker."""
    db = request.app.state.db
    engine = get_engine(request)
    t = ticker.upper()
    trading_sym = to_trading_ticker(t)

    # 1. Fetch Sinyalci signals from SQLite
    all_signals = db.list_signals(limit=100)
    matched_signals = [s for s in all_signals if s["ticker"] == t or t in s["broker_symbol"]]

    # 2. Fetch TradingAgents reports list
    reports = []
    try:
        import urllib.request, json
        ta_url = f"{engine.tradingagents_url}/api/reports"
        loop = asyncio.get_running_loop()
        req = urllib.request.Request(ta_url, headers={"User-Agent": "Sinyalci/1.0"})
        r_resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=5).read().decode())
        r_data = json.loads(r_resp)
        all_reports = r_data.get("reports", [])
        for r in all_reports:
            r_tick = str(r.get("ticker", "")).upper()
            if r_tick in [t, trading_sym.upper()] or trading_sym.upper() in r.get("report_id", "").upper():
                reports.append(r)
    except Exception:
        pass

    return {
        "ticker": t,
        "trading_ticker": trading_sym,
        "signals": matched_signals,
        "reports": reports,
    }


@router.get("/reports/{ticker}/{report_id}")
async def get_report_detail(ticker: str, report_id: str, request: Request):
    """Fetch full TradingAgents report content for a given report ID."""
    engine = get_engine(request)
    try:
        import urllib.request, json
        rep_url = f"{engine.tradingagents_url}/api/reports/{report_id}"
        loop = asyncio.get_running_loop()
        req = urllib.request.Request(rep_url, headers={"User-Agent": "Sinyalci/1.0"})
        rep_resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=5).read().decode())
        return json.loads(rep_resp)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Rapor yüklenemedi: {e}")
