"""FastAPI entry point: REST + WebSocket + built SPA static hosting."""

from __future__ import annotations

from contextlib import asynccontextmanager
import pathlib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.agent_hub import AgentHub
from api.db import Database
from api.device_manager import DeviceManager
from api.routes import accounts, devices, orders, system, strategy
from api.scheduler import OrderScheduler
from api.ws import EventHub


def create_app(db_path: str | pathlib.Path = "data/treader.db") -> FastAPI:
    db = Database(db_path)
    ws_hub = EventHub()
    agent_hub = AgentHub()
    dm = DeviceManager(db, ws_hub, agent_hub=agent_hub)
    scheduler = OrderScheduler(db, dm, ws_hub=ws_hub, poll_interval_s=1.0)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler.start()
        try:
            yield
        finally:
            scheduler.stop()

    app = FastAPI(title="Sinyalci Admin", version="0.1.0", lifespan=lifespan)
    app.state.db = db
    app.state.ws = ws_hub
    app.state.hub = agent_hub
    app.state.dm = dm
    app.state.scheduler = scheduler

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router)
    app.include_router(devices.router)
    app.include_router(accounts.router)
    app.include_router(orders.router)
    app.include_router(strategy.router)

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws_hub.connect(ws)
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            ws_hub.disconnect(ws)

    @app.websocket("/ws/agent/{device_id}")
    async def agent_websocket_endpoint(ws: WebSocket, device_id: str, token: str = "", model: str = "Android"):
        expected = db.get_setting("agent_token", "")
        if not expected or token != expected:
            await ws.close(code=1008)
            return
        client_ip = ws.client.host if ws.client else ""
        await agent_hub.register(device_id, ws, ip=client_ip, model=model)

        # Auto-link or auto-create device in DB so it immediately reflects in UI
        existing = db.list_devices()
        matched = next(
            (d for d in existing if d.get("serial") == device_id or d.get("name", "").lower().replace(" ", "_") == device_id.lower()),
            None,
        )
        if not matched:
            dev_name = model if model != "Android" else "Samsung Galaxy A11"
            matched = db.create_device({
                "name": dev_name,
                "serial": device_id,
                "usb_vid": "04e8",
                "usb_pid": "6860",
                "screen_width": 720,
                "screen_height": 1560,
                "profile_path": "profiles/galaxy_a11_mt5.json",
            })
        db.update_device_status(matched["id"], "ready")
        db.add_log(f"4.5G Telefon Ajanı bağlandı ve hazır: {device_id} ({client_ip})", level="INFO")
        await ws_hub.broadcast("devices_changed", db.list_devices())
        await ws_hub.broadcast("system_state", system._build_state(app).model_dump())
        try:
            while True:
                payload = await ws.receive_json()
                agent_hub.handle_incoming(device_id, payload)
                if "battery" in payload and payload["battery"] is not None:
                    db.update_device_status(matched["id"], "ready", battery=int(payload["battery"]))
                    await ws_hub.broadcast("devices_changed", db.list_devices())
        except WebSocketDisconnect:
            agent_hub.unregister(device_id)
            db.update_device_status(matched["id"], "offline")
            db.add_log(f"4.5G Telefon Ajanı koptu: {device_id}", level="WARN")
            await ws_hub.broadcast("devices_changed", db.list_devices())
            await ws_hub.broadcast("system_state", system._build_state(app).model_dump())

    agent_dir = pathlib.Path(__file__).resolve().parents[2] / "agent"

    @app.get("/setup")
    @app.get("/setup_agent.sh")
    async def serve_setup_script():
        sh_file = agent_dir / "setup_agent.sh"
        if sh_file.exists():
            return FileResponse(sh_file, media_type="text/x-shellscript")
        return FileResponse(agent_dir / "phone_agent.py")

    @app.get("/agent/phone_agent.py")
    async def serve_phone_agent():
        py_file = agent_dir / "phone_agent.py"
        if py_file.exists():
            return FileResponse(py_file, media_type="text/x-python")
        return FileResponse(agent_dir / "phone_agent.py")

    dist_dir = pathlib.Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(dist_dir / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            target = dist_dir / full_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(dist_dir / "index.html")

    return app


app = create_app()
