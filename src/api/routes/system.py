"""System state, Kill-Switch, Dry-Run, and audit log routes."""

from fastapi import APIRouter, Request
from api.schemas import LogOut, SystemStateOut

router = APIRouter(prefix="/api", tags=["system"])


def _build_state(db) -> SystemStateOut:
    devices = db.list_devices()
    accounts = db.list_accounts()
    orders = db.list_orders(limit=500)
    return SystemStateOut(
        kill_switch=db.get_setting("kill_switch") == "1",
        dry_run=db.get_setting("dry_run") == "1",
        webhook_secret=db.get_setting("webhook_secret"),
        total_balance=round(sum(a["balance"] for a in accounts), 2),
        active_devices=sum(1 for d in devices if d["status"] == "ready"),
        total_devices=len(devices),
        today_orders=db.count_today_orders(),
        pending_orders=sum(1 for o in orders if o["status"] in ("queued", "scheduled", "executing")),
    )


@router.get("/system", response_model=SystemStateOut)
async def get_system_state(request: Request):
    return _build_state(request.app.state.db)


@router.post("/system/kill-switch", response_model=SystemStateOut)
async def toggle_kill_switch(request: Request, active: bool):
    db = request.app.state.db
    ws = request.app.state.ws
    db.set_setting("kill_switch", "1" if active else "0")
    db.add_log(f"Master Kill-Switch {'ENGAGED' if active else 'RELEASED'}", level="WARN" if active else "INFO")
    state = _build_state(db)
    await ws.broadcast("system_state", state.model_dump())
    return state


@router.post("/system/dry-run", response_model=SystemStateOut)
async def toggle_dry_run(request: Request, active: bool):
    db = request.app.state.db
    ws = request.app.state.ws
    db.set_setting("dry_run", "1" if active else "0")
    db.add_log(f"Dry-Run mode {'ENABLED' if active else 'DISABLED'}", level="INFO")
    state = _build_state(db)
    await ws.broadcast("system_state", state.model_dump())
    return state


@router.get("/logs", response_model=list[LogOut])
async def list_logs(request: Request, limit: int = 100):
    return request.app.state.db.list_logs(limit=limit)
