"""Ultra-lightweight Termux 4.5G Reverse-Tunnel Agent for TREADER VPS.

Usage inside Android Termux (no root required):
    pkg install python android-tools
    pip install websockets
    adb connect 127.0.0.1:5555
    python phone_agent.py --server wss://YOUR_VPS_HOST/ws/agent/galaxy_a11 --token YOUR_AGENT_TOKEN
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
from typing import Any


def _adb(adb_target: str, *args: str, binary: bool = False) -> tuple[int, bytes | str]:
    cmd = ["adb", "-s", adb_target, *args]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if binary:
        return res.returncode, res.stdout
    return res.returncode, res.stdout.decode("utf-8", errors="replace").strip()


def _read_battery(adb_target: str) -> int | None:
    rc, out = _adb(adb_target, "shell", "dumpsys", "battery")
    if rc == 0 and isinstance(out, str):
        for line in out.splitlines():
            if "level:" in line:
                try:
                    return int(line.split(":")[1].strip())
                except ValueError:
                    return None
    return None


def _execute_action(adb_target: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
    if action == "PING":
        return {"ok": True, "battery": _read_battery(adb_target)}

    if action == "WAKE":
        _adb(adb_target, "shell", "input", "keyevent", "224")
        _adb(adb_target, "shell", "input", "swipe", "360", "1200", "360", "400", "250")
        return {"ok": True}

    if action == "LAUNCH_MT5":
        pkg = params.get("package", "net.metaquotes.metatrader5")
        _adb(adb_target, "shell", "monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1")
        return {"ok": True}

    if action == "TAP":
        x, y, dwell = int(params["x"]), int(params["y"]), int(params.get("dwell_ms", 100))
        _adb(adb_target, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(dwell))
        return {"ok": True}

    if action == "LONG_PRESS":
        x, y, dur = int(params["x"]), int(params["y"]), int(params.get("duration_ms", 900))
        _adb(adb_target, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(dur))
        return {"ok": True}

    if action == "TYPE":
        text = str(params.get("text", ""))
        _adb(adb_target, "shell", "input", "text", text)
        return {"ok": True}

    if action == "CLEAR_AND_TYPE":
        text = str(params.get("text", ""))
        # Move cursor to end
        _adb(adb_target, "shell", "input", "keyevent", "123")
        # Delete up to 10 characters
        for _ in range(10):
            _adb(adb_target, "shell", "input", "keyevent", "67")
        # Type text
        _adb(adb_target, "shell", "input", "text", text)
        # Dismiss soft keyboard cleanly
        _adb(adb_target, "shell", "input", "keyevent", "111")
        return {"ok": True}

    if action == "SWIPE":
        x1, y1 = int(params["x1"]), int(params["y1"])
        x2, y2 = int(params["x2"]), int(params["y2"])
        dur = int(params.get("duration_ms", 250))
        _adb(adb_target, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur))
        return {"ok": True}

    if action == "KEYEVENT":
        code = str(params.get("code", "4"))
        _adb(adb_target, "shell", "input", "keyevent", code)
        return {"ok": True}

    if action == "DISMISS_KEYBOARD":
        _adb(adb_target, "shell", "input", "keyevent", "111")
        return {"ok": True}

    if action == "SCREENCAP":
        rc, raw = _adb(adb_target, "exec-out", "screencap", "-p", binary=True)
        if rc != 0 or not raw:
            return {"ok": False, "error": "screencap failed"}
        b64 = base64.b64encode(raw if isinstance(raw, bytes) else raw.encode()).decode("ascii")
        return {"ok": True, "image_b64": b64, "format": "png", "battery": _read_battery(adb_target)}

    return {"ok": False, "error": f"Unknown action: {action}"}


async def run_agent(server_url: str, token: str, adb_target: str, model: str) -> None:
    import websockets

    sep = "&" if "?" in server_url else "?"
    full_url = f"{server_url}{sep}token={token}&model={model}"
    backoff = 2

    while True:
        try:
            print(f"[AGENT] Sunucuya baglaniliyor: {server_url} ...")
            async with websockets.connect(full_url, ping_interval=20, ping_timeout=15) as ws:
                print("[AGENT] Baglandi! Emir bekleniyor...")
                backoff = 2
                await ws.send(json.dumps({"event": "heartbeat", "battery": _read_battery(adb_target), "model": model}))

                async for raw_msg in ws:
                    msg = json.loads(raw_msg)
                    req_id = msg.get("req_id")
                    action = msg.get("action", "")
                    params = msg.get("params", {})
                    result = await asyncio.to_thread(_execute_action, adb_target, action, params)
                    result["req_id"] = req_id
                    await ws.send(json.dumps(result))
        except Exception as exc:
            print(f"[AGENT] Baglanti koptu ({exc}). {backoff} sn sonra yeniden denenecek...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


def main() -> None:
    parser = argparse.ArgumentParser(description="TREADER 4.5G Reverse-Tunnel Phone Agent")
    parser.add_argument("--server", required=True, help="WebSocket URL e.g. wss://vps.domain/ws/agent/galaxy_a11")
    parser.add_argument("--token", required=True, help="Agent auth token from Settings page")
    parser.add_argument("--adb-target", default="127.0.0.1:5555", help="Local loopback ADB address")
    parser.add_argument("--model", default="Galaxy-A11", help="Device label")
    args = parser.parse_args()

    try:
        asyncio.run(run_agent(args.server, args.token, args.adb_target, args.model))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
