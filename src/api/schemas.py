"""Single-source Pydantic schemas for TREADER Admin API."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    serial: Optional[str] = None
    usb_vid: str = "04e8"
    usb_pid: str = "6860"
    screen_width: int = 720
    screen_height: int = 1560
    profile_path: str = "profiles/galaxy_a11_mt5.json"


class DeviceOut(DeviceCreate):
    id: int
    status: str = "offline"
    battery: Optional[int] = None
    aoa_version: Optional[int] = None
    created_at: str


class DeviceScanItem(BaseModel):
    serial: Optional[str] = None
    usb_vid: Optional[str] = None
    usb_pid: Optional[str] = None
    vendor: str = "Unknown"
    adb_status: str = "none"
    aoa_status: str = "none"
    battery: Optional[int] = None


class AccountCreate(BaseModel):
    device_id: int
    label: str = Field(min_length=1, max_length=64)
    login: str = Field(min_length=1, max_length=32)
    server: str = Field(min_length=1, max_length=64)
    account_type: Literal["Demo", "Real"] = "Demo"
    balance: float = 0.0
    max_lot: float = Field(default=0.10, gt=0.0)
    daily_max_orders: int = Field(default=5, ge=1)
    daily_max_loss: float = Field(default=50.0, ge=0.0)


class AccountUpdate(BaseModel):
    label: Optional[str] = None
    balance: Optional[float] = None
    max_lot: Optional[float] = Field(default=None, gt=0.0)
    daily_max_orders: Optional[int] = Field(default=None, ge=1)
    daily_max_loss: Optional[float] = Field(default=None, ge=0.0)
    enabled: Optional[bool] = None


class AccountOut(AccountCreate):
    id: int
    enabled: bool = True
    today_orders: int = 0
    created_at: str


class OrderCreate(BaseModel):
    account_ids: list[int] = Field(min_length=1)
    symbol: str = Field(min_length=3, max_length=24)
    side: Literal["BUY", "SELL"]
    lot: float = Field(gt=0.0, le=50.0)
    sl: Optional[float] = None
    tp: Optional[float] = None
    scheduled_at: Optional[str] = None  # ISO-8601 UTC or None for immediate
    idempotency_key: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    account_id: int
    device_id: int
    account_label: str = ""
    symbol: str
    side: str
    lot: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    status: str
    scheduled_at: Optional[str] = None
    executed_at: Optional[str] = None
    latency_ms: Optional[int] = None
    ocr_lot: Optional[float] = None
    error: Optional[str] = None
    idempotency_key: str
    created_at: str


class WebhookSignal(BaseModel):
    secret: str
    account_ids: Optional[list[int]] = None
    symbol: str
    side: Literal["BUY", "SELL"]
    lot: float = Field(gt=0.0, le=50.0)
    sl: Optional[float] = None
    tp: Optional[float] = None
    idempotency_key: Optional[str] = None


class CalibrationUpdate(BaseModel):
    key: str  # e.g. "new_order_screen.buy_button"
    x: int
    y: int


class LogOut(BaseModel):
    id: int
    level: str
    device_id: Optional[int] = None
    order_id: Optional[int] = None
    message: str
    created_at: str


class SystemStateOut(BaseModel):
    kill_switch: bool
    dry_run: bool
    webhook_secret: str
    total_balance: float
    active_devices: int
    total_devices: int
    today_orders: int
    pending_orders: int
