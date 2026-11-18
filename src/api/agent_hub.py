"""WebSocket Hub for remote 4.5G Android phone agents (VPS reverse-tunnel)."""

from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import WebSocket


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ConnectedAgent:
    device_id: str
    ws: WebSocket
    ip: str = ""
    model: str = "Android"
    battery: Optional[int] = None
    connected_at: str = field(default_factory=_utc_now)
    last_seen: str = field(default_factory=_utc_now)


class AgentHub:
    """Manages reverse-tunneled 4.5G phone agents and request/response RPC over WebSocket."""

    def __init__(self) -> None:
        self._agents: dict[str, ConnectedAgent] = {}
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    def connected_count(self) -> int:
        return len(self._agents)

    def list_agents(self) -> list[dict[str, Any]]:
        return [
            {
                "device_id": a.device_id,
                "ip": a.ip,
                "model": a.model,
                "battery": a.battery,
                "connected_at": a.connected_at,
                "last_seen": a.last_seen,
                "online": True,
            }
            for a in self._agents.values()
        ]

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._agents

    async def register(self, device_id: str, ws: WebSocket, ip: str = "", model: str = "Android") -> None:
        await ws.accept()
        self._agents[device_id] = ConnectedAgent(device_id=device_id, ws=ws, ip=ip, model=model)

    def unregister(self, device_id: str) -> None:
        self._agents.pop(device_id, None)

    def handle_incoming(self, device_id: str, payload: dict[str, Any]) -> None:
        agent = self._agents.get(device_id)
        if agent:
            agent.last_seen = _utc_now()
            if "battery" in payload and payload["battery"] is not None:
                agent.battery = int(payload["battery"])
            if "model" in payload and payload["model"]:
                agent.model = str(payload["model"])

        req_id = payload.get("req_id")
        if req_id and req_id in self._pending:
            fut = self._pending.pop(req_id)
            if not fut.done():
                fut.set_result(payload)

    async def send_command(
        self,
        device_id: str,
        action: str,
        params: Optional[dict[str, Any]] = None,
        timeout: float = 20.0,
    ) -> dict[str, Any]:
        agent = self._agents.get(device_id)
        if not agent:
            raise RuntimeError(f"Telefon ajanı çevrimdışı: {device_id}")

        req_id = secrets.token_hex(8)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[req_id] = fut

        try:
            await agent.ws.send_json({"req_id": req_id, "action": action, "params": params or {}})
            return await asyncio.wait_for(fut, timeout=timeout)
        finally:
            self._pending.pop(req_id, None)
