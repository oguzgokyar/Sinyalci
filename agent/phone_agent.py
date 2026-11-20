"""Ultra-lightweight Termux 4.5G Reverse-Tunnel Agent for TREADER / Sinyalci VPS.

Usage inside Android Termux (no root required):
    curl -sSL https://YOUR_VPS/api/agent/install.sh | bash
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
    cmd = ["adb"]
    if adb_target:
        cmd.extend(["-s", adb_target])
    cmd.extend(args)
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
        if binary:
            return res.returncode, res.stdout
        return res.returncode, res.stdout.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        if binary:
            return 1, b""
        return 1, str(exc)


def _detect_adb_target(preferred: str = "127.0.0.1:5555") -> str:
    """Auto-detect active local ADB device or port."""
    try:
        res = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4)
        lines = [line.strip().split() for line in res.stdout.splitlines()[1:] if line.strip()]
        active = [parts[0] for parts in lines if len(parts) >= 2 and parts[1] == "device"]
        if preferred in active:
            return preferred
        if active:
            return active[0]
        # Quick loopback attempt
        c_res = subprocess.run(["adb", "connect", preferred], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3)
        if "connected" in c_res.stdout.lower():
            return preferred
    except Exception:
        pass
    return preferred


def _find_mt5_package(target: str, default: str = "net.metaquotes.metatrader5") -> str:
    """Find installed MetaTrader package name on device."""
    rc, out = _adb(target, "shell", "pm", "list", "packages")
    if rc == 0 and isinstance(out, str):
        candidates = []
        for line in out.splitlines():
            p = line.replace("package:", "").strip()
            if "metatrader" in p.lower() or "metaquotes" in p.lower():
                candidates.append(p)
        if default in candidates:
            return default
        if candidates:
            return candidates[0]
    return default


def _read_battery(adb_target: str) -> int | None:
    rc, out = _adb(adb_target, "shell", "dumpsys", "battery")
    if rc == 0 and isinstance(out, str):
        for line in out.splitlines():
            if "level:" in line:
                try:
                    return int(line.split(":")[1].strip())
                except ValueError:
                    return None
    # Fallback to sysfs capacity
    rc2, out2 = _adb(adb_target, "shell", "cat", "/sys/class/power_supply/battery/capacity")
    if rc2 == 0 and isinstance(out2, str) and out2.strip().isdigit():
        return int(out2.strip())
    return None


def _execute_action(adb_target: str, action: str, params: dict[str, Any]) -> dict[str, Any]:
    target = _detect_adb_target(adb_target)

    if action == "PING":
        return {"ok": True, "battery": _read_battery(target), "target": target}

    if action == "WAKE":
        _adb(target, "shell", "input", "keyevent", "224")  # KEYCODE_WAKEUP
        _adb(target, "shell", "input", "keyevent", "82")   # KEYCODE_MENU (unlocks swipe lockscreen)
        _adb(target, "shell", "input", "swipe", "360", "1200", "360", "400", "250")
        return {"ok": True}

    if action == "LAUNCH_MT5":
        requested_pkg = params.get("package", "net.metaquotes.metatrader5")
        actual_pkg = _find_mt5_package(target, default=requested_pkg)
        # Attempt multi-method app launch
        _adb(target, "shell", "monkey", "-p", actual_pkg, "-c", "android.intent.category.LAUNCHER", "1")
        _adb(target, "shell", "monkey", "-p", actual_pkg, "1")
        _adb(target, "shell", "am", "start", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", actual_pkg)
        _adb(target, "shell", "am", "start", "-n", f"{actual_pkg}/net.metaquotes.metatrader.ui.MainActivity")
        return {"ok": True, "package": actual_pkg}

    if action == "TAP":
        x, y, dwell = int(params["x"]), int(params["y"]), int(params.get("dwell_ms", 100))
        if dwell <= 140:
            _adb(target, "shell", "input", "tap", str(x), str(y))
        else:
            _adb(target, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(dwell))
        return {"ok": True}

    if action == "SWIPE":
        x1, y1 = int(params.get("x1", 360)), int(params.get("y1", 1000))
        x2, y2 = int(params.get("x2", 360)), int(params.get("y2", 400))
        dur = int(params.get("duration_ms", 300))
        _adb(target, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(dur))
        return {"ok": True}

    if action == "LONG_PRESS":
        x, y, dur = int(params["x"]), int(params["y"]), int(params.get("duration_ms", 900))
        _adb(target, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(dur))
        return {"ok": True}

    if action == "TYPE":
        text = str(params.get("text", ""))
        _adb(target, "shell", "input", "text", text)
        return {"ok": True}

    if action == "CLEAR_AND_TYPE":
        text = str(params.get("text", ""))
        # Move to end, delete existing text, type new text, and dismiss soft keyboard using KEYCODE_ESCAPE (111)
        _adb(target, "shell", "input", "keyevent", "123")  # KEYCODE_MOVE_END
        _adb(target, "shell", "input", "keyevent", "67", "67", "67", "67", "67", "67", "67", "67", "67", "67", "67", "67")
        _adb(target, "shell", "input", "text", text)
        _adb(target, "shell", "input", "keyevent", "111")  # KEYCODE_ESCAPE dismisses keyboard safely
        return {"ok": True}

    if action == "DISMISS_KEYBOARD":
        _adb(target, "shell", "input", "keyevent", "111")  # KEYCODE_ESCAPE
        return {"ok": True}

    if action == "KEYEVENT":
        code = str(params.get("code", "4"))
        _adb(target, "shell", "input", "keyevent", code)
        return {"ok": True}

    if action == "KEY_BACK":
        _adb(target, "shell", "input", "keyevent", "4")
        return {"ok": True}

    if action == "KEY_HOME":
        _adb(target, "shell", "input", "keyevent", "3")
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
        rc, raw = _adb(target, "exec-out", "screencap", "-p", binary=True)
        if rc != 0 or not raw or len(raw) < 100:
            # Fallback method: capture to /data/local/tmp/.sinyalci.png
            _adb(target, "shell", "screencap", "-p", "/data/local/tmp/.sinyalci.png")
            rc2, raw2 = _adb(target, "exec-out", "cat", "/data/local/tmp/.sinyalci.png", binary=True)
            if rc2 == 0 and raw2 and len(raw2) > 100:
                raw = raw2
                rc = 0

        if rc != 0 or not raw or len(raw) < 100:
            err_text = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw)
            if not err_text:
                err_text = f"ADB hedefi yanıt vermedi ({target}). Telefonda 'adb connect 127.0.0.1:PORT' yapılmalı."
            return {"ok": False, "error": err_text}
        b64 = base64.b64encode(raw if isinstance(raw, bytes) else raw.encode()).decode("ascii")
        return {"ok": True, "image_b64": b64, "format": "png", "battery": _read_battery(target)}

    return {"ok": False, "error": f"Unknown action: {action}"}


async def _heartbeat_worker(ws: Any, adb_target: str, model: str) -> None:
    """Send periodic background heartbeat every 15 seconds."""
    while True:
        try:
            await asyncio.sleep(15)
            target = _detect_adb_target(adb_target)
            bat = _read_battery(target)
            await ws.send(json.dumps({"event": "heartbeat", "battery": bat, "model": model}))
        except asyncio.CancelledError:
            break
        except Exception:
            break


async def run_agent(server_url: str, token: str, adb_target: str, model: str) -> None:
    import websockets

    sep = "&" if "?" in server_url else "?"
    full_url = f"{server_url}{sep}token={token}&model={model}"
    backoff = 2

    while True:
        target = _detect_adb_target(adb_target)
        try:
            print(f"[AGENT] Sunucuya bağlanılıyor: {server_url} (ADB: {target}) ...")
            async with websockets.connect(full_url, ping_interval=None, ping_timeout=None) as ws:
                print(f"[AGENT] ✓ Sunucuya başarıyla bağlandı! Model: {model}, Hedef: {target}")
                backoff = 2
                # Initial handshake
                await ws.send(json.dumps({
                    "event": "handshake",
                    "battery": _read_battery(target),
                    "model": model,
                    "target": target,
                }))

                # Launch periodic heartbeat in background
                hb_task = asyncio.create_task(_heartbeat_worker(ws, adb_target, model))
                try:
                    async for raw_msg in ws:
                        msg = json.loads(raw_msg)
                        req_id = msg.get("req_id")
                        action = msg.get("action", "")
                        params = msg.get("params", {})
                        
                        result = await asyncio.to_thread(_execute_action, target, action, params)
                        result["req_id"] = req_id
                        await ws.send(json.dumps(result))
                finally:
                    hb_task.cancel()
        except Exception as exc:
            print(f"[AGENT] Bağlantı kesildi ({exc}). {backoff} sn sonra yeniden denenecek...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sinyalci 4.5G Reverse-Tunnel Phone Agent")
    parser.add_argument("--server", required=True, help="WebSocket URL e.g. wss://sinyalci.domain/ws/agent/galaxy_a11")
    parser.add_argument("--token", required=True, help="Agent auth token from Settings page")
    parser.add_argument("--adb-target", default="127.0.0.1:5555", help="Local loopback ADB address")
    parser.add_argument("--model", default="Galaxy-A11", help="Device label")
    args = parser.parse_args()

    try:
        asyncio.run(run_agent(args.server, args.token, args.adb_target, args.model))
    except KeyboardInterrupt:
        print("[AGENT] Çıkış yapıldı.")
        sys.exit(0)


if __name__ == "__main__":
    main()
