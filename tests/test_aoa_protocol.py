import pytest
from usb_trader.hardware.aoa_protocol import (
    AOA_GET_PROTOCOL,
    AOA_REGISTER_HID,
    AOA_UNREGISTER_HID,
    AOA_SET_HID_REPORT_DESC,
    AOA_SEND_HID_EVENT,
    TOUCHSCREEN_HID_ID,
    KEYBOARD_HID_ID,
    TOUCHSCREEN_REPORT_DESCRIPTOR,
    KEYBOARD_REPORT_DESCRIPTOR,
    pixel_to_hid_coord,
    build_touch_report,
    build_key_report,
)


def test_aoa_control_request_codes():
    assert AOA_GET_PROTOCOL == 51
    assert AOA_REGISTER_HID == 54
    assert AOA_UNREGISTER_HID == 55
    assert AOA_SET_HID_REPORT_DESC == 56
    assert AOA_SEND_HID_EVENT == 57
    assert TOUCHSCREEN_HID_ID != KEYBOARD_HID_ID
    assert len(TOUCHSCREEN_REPORT_DESCRIPTOR) > 20
    assert len(KEYBOARD_REPORT_DESCRIPTOR) > 20


def test_pixel_to_hid_coord_scaling_and_clamping():
    assert pixel_to_hid_coord(540, 1080) == 5000
    assert pixel_to_hid_coord(0, 1080) == 0
    assert pixel_to_hid_coord(1080, 1080) == 10000
    assert pixel_to_hid_coord(-50, 1080) == 0
    assert pixel_to_hid_coord(5000, 1080) == 10000


def test_build_touch_report_little_endian_encoding():
    # x=5000 (0x1388), y=2500 (0x09C4), 7-byte multi-touch report
    down = build_touch_report(5000, 2500, pressed=True)
    up = build_touch_report(5000, 2500, pressed=False)
    assert down == bytes([0x03, 0x00, 0x88, 0x13, 0xC4, 0x09, 0x01])
    assert up == bytes([0x00, 0x00, 0x88, 0x13, 0xC4, 0x09, 0x00])


def test_build_key_report_digits_and_dot():
    rep_zero = build_key_report("0")
    rep_dot = build_key_report(".")
    rep_release = build_key_report(None)
    assert len(rep_zero) == 8
    assert rep_zero[2] == 0x27  # USB HID Usage ID for '0'
    assert rep_dot[2] == 0x37   # USB HID Usage ID for '.'
    assert rep_release == bytes(8)


def test_build_key_report_rejects_unsupported_char():
    with pytest.raises(ValueError):
        build_key_report("€")
