import numpy as np
from usb_trader.vision.ocr_verifier import parse_numeric_text, OCRVerifier


def test_parse_numeric_text_handles_mt5_formatting():
    assert parse_numeric_text("0.10") == 0.10
    assert parse_numeric_text(" 1,25 ") == 1.25
    assert parse_numeric_text("Lot: 0.50") == 0.50
    assert parse_numeric_text("invalid") is None


def test_ocr_verifier_confirms_expected_lot():
    verifier = OCRVerifier(reader_fn=lambda _roi: "0.10")
    dummy_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert verifier.verify_value(dummy_frame, roi=(10, 10, 80, 40), expected=0.10) is True
    assert verifier.verify_value(dummy_frame, roi=(10, 10, 80, 40), expected=0.50) is False
