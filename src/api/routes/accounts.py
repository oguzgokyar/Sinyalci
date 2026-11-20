"""MT5 account management and per-account risk guard routes."""

from fastapi import APIRouter, HTTPException, Request
from api.schemas import AccountCreate, AccountOut, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountOut])
async def list_accounts(request: Request):
    return request.app.state.db.list_accounts()


@router.post("", response_model=AccountOut)
async def create_account(request: Request, body: AccountCreate):
    db = request.app.state.db
    ws = request.app.state.ws
    if not db.get_device(body.device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    acc = db.create_account(body.model_dump())
    db.add_log(f"Account added: {acc['label']} ({acc['login']}@{acc['server']})", device_id=acc["device_id"])
    await ws.broadcast("accounts_changed", db.list_accounts())
    return acc


@router.patch("/{account_id}", response_model=AccountOut)
async def update_account(request: Request, account_id: int, body: AccountUpdate):
    db = request.app.state.db
    ws = request.app.state.ws
    acc = db.update_account(account_id, body.model_dump(exclude_none=True))
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    await ws.broadcast("accounts_changed", db.list_accounts())
    return acc


@router.post("/{account_id}/sync-balance", response_model=AccountOut)
async def sync_account_balance(request: Request, account_id: int):
    try:
        acc = await request.app.state.dm.sync_balance(account_id)
        await request.app.state.ws.broadcast("accounts_changed", request.app.state.db.list_accounts())
        return acc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/{account_id}")
async def delete_account(request: Request, account_id: int):
    db = request.app.state.db
    ws = request.app.state.ws
    if not db.delete_account(account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    await ws.broadcast("accounts_changed", db.list_accounts())
    return {"deleted": True}
