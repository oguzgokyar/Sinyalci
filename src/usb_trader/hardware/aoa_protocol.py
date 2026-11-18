"""Android Open Accessory (AOA) 2.0 HID constants, descriptors and report builders."""

from typing import Optional

AOA_GET_PROTOCOL = 51
AOA_SEND_STRING = 52
AOA_START = 53
AOA_REGISTER_HID = 54
AOA_UNREGISTER_HID = 55
AOA_SET_HID_REPORT_DESC = 56
AOA_SEND_HID_EVENT = 57

TOUCHSCREEN_HID_ID = 1
KEYBOARD_HID_ID = 2
HID_LOGICAL_MAX = 10000

# Single-finger Absolute Touchscreen Digitizer (0..10000 X/Y)
TOUCHSCREEN_REPORT_DESCRIPTOR = bytes([
    0x05, 0x0D,        # USAGE_PAGE (Digitizer)
    0x09, 0x04,        # USAGE (Touch Screen)
    0xA1, 0x01,        # COLLECTION (Application)
    0x09, 0x22,        #   USAGE (Finger)
    0xA1, 0x02,        #   COLLECTION (Logical)
    0x09, 0x42,        #     USAGE (Tip Switch)
    0x15, 0x00,        #     LOGICAL_MINIMUM (0)
    0x25, 0x01,        #     LOGICAL_MAXIMUM (1)
    0x75, 0x01,        #     REPORT_SIZE (1)
    0x95, 0x01,        #     REPORT_COUNT (1)
    0x81, 0x02,        #     INPUT (Data,Var,Abs)
    0x95, 0x07,        #     REPORT_COUNT (7) padding
    0x81, 0x03,        #     INPUT (Cnst,Var,Abs)
    0x05, 0x01,        #     USAGE_PAGE (Generic Desktop)
    0x09, 0x30,        #     USAGE (X)
    0x15, 0x00,        #     LOGICAL_MINIMUM (0)
    0x26, 0x10, 0x27,  #     LOGICAL_MAXIMUM (10000)
    0x75, 0x10,        #     REPORT_SIZE (16)
    0x95, 0x01,        #     REPORT_COUNT (1)
    0x81, 0x02,        #     INPUT (Data,Var,Abs)
    0x09, 0x31,        #     USAGE (Y)
    0x15, 0x00,        #     LOGICAL_MINIMUM (0)
    0x26, 0x10, 0x27,  #     LOGICAL_MAXIMUM (10000)
    0x75, 0x10,        #     REPORT_SIZE (16)
    0x95, 0x01,        #     REPORT_COUNT (1)
    0x81, 0x02,        #     INPUT (Data,Var,Abs)
    0xC0,              #   END_COLLECTION
    0xC0,              # END_COLLECTION
])

# Standard 8-byte Boot Keyboard Descriptor
KEYBOARD_REPORT_DESCRIPTOR = bytes([
    0x05, 0x01, 0x09, 0x06, 0xA1, 0x01,
    0x05, 0x07, 0x19, 0xE0, 0x29, 0xE7,
    0x15, 0x00, 0x25, 0x01, 0x75, 0x01,
    0x95, 0x08, 0x81, 0x02, 0x95, 0x01,
    0x75, 0x08, 0x81, 0x03, 0x95, 0x06,
    0x75, 0x08, 0x15, 0x00, 0x25, 0x65,
    0x05, 0x07, 0x19, 0x00, 0x29, 0x65,
    0x81, 0x00, 0xC0,
])

# USB HID Usage Table (Keyboard/Keypad Page 0x07)
CHAR_TO_HID_USAGE: dict[str, tuple[int, int]] = {
    "1": (0x00, 0x1E), "2": (0x00, 0x1F), "3": (0x00, 0x20),
    "4": (0x00, 0x21), "5": (0x00, 0x22), "6": (0x00, 0x23),
    "7": (0x00, 0x24), "8": (0x00, 0x25), "9": (0x00, 0x26),
    "0": (0x00, 0x27), ".": (0x00, 0x37), "\n": (0x00, 0x28),
    "\b": (0x00, 0x2A),
}
for _i, _ch in enumerate("abcdefghijklmnopqrstuvwxyz"):
    CHAR_TO_HID_USAGE[_ch] = (0x00, 0x04 + _i)
    CHAR_TO_HID_USAGE[_ch.upper()] = (0x02, 0x04 + _i)  # Left Shift


def pixel_to_hid_coord(pixel: int, axis_max_px: int) -> int:
    if axis_max_px <= 0:
        raise ValueError("axis_max_px must be > 0")
    scaled = round((pixel / axis_max_px) * HID_LOGICAL_MAX)
    return max(0, min(HID_LOGICAL_MAX, scaled))


def build_touch_report(x: int, y: int, pressed: bool) -> bytes:
    tip = 0x01 if pressed else 0x00
    xc = max(0, min(HID_LOGICAL_MAX, x))
    yc = max(0, min(HID_LOGICAL_MAX, y))
    return bytes([tip, xc & 0xFF, (xc >> 8) & 0xFF, yc & 0xFF, (yc >> 8) & 0xFF])


def build_key_report(char: Optional[str]) -> bytes:
    if char is None:
        return bytes(8)
    if char not in CHAR_TO_HID_USAGE:
        raise ValueError(f"Unsupported HID character: {char!r}")
    mod, usage = CHAR_TO_HID_USAGE[char]
    return bytes([mod, 0x00, usage, 0x00, 0x00, 0x00, 0x00, 0x00])
