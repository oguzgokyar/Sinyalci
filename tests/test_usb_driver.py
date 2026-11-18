from unittest.mock import MagicMock
import pytest
from usb_trader.hardware.aoa_protocol import (
    AOA_GET_PROTOCOL,
    AOA_REGISTER_HID,
    AOA_SET_HID_REPORT_DESC,
    AOA_SEND_HID_EVENT,
    AOA_UNREGISTER_HID,
    TOUCHSCREEN_HID_ID,
    KEYBOARD_HID_ID,
)
from usb_trader.hardware.usb_driver import AOAUSBDriver, AOADriverError


def _make_mock_usb_device(aoa_version: int = 2) -> MagicMock:
    dev = MagicMock()
    def ctrl_transfer(bmRequestType, bRequest, wValue=0, wIndex=0, data_or_wLength=None, timeout=None):
        if bRequest == AOA_GET_PROTOCOL:
            return bytes([aoa_version & 0xFF, (aoa_version >> 8) & 0xFF])
        return len(data_or_wLength) if isinstance(data_or_wLength, (bytes, bytearray)) else 0
    dev.ctrl_transfer.side_effect = ctrl_transfer
    return dev


def test_driver_verifies_aoa_v2_and_registers_hid_devices():
    dev = _make_mock_usb_device(aoa_version=2)
    driver = AOAUSBDriver(dev, screen_width=1080, screen_height=2400, sleep_fn=lambda _: None)
    driver.open()
    requests = [call.args[1] for call in dev.ctrl_transfer.call_args_list]
    assert AOA_GET_PROTOCOL in requests
    assert requests.count(AOA_REGISTER_HID) == 2
    assert requests.count(AOA_SET_HID_REPORT_DESC) >= 2
    driver.close()
    close_reqs = [call.args[1] for call in dev.ctrl_transfer.call_args_list]
    assert close_reqs.count(AOA_UNREGISTER_HID) == 2


def test_driver_rejects_aoa_v1_device():
    dev = _make_mock_usb_device(aoa_version=1)
    driver = AOAUSBDriver(dev, screen_width=1080, screen_height=2400, sleep_fn=lambda _: None)
    with pytest.raises(AOADriverError):
        driver.open()


def test_driver_tap_and_type_emit_hid_events():
    dev = _make_mock_usb_device(aoa_version=2)
    driver = AOAUSBDriver(dev, screen_width=1080, screen_height=2400, sleep_fn=lambda _: None)
    driver.open()
    dev.ctrl_transfer.reset_mock()

    driver.tap(540, 1200, dwell_ms=100)
    touch_calls = [c for c in dev.ctrl_transfer.call_args_list if c.args[1] == AOA_SEND_HID_EVENT]
    assert len(touch_calls) == 2
    assert touch_calls[0].args[2] == TOUCHSCREEN_HID_ID
    assert touch_calls[0].args[4][0] == 0x01
    assert touch_calls[1].args[4][0] == 0x00

    dev.ctrl_transfer.reset_mock()
    driver.type_text("0.1")
    key_calls = [c for c in dev.ctrl_transfer.call_args_list if c.args[1] == AOA_SEND_HID_EVENT]
    assert len(key_calls) == 6  # 3 chars * (press + release)
    assert all(c.args[2] == KEYBOARD_HID_ID for c in key_calls)
