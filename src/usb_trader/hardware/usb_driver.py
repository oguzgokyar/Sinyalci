"""PyUSB-backed AOA 2.0 HID transport driver for Android over USB cable."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Optional

from usb_trader.hardware.aoa_protocol import (
    AOA_GET_PROTOCOL,
    AOA_REGISTER_HID,
    AOA_SEND_HID_EVENT,
    AOA_SET_HID_REPORT_DESC,
    AOA_UNREGISTER_HID,
    KEYBOARD_HID_ID,
    KEYBOARD_REPORT_DESCRIPTOR,
    TOUCHSCREEN_HID_ID,
    TOUCHSCREEN_REPORT_DESCRIPTOR,
    build_key_report,
    build_touch_report,
    pixel_to_hid_coord,
)

USB_DIR_OUT = 0x00
USB_DIR_IN = 0x80
USB_TYPE_VENDOR = 0x40
EP0_MAX_CHUNK = 64


class AOADriverError(RuntimeError):
    """Raised when USB AOA 2.0 negotiation or HID submission fails."""


class AOAUSBDriver:
    def __init__(
        self,
        usb_device: Any,
        screen_width: int = 1080,
        screen_height: int = 2400,
        timeout_ms: int = 1000,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._dev = usb_device
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._timeout_ms = timeout_ms
        self._sleep = sleep_fn
        self._registered = False

    def get_aoa_version(self) -> int:
        raw = self._dev.ctrl_transfer(
            USB_DIR_IN | USB_TYPE_VENDOR, AOA_GET_PROTOCOL, 0, 0, 2, self._timeout_ms
        )
        return int(raw[0]) | (int(raw[1]) << 8)

    def _register_hid(self, hid_id: int, descriptor: bytes) -> None:
        self._dev.ctrl_transfer(
            USB_DIR_OUT | USB_TYPE_VENDOR,
            AOA_REGISTER_HID,
            hid_id,
            len(descriptor),
            b"",
            self._timeout_ms,
        )
        for offset in range(0, len(descriptor), EP0_MAX_CHUNK):
            chunk = descriptor[offset : offset + EP0_MAX_CHUNK]
            self._dev.ctrl_transfer(
                USB_DIR_OUT | USB_TYPE_VENDOR,
                AOA_SET_HID_REPORT_DESC,
                hid_id,
                offset,
                chunk,
                self._timeout_ms,
            )

    def _send_hid(self, hid_id: int, payload: bytes) -> None:
        self._dev.ctrl_transfer(
            USB_DIR_OUT | USB_TYPE_VENDOR,
            AOA_SEND_HID_EVENT,
            hid_id,
            0,
            payload,
            self._timeout_ms,
        )

    def open(self) -> None:
        version = self.get_aoa_version()
        if version < 2:
            raise AOADriverError(f"Device AOA protocol version {version} < 2 (HID unsupported)")
        self._register_hid(TOUCHSCREEN_HID_ID, TOUCHSCREEN_REPORT_DESCRIPTOR)
        self._register_hid(KEYBOARD_HID_ID, KEYBOARD_REPORT_DESCRIPTOR)
        self._sleep(0.15)  # Android input subsystem registration settle window
        self._registered = True

    def close(self) -> None:
        if not self._registered:
            return
        for hid_id in (TOUCHSCREEN_HID_ID, KEYBOARD_HID_ID):
            self._dev.ctrl_transfer(
                USB_DIR_OUT | USB_TYPE_VENDOR, AOA_UNREGISTER_HID, hid_id, 0, b"", self._timeout_ms
            )
        self._registered = False

    def tap(self, x_px: int, y_px: int, dwell_ms: int = 100) -> None:
        hx = pixel_to_hid_coord(x_px, self.screen_width)
        hy = pixel_to_hid_coord(y_px, self.screen_height)
        self._send_hid(TOUCHSCREEN_HID_ID, build_touch_report(hx, hy, pressed=True))
        self._sleep(dwell_ms / 1000.0)
        self._send_hid(TOUCHSCREEN_HID_ID, build_touch_report(hx, hy, pressed=False))

    def swipe_path(self, points: Iterable[tuple[int, int]], step_delay_ms: float = 12.0) -> None:
        pts = list(points)
        if not pts:
            return
        for x_px, y_px in pts:
            hx = pixel_to_hid_coord(x_px, self.screen_width)
            hy = pixel_to_hid_coord(y_px, self.screen_height)
            self._send_hid(TOUCHSCREEN_HID_ID, build_touch_report(hx, hy, pressed=True))
            self._sleep(step_delay_ms / 1000.0)
        last_x, last_y = pts[-1]
        self._send_hid(
            TOUCHSCREEN_HID_ID,
            build_touch_report(
                pixel_to_hid_coord(last_x, self.screen_width),
                pixel_to_hid_coord(last_y, self.screen_height),
                pressed=False,
            ),
        )

    def type_text(self, text: str, key_delay_ms: float = 65.0) -> None:
        for ch in text:
            self._send_hid(KEYBOARD_HID_ID, build_key_report(ch))
            self._sleep(key_delay_ms / 1000.0)
            self._send_hid(KEYBOARD_HID_ID, build_key_report(None))
            self._sleep(key_delay_ms / 1000.0)


def find_usb_device(vendor_id: Optional[int] = None, product_id: Optional[int] = None) -> Any:
    """Locate a WinUSB-bound Android USB device using libusb-package backend."""
    import libusb_package
    import usb.backend.libusb1 as libusb1
    import usb.core

    backend = libusb1.get_backend(find_library=libusb_package.find_library)
    kwargs: dict[str, Any] = {"backend": backend}
    if vendor_id is not None:
        kwargs["idVendor"] = vendor_id
    if product_id is not None:
        kwargs["idProduct"] = product_id
    dev = usb.core.find(**kwargs)
    if dev is None:
        raise AOADriverError("No matching USB device found (check cable and WinUSB driver).")
    return dev
