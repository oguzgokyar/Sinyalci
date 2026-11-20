"""Device inventory, USB scan, live capture, AOA test, and click-to-calibrate routes."""

import cv2
from fastapi import APIRouter, HTTPException, Request, Response
from api.schemas import CalibrationUpdate, DeviceCreate, DeviceOut, DeviceScanItem

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(request: Request):
    return request.app.state.db.list_devices()


@router.post("/scan", response_model=list[DeviceScanItem])
async def scan_devices(request: Request):
    return request.app.state.dm.scan_usb()


@router.post("", response_model=DeviceOut)
async def create_device(request: Request, body: DeviceCreate):
    db = request.app.state.db
    ws = request.app.state.ws
    dev = db.create_device(body.model_dump())
    db.add_log(f"Device registered: {dev['name']} ({dev['usb_vid']}:{dev['usb_pid']})", device_id=dev["id"])
    await ws.broadcast("devices_changed", db.list_devices())
    return dev


@router.delete("/{device_id}")
async def delete_device(request: Request, device_id: int):
    db = request.app.state.db
    ws = request.app.state.ws
    if not db.delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    await ws.broadcast("devices_changed", db.list_devices())
    return {"deleted": True}


@router.get("/{device_id}/screenshot")
async def get_device_screenshot(request: Request, device_id: int):
    try:
        frame, _ = await request.app.state.dm.capture_screen(device_id)
        ok, buf = cv2.imencode(".png", frame)
        if not ok:
            raise RuntimeError("PNG encode failed")
        return Response(content=buf.tobytes(), media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{device_id}/test-aoa")
async def test_device_aoa(request: Request, device_id: int):
    try:
        res = await request.app.state.dm.test_aoa(device_id)
        await request.app.state.ws.broadcast("devices_changed", request.app.state.db.list_devices())
        return res
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/{device_id}/close-position")
async def close_device_position(request: Request, device_id: int):
    try:
        res = await request.app.state.dm.close_position_async(device_id)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{device_id}/calibrate")
async def calibrate_device(request: Request, device_id: int, body: CalibrationUpdate):
    try:
        res = request.app.state.dm.update_calibration(device_id, body.key, body.x, body.y)
        request.app.state.db.add_log(
            f"Calibrated {body.key} -> ({body.x}, {body.y})", device_id=device_id
        )
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{device_id}/close-position")
async def close_device_position(request: Request, device_id: int):
    try:
        res = await request.app.state.dm.close_position_async(device_id)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{device_id}/tap")
async def tap_device(request: Request, device_id: int, x: int = 540, y: int = 1435, dwell_ms: int = 90):
    try:
        dm = request.app.state.dm
        dev = dm.db.get_device(device_id)
        if not dev:
            raise HTTPException(status_code=404, detail="Device not found")
        serial = dev.get("serial")
        if dm._is_remote_agent(dev) and dm.agent_hub:
            res = await dm.agent_hub.send_command(serial, "TAP", {"x": x, "y": y, "dwell_ms": dwell_ms}, timeout=5.0)
            return res
        drv, _ = dm._get_touch_driver(dev)
        drv.tap(x, y, dwell_ms=dwell_ms)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{device_id}/dry-run-test")
async def run_device_dry_run_test(request: Request, device_id: int):
    try:
        res = await request.app.state.dm.run_dry_run_diagnostics(device_id)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
