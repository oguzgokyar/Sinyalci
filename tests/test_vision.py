import cv2
import numpy as np
import pytest
from usb_trader.vision.capture import StaticFrameSource
from usb_trader.vision.template_matcher import find_template
from usb_trader.vision.state_machine import MTState, ScreenStateClassifier


def _draw_button(
    canvas: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: tuple[int, int, int],
    label: str,
) -> None:
    cv2.rectangle(canvas, (x1, y1), (x2, y2), color, thickness=-1)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), (255, 255, 255), thickness=2)
    cv2.putText(canvas, label, (x1 + 10, y1 + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def test_template_matcher_locates_synthetic_button():
    frame = np.full((300, 300, 3), 240, dtype=np.uint8)
    _draw_button(frame, 120, 100, 200, 140, (200, 90, 20), "BUY")
    _draw_button(frame, 20, 100, 100, 140, (20, 40, 210), "SELL")
    tmpl = frame[100:140, 120:200].copy()

    match = find_template(frame, tmpl, threshold=0.95)
    assert match is not None
    assert match.center_x == 160
    assert match.center_y == 120
    assert match.score >= 0.99


def test_template_matcher_rejects_solid_zero_variance_template():
    frame = np.full((100, 100, 3), 200, dtype=np.uint8)
    solid_tmpl = np.full((20, 20, 3), 10, dtype=np.uint8)
    with pytest.raises(ValueError):
        find_template(frame, solid_tmpl)


def test_screen_state_classifier_detects_order_form_and_popup():
    frame = np.full((300, 300, 3), 250, dtype=np.uint8)
    _draw_button(frame, 20, 20, 140, 60, (180, 70, 20), "ORDER")
    order_tmpl = frame[20:60, 20:140].copy()

    popup_canvas = np.full((60, 140, 3), 250, dtype=np.uint8)
    _draw_button(popup_canvas, 0, 0, 140, 60, (20, 20, 200), "REQUOTE")

    classifier = ScreenStateClassifier(
        templates={
            MTState.ORDER_FORM: order_tmpl,
            MTState.POPUP_ERROR: popup_canvas,
        },
        threshold=0.90,
    )
    src = StaticFrameSource(frame)
    assert classifier.classify(src.grab()) == MTState.ORDER_FORM
