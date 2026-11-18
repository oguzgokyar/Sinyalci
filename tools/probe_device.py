"""Read-only USB & AOA 2.0 capability probe for connected Android devices."""

import libusb_package
import usb.backend.libusb1 as libusb1
import usb.core
from usb_trader.hardware.usb_driver import AOAUSBDriver

KNOWN_ANDROID_VIDS = {
    0x04E8: "Samsung",
    0x18D1: "Google / AOA Accessory",
    0x2717: "Xiaomi",
    0x2A70: "OnePlus",
    0x12D1: "Huawei",
    0x22B8: "Motorola",
    0x0FCE: "Sony",
}


def main() -> None:
    backend = libusb1.get_backend(find_library=libusb_package.find_library)
    if backend is None:
        print("ERROR: libusb backend could not be loaded.")
        return

    devices = list(usb.core.find(find_all=True, backend=backend))
    print(f"Discovered {len(devices)} USB device(s):")
    android_found = False

    for dev in devices:
        vid, pid = dev.idVendor, dev.idProduct
        vendor_hint = KNOWN_ANDROID_VIDS.get(vid, "")
        if vendor_hint:
            android_found = True

        aoa_status = "skipped"
        if vendor_hint:
            try:
                ver = AOAUSBDriver(dev).get_aoa_version()
                aoa_status = f"READY -> AOA v{ver}"
            except Exception as exc:
                aoa_status = f"needs WinUSB or unsupported ({type(exc).__name__}: {exc})"

        tag = f" [{vendor_hint}]" if vendor_hint else ""
        print(f"  - {vid:04x}:{pid:04x}{tag} -> {aoa_status}")

    if not android_found:
        print("\nNo known Android phone VID detected. Check USB data cable connection.")


if __name__ == "__main__":
    main()
