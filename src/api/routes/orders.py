"""Order planning, multi-account fan-out, cancellation, and external webhook ingress."""

import asyncio
import uuid
from fastapi import APIRouter, HTTPException, Request
from api.schemas import OrderCreate, OrderOut, WebhookSignal

router = APIRouter(prefix="/api", tags=["orders"])


async def _enqueue_orders(request: Request, body: OrderCreate) -> list[dict]:
    db = request.app.state.db
    dm = request.app.state.dm
    ws = request.app.state.ws

    if db.get_setting("kill_switch") == "1":
        raise HTTPException(status_code=423, detail="Master Kill-Switch is active")

    base_key = body.idempotency_key or f"ord-{uuid.uuid4().hex[:12]}"
    created: list[dict] = []

    for acc_id in body.account_ids:
        acc = db.get_account(acc_id)
        if not acc:
            raise HTTPException(status_code=404, detail=f"Account {acc_id} not found")
        if not acc["enabled"]:
            raise HTTPException(status_code=400, detail=f"Account {acc['label']} is disabled")
        if body.lot > acc["max_lot"]:
            raise HTTPException(
                status_code=400,
                detail=f"Lot {body.lot} exceeds max_lot {acc['max_lot']} for {acc['label']}",
            )
        if acc["today_orders"] >= acc["daily_max_orders"]:
            raise HTTPException(
                status_code=400,
                detail=f"Daily order cap ({acc['daily_max_orders']}) reached for {acc['label']}",
            )

        key = f"{base_key}-a{acc_id}"
        existing = db.get_order_by_key(key)
        if existing:
            created.append(existing)
            continue

        order = db.create_order({
            "account_id": acc_id,
            "device_id": acc["device_id"],
            "symbol": body.symbol,
            "side": body.side,
            "lot": body.lot,
            "sl": body.sl,
            "tp": body.tp,
            "scheduled_at": body.scheduled_at,
            "idempotency_key": key,
        })
        created.append(order)
        db.add_log(
            f"Order #{order['id']} {order['status']}: {order['side']} {order['lot']} {order['symbol']}",
            device_id=acc["device_id"],
            order_id=order["id"],
        )
        await ws.broadcast("order_updated", order)
        if order["status"] == "queued":
            asyncio.create_task(dm.execute_order_async(order["id"]))

    return created


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(request: Request, limit: int = 100):
    return request.app.state.db.list_orders(limit=limit)


@router.post("/orders", response_model=list[OrderOut])
async def create_orders(request: Request, body: OrderCreate):
    return await _enqueue_orders(request, body)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order(request: Request, order_id: int):
    db = request.app.state.db
    ws = request.app.state.ws
    order = db.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] not in ("queued", "scheduled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel order in state {order['status']}")
    updated = db.update_order(order_id, status="cancelled")
    db.add_log(f"Order #{order_id} cancelled", device_id=order["device_id"], order_id=order_id)
    await ws.broadcast("order_updated", updated)
    return updated


@router.post("/webhook/signal", response_model=list[OrderOut])
async def webhook_signal(request: Request, body: WebhookSignal):
    db = request.app.state.db
    expected = db.get_setting("webhook_secret")
    if body.secret != expected:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    account_ids = body.account_ids or [a["id"] for a in db.list_accounts() if a["enabled"]]
    if not account_ids:
        raise HTTPException(status_code=400, detail="No active accounts available")

    order_req = OrderCreate(
        account_ids=account_ids,
        symbol=body.symbol,
        side=body.side,
        lot=body.lot,
        sl=body.sl,
        tp=body.tp,
        idempotency_key=body.idempotency_key,
    )
    return await _enqueue_orders(request, order_req)
