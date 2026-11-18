"""System state, Kill-Switch, Dry-Run, Environment & GitHub Updater routes."""

from __future__ import annotations

import pathlib
from typing import Any
from fastapi import APIRouter, HTTPException, Request
from api.schemas import LogOut, SettingsUpdate, SystemStateOut
from usb_trader.environment import build_checklist, detect_environment
from usb_trader.updater import apply_github_update, check_github_updates, get_local_git_info

router = APIRouter(prefix="/api", tags=["system"])


def _build_state(app) -> SystemStateOut:
    db = app.state.db
    hub = getattr(app.state, "hub", None)
    override = db.get_setting("env_mode_override", "auto")
    env_info = detect_environment(env_override=override)

    devices = db.list_devices()
    accounts = db.list_accounts()
    orders = db.list_orders(limit=500)
    connected_agents = hub.connected_count() if hub else 0

    return SystemStateOut(
        kill_switch=db.get_setting("kill_switch") == "1",
        dry_run=db.get_setting("dry_run") == "1",
        webhook_secret=db.get_setting("webhook_secret"),
        total_balance=round(sum(a["balance"] for a in accounts), 2),
        active_devices=sum(1 for d in devices if d["status"] == "ready"),
        total_devices=len(devices),
        today_orders=db.count_today_orders(),
        pending_orders=sum(1 for o in orders if o["status"] in ("queued", "scheduled", "executing")),
        env_mode=env_info["mode"],
        is_docker=env_info["is_docker"],
        connected_agents=connected_agents,
    )


@router.get("/system", response_model=SystemStateOut)
async def get_system_state(request: Request):
    return _build_state(request.app)


@router.post("/system/kill-switch", response_model=SystemStateOut)
async def toggle_kill_switch(request: Request, active: bool):
    db = request.app.state.db
    ws = request.app.state.ws
    db.set_setting("kill_switch", "1" if active else "0")
    db.add_log(f"Master Kill-Switch {'ENGAGED' if active else 'RELEASED'}", level="WARN" if active else "INFO")
    state = _build_state(request.app)
    await ws.broadcast("system_state", state.model_dump())
    return state


@router.post("/system/dry-run", response_model=SystemStateOut)
async def toggle_dry_run(request: Request, active: bool):
    db = request.app.state.db
    ws = request.app.state.ws
    db.set_setting("dry_run", "1" if active else "0")
    db.add_log(f"Dry-Run mode {'ENABLED' if active else 'DISABLED'}", level="INFO")
    state = _build_state(request.app)
    await ws.broadcast("system_state", state.model_dump())
    return state


@router.get("/logs", response_model=list[LogOut])
async def list_logs(request: Request, limit: int = 100):
    return request.app.state.db.list_logs(limit=limit)


@router.get("/system/environment")
async def get_environment_info(request: Request) -> dict[str, Any]:
    db = request.app.state.db
    hub = getattr(request.app.state, "hub", None)
    override = db.get_setting("env_mode_override", "auto")
    env = detect_environment(env_override=override)
    devices = db.list_devices()
    agent_count = hub.connected_count() if hub else 0
    token = db.get_setting("agent_token", "")
    kill_switch = db.get_setting("kill_switch") == "1"
    dry_run = db.get_setting("dry_run") == "1"

    checklist = build_checklist(
        mode=env["mode"],
        devices=devices,
        agent_count=agent_count,
        agent_token=token,
        kill_switch=kill_switch,
        dry_run=dry_run,
    )
    return {
        "env": env,
        "env_mode_override": override,
        "checklist": checklist,
        "agent_token": token,
        "vps_public_url": db.get_setting("vps_public_url", ""),
        "agents": hub.list_agents() if hub else [],
    }


@router.post("/system/settings")
async def update_settings(request: Request, body: SettingsUpdate):
    db = request.app.state.db
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            db.set_setting(k, str(v))
    db.add_log("Sistem ayarları güncellendi.", level="INFO")
    state = _build_state(request.app)
    await request.app.state.ws.broadcast("system_state", state.model_dump())
    return {"ok": True, "state": state}


@router.get("/system/github")
async def get_github_status(request: Request) -> dict[str, Any]:
    db = request.app.state.db
    repo_url = db.get_setting("github_repo_url", "")
    branch = db.get_setting("github_branch", "master")
    token = db.get_setting("github_token", "")
    repo_dir = pathlib.Path(__file__).resolve().parents[3]
    local_info = get_local_git_info(repo_dir)

    return {
        "repo_url": repo_url or local_info.get("remote_url", ""),
        "branch": branch,
        "has_token": bool(token.strip()),
        "local_git": local_info,
    }


@router.post("/system/github/check")
async def check_github_endpoint(request: Request) -> dict[str, Any]:
    db = request.app.state.db
    repo_url = db.get_setting("github_repo_url", "")
    branch = db.get_setting("github_branch", "master")
    token = db.get_setting("github_token", "")
    repo_dir = pathlib.Path(__file__).resolve().parents[3]

    if not repo_url:
        local_info = get_local_git_info(repo_dir)
        repo_url = local_info.get("remote_url", "")

    if not repo_url:
        raise HTTPException(status_code=400, detail="GitHub depo adresi (URL) ayarlanmamış.")

    return check_github_updates(repo_url=repo_url, branch=branch, repo_dir=repo_dir, github_token=token)


@router.post("/system/github/pull")
async def pull_github_endpoint(request: Request) -> dict[str, Any]:
    db = request.app.state.db
    repo_url = db.get_setting("github_repo_url", "")
    branch = db.get_setting("github_branch", "master")
    token = db.get_setting("github_token", "")
    repo_dir = pathlib.Path(__file__).resolve().parents[3]

    if not repo_url:
        local_info = get_local_git_info(repo_dir)
        repo_url = local_info.get("remote_url", "")

    if not repo_url:
        raise HTTPException(status_code=400, detail="GitHub depo adresi (URL) ayarlanmamış.")

    res = apply_github_update(repo_url=repo_url, branch=branch, repo_dir=repo_dir, github_token=token)
    if res.get("updated"):
        db.add_log(f"GitHub'dan güncellendi: {res.get('previous_sha')} -> {res.get('current_sha')}", level="INFO")
    return res
