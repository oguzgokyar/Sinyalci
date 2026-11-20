import pytest
from httpx import ASGITransport, AsyncClient
from api.main import create_app


@pytest.fixture
def test_app(tmp_path):
    db_file = tmp_path / "test.db"
    return create_app(db_path=db_file)


@pytest.mark.anyio
async def test_api_full_flow(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. System state
        res = await client.get("/api/system")
        assert res.status_code == 200
        state = res.json()
        assert state["kill_switch"] is False

        # 2. Register Device
        dev_res = await client.post("/api/devices", json={
            "name": "Galaxy A11 Lab",
            "serial": "TEST1234",
            "usb_vid": "04e8",
            "usb_pid": "6860",
            "screen_width": 720,
            "screen_height": 1560,
        })
        assert dev_res.status_code == 200
        dev = dev_res.json()
        assert dev["id"] == 1

        # 3. Create MT5 Account
        acc_res = await client.post("/api/accounts", json={
            "device_id": dev["id"],
            "label": "Alpha Capital Demo",
            "login": "2765609",
            "server": "ACGMarkets-Main",
            "account_type": "Demo",
            "balance": 46250.0,
            "max_lot": 0.50,
            "daily_max_orders": 3,
        })
        assert acc_res.status_code == 200
        acc = acc_res.json()
        assert acc["id"] == 1

        # 4. Enqueue Order (in Dry-run mode)
        order_res = await client.post("/api/orders", json={
            "account_ids": [acc["id"]],
            "symbol": "EURUSD",
            "side": "BUY",
            "lot": 0.01,
            "idempotency_key": "test-key-001",
        })
        assert order_res.status_code == 200
        orders = order_res.json()
        assert len(orders) == 1
        assert orders[0]["status"] == "queued"

        # 5. Idempotency duplicate check
        dup_res = await client.post("/api/orders", json={
            "account_ids": [acc["id"]],
            "symbol": "EURUSD",
            "side": "BUY",
            "lot": 0.01,
            "idempotency_key": "test-key-001",
        })
        assert dup_res.status_code == 200
        dup_orders = dup_res.json()
        assert dup_orders[0]["id"] == orders[0]["id"]

        # 6. Webhook signal ingress
        secret = state["webhook_secret"]
        wh_res = await client.post("/api/webhook/signal", json={
            "secret": secret,
            "symbol": "GBPUSD",
            "side": "SELL",
            "lot": 0.02,
        })
        assert wh_res.status_code == 200
        wh_orders = wh_res.json()
        assert wh_orders[0]["symbol"] == "GBPUSD"

        # 7. Kill-switch engagement blocks new orders
        await client.post("/api/system/kill-switch?active=true")
        blocked_res = await client.post("/api/orders", json={
            "account_ids": [acc["id"]],
            "symbol": "AUDCAD",
            "side": "BUY",
            "lot": 0.01,
        })
        assert blocked_res.status_code == 423
