"""Strategy & Signals API endpoints."""

from __future__ import annotations

import asyncio
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel

from usb_trader.core.strategy_engine import StrategyEngine

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


class StrategyConfigUpdate(BaseModel):
    balance: Optional[float] = None
    risk_percent: Optional[float] = None
    min_rr: Optional[float] = None
    symbol_suffix: Optional[str] = None
    auto_execute: Optional[bool] = None
    watchlist: Optional[list[str]] = None
    max_daily_loss: Optional[float] = None


class ScanRequest(BaseModel):
    ticker: str
    date: Optional[str] = None


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


@router.get("/signals")
async def list_signals(request: Request, limit: int = 50):
    db = request.app.state.db
    signals = db.list_signals(limit=limit)
    stats = db.get_today_signal_stats()
    return {"signals": signals, "stats": stats}


@router.post("/scan")
async def scan_ticker(payload: ScanRequest, request: Request, background_tasks: BackgroundTasks):
    engine = get_engine(request)
    db = request.app.state.db
    ws_hub = request.app.state.ws
    ticker = payload.ticker.strip().upper()

    async def _do_scan():
        try:
            db.add_log(f"TradingAgents Taraması Başlatıldı: {ticker}", level="INFO")
            await ws_hub.broadcast("scan_started", {"ticker": ticker})
            signal = await engine.scan_ticker(ticker, date=payload.date)
            await ws_hub.broadcast("signal_created", signal)
            
            # If auto-execute is enabled, dispatch order directly
            cfg = engine.get_config()
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
