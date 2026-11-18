"""Launcher for TREADER Admin Dashboard."""

import os
import pathlib
import sys
import uvicorn
from api.db import Database


def bootstrap_defaults(db: Database) -> None:
    # 1. Ensure Galaxy A11 device is registered
    devs = db.list_devices()
    galaxy_dev = None
    for d in devs:
        if d.get("serial") == "R9HN70KYS1J" or "Galaxy" in d.get("name", ""):
            galaxy_dev = d
            break

    if not galaxy_dev:
        galaxy_dev = db.create_device({
            "name": "Samsung Galaxy A11",
            "serial": "R9HN70KYS1J",
            "usb_vid": "04e8",
            "usb_pid": "6860",
            "screen_width": 720,
            "screen_height": 1560,
            "profile_path": "profiles/galaxy_a11_mt5.json",
        })
        db.update_device_status(galaxy_dev["id"], "ready", aoa_version=2)
        print(f"Auto-registered device #{galaxy_dev['id']}: {galaxy_dev['name']}")

    # 2. Ensure Alpha Capital Demo MT5 account is registered
    accounts = db.list_accounts()
    if not any(a.get("login") == "2765609" for a in accounts):
        acc = db.create_account({
            "device_id": galaxy_dev["id"],
            "label": "Alpha Capital Demo",
            "login": "2765609",
            "server": "ACGMarkets-Main",
            "account_type": "Demo",
            "balance": 46250.0,
            "max_lot": 0.50,
            "daily_max_orders": 5,
            "daily_max_loss": 50.0,
        })
        print(f"Auto-registered MT5 account #{acc['id']}: {acc['label']} ({acc['login']}@{acc['server']})")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent
    os.chdir(root)
    db = Database(root / "data" / "treader.db")
    bootstrap_defaults(db)

    host = "127.0.0.1"
    port = 8000
    print(f"\n=======================================================")
    print(f"  TREADER Admin Dashboard baslatiliyor...")
    print(f"  URL: http://{host}:{port}")
    print(f"=======================================================\n")

    uvicorn.run("api.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
