import asyncio
from unittest.mock import AsyncMock
import pytest
from api.agent_hub import AgentHub


@pytest.mark.anyio
async def test_agent_hub_register_and_rpc_roundtrip():
    hub = AgentHub()
    ws = AsyncMock()
    await hub.register("galaxy_a11", ws, ip="10.0.0.1", model="Galaxy-A11")
    assert hub.connected_count() == 1
    assert hub.is_connected("galaxy_a11") is True

    async def fake_send(payload):
        # Simulate phone agent immediately replying with same req_id
        hub.handle_incoming("galaxy_a11", {"req_id": payload["req_id"], "ok": True, "battery": 94})

    ws.send_json.side_effect = fake_send
    reply = await hub.send_command("galaxy_a11", "PING")
    assert reply["ok"] is True
    assert hub.list_agents()[0]["battery"] == 94

    hub.unregister("galaxy_a11")
    assert hub.connected_count() == 0
