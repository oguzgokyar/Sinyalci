"""Live Demo Trade Learning & Execution Script (0.01 Lot BUY/SELL + Close)."""

import argparse
import json
import pathlib
import subprocess
import time
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

from usb_trader.config import TraderConfig
from usb_trader.humanizer.jitter import apply_gaussian_jitter
from usb_trader.humanizer.timing import sample_dwell_ms
from usb_trader.vision.adb_capture import AdbSnapshotSource
from usb_trader.vision.ocr_verifier import OCRVerifier

ADB_PATH = str(pathlib.Path(__file__).resolve().parents[1] / "tools" / "scrcpy" / "adb.exe")
PROFILE_PATH = pathlib.Path(__file__).resolve().parents[1] / "profiles" / "galaxy_a11_mt5.json"


def adb_tap(x: int, y: int, cfg: TraderConfig, jitter: bool = True) -> tuple[int, int]:
    tx, ty = (
        apply_gaussian_jitter(x, y, sigma=cfg.jitter_sigma_px, max_offset=12)
        if jitter
        else (x, y)
    )
    dwell = sample_dwell_ms(cfg.dwell_min_ms, cfg.dwell_max_ms)
    subprocess.run(
        [ADB_PATH, "shell", "input", "swipe", str(tx), str(ty), str(tx), str(ty), str(dwell)],
        check=True,
    )
    return tx, ty


def adb_long_press(x: int, y: int, duration_ms: int = 900) -> None:
    subprocess.run(
        [ADB_PATH, "shell", "input", "swipe", str(x), str(y), str(x), str(y), str(duration_ms)],
        check=True,
    )


def find_text_center(img: np.ndarray, needle: str, engine: RapidOCR) -> tuple[int, int] | None:
    res, _ = engine(img)
    needle_low = needle.lower()
    for box, txt, _score in (res or []):
        if needle_low in txt.lower():
            xs = [int(p[0]) for p in box]
            ys = [int(p[1]) for p in box]
            return (min(xs) + max(xs)) // 2, (min(ys) + max(ys)) // 2
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute 0.01 lot BUY or SELL and learn close flow on Demo.")
    parser.add_argument("--side", choices=["BUY", "SELL"], required=True)
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--hold-sec", type=float, default=3.0, help="Seconds to hold before closing")
    args = parser.parse_args()

    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    cfg = TraderConfig(screen_width=720, screen_height=1560)
    cap = AdbSnapshotSource(adb_path=ADB_PATH)
    ocr = OCRVerifier()
    raw_ocr = RapidOCR()
    out_dir = pathlib.Path("captures/live_trade")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 0. Check screen is unlocked
    frame = cap.grab()
    if find_text_center(frame, "kilit", raw_ocr) is not None or float(np.mean(frame)) < 10.0:
        raise RuntimeError("Phone screen is locked or off! Unlock phone first.")

    # 1. Go to Trade tab -> open New Order (+)
    nav = profile["navigation"]
    print("[1/6] Islem (Trade) sekmesine geciliyor...")
    adb_tap(*nav["tab_trade"], cfg)
    time.sleep(0.8)

    print("[2/6] Yeni Emir (+) ekrani aciliyor...")
    adb_tap(*nav["btn_new_order_header"], cfg)
    time.sleep(1.2)

    order_frame = cap.grab()
    cv2.imwrite(str(out_dir / f"01_order_form_{args.side.lower()}.png"), order_frame)

    # 2. Verify Lot == args.lot (0.01) before touching BUY/SELL
    order_cfg = profile["new_order_screen"]
    lot_roi = tuple(order_cfg["lot_roi"])
    observed_lot = ocr.read_number(order_frame, lot_roi)
    print(f"[3/6] Ekrandaki Lot OCR okumasi: {observed_lot} (Hedef: {args.lot})")
    if observed_lot is None or abs(observed_lot - args.lot) > 1e-4:
        raise RuntimeError(f"SAFETY ABORT: Expected lot {args.lot}, observed {observed_lot}!")

    # 3. Execute BUY or SELL with Gaussian Jitter + Dwell Time
    btn_coords = order_cfg["buy_button"] if args.side == "BUY" else order_cfg["sell_button"]
    tx, ty = adb_tap(*btn_coords, cfg)
    print(f"[4/6] {args.side} butonuna insansi sapmayla basildi -> ({tx}, {ty})")
    time.sleep(args.hold_sec)

    # 4. Capture Trade tab with open position
    open_frame = cap.grab()
    cv2.imwrite(str(out_dir / f"02_open_position_{args.side.lower()}.png"), open_frame)
    print("[5/6] Acik pozisyon yakalandi. Kapatmak icin pozisyon satirina uzun basiliyor...")

    # First open position row sits right below Pozisyonlar header (~y=450)
    pos_center = find_text_center(open_frame, ".pro", raw_ocr)
    if pos_center is None:
        raise RuntimeError("No open '.pro' position found on Trade tab after execution!")
    print(f"      Acik pozisyon bulundu: {pos_center}")

    adb_long_press(pos_center[0], pos_center[1], duration_ms=900)
    time.sleep(1.0)

    menu_frame = cap.grab()
    cv2.imwrite(str(out_dir / f"03_position_menu_{args.side.lower()}.png"), menu_frame)

    close_opt = find_text_center(menu_frame, "kapat", raw_ocr)
    if close_opt is None:
        raise RuntimeError("Could not find 'Pozisyonu kapat' option in context menu!")
    print(f"      'Pozisyonu kapat' menusu bulundu: {close_opt}")
    adb_tap(close_opt[0], close_opt[1], cfg)
    time.sleep(1.2)

    close_screen = cap.grab()
    cv2.imwrite(str(out_dir / f"04_close_screen_{args.side.lower()}.png"), close_screen)

    close_confirm = find_text_center(close_screen, "kapat", raw_ocr)
    # Specifically prefer bottom close button (y > 1200)
    res_close, _ = raw_ocr(close_screen)
    bottom_close = None
    for box, txt, _ in (res_close or []):
        ys = [int(p[1]) for p in box]
        xs = [int(p[0]) for p in box]
        cy = (min(ys) + max(ys)) // 2
        cx = (min(xs) + max(xs)) // 2
        if cy > 1200 and ("kapat" in txt.lower() or "zarar" in txt.lower() or "kar" in txt.lower()):
            bottom_close = (cx, cy)
            break

    if bottom_close is None:
        raise RuntimeError("Could not locate bottom Close confirmation button!")
    tx, ty = adb_tap(bottom_close[0], bottom_close[1], cfg)
    print(f"[6/6] Pozisyon kapatma onayina basildi -> ({tx}, {ty})")
    time.sleep(1.5)

    final_frame = cap.grab()
    cv2.imwrite(str(out_dir / f"05_after_close_{args.side.lower()}.png"), final_frame)
    print(f"TAMAMLANDI: {args.side} {args.lot} Lot acildi ve guvenle kapatildi!")


if __name__ == "__main__":
    main()
