"""Capture live MT5 frames from connected Android phone for template & ROI calibration."""

import argparse
import pathlib
import cv2
from usb_trader.vision.adb_capture import AdbSnapshotSource
from usb_trader.vision.ocr_verifier import OCRVerifier


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture MT5 screen frame for calibration.")
    parser.add_argument("--name", default="snapshot", help="Output filename tag (saved under captures/)")
    parser.add_argument("--serial", default=None, help="Optional ADB device serial or IP:port")
    parser.add_argument("--roi", default=None, help="Optional OCR test ROI as x1,y1,x2,y2")
    args = parser.parse_args()

    out_dir = pathlib.Path("captures")
    out_dir.mkdir(exist_ok=True)

    src = AdbSnapshotSource(serial=args.serial)
    frame = src.grab()
    h, w = frame.shape[:2]
    out_path = out_dir / f"{args.name}.png"
    cv2.imwrite(str(out_path), frame)
    print(f"Saved {out_path.resolve()} ({w}x{h})")

    if args.roi:
        x1, y1, x2, y2 = (int(v.strip()) for v in args.roi.split(","))
        val = OCRVerifier().read_number(frame, (x1, y1, x2, y2))
        print(f"OCR ROI ({x1},{y1},{x2},{y2}) -> {val}")


if __name__ == "__main__":
    main()
