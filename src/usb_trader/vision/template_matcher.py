"""OpenCV template matching for button and widget localization."""

from dataclasses import dataclass
from typing import Optional
import cv2
import numpy as np


@dataclass(frozen=True)
class TemplateMatch:
    center_x: int
    center_y: int
    width: int
    height: int
    score: float


def find_template(
    frame: np.ndarray, template: np.ndarray, threshold: float = 0.85
) -> Optional[TemplateMatch]:
    if template.shape[0] > frame.shape[0] or template.shape[1] > frame.shape[1]:
        return None
    if float(np.std(template)) < 1e-3:
        raise ValueError("Template has zero variance (solid color); include button text or border.")

    if frame.ndim == template.ndim:
        src_frame, src_tmpl = frame, template
    else:
        src_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        src_tmpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if template.ndim == 3 else template

    result = cv2.matchTemplate(src_frame, src_tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if float(max_val) < threshold:
        return None
    th, tw = src_tmpl.shape[:2]
    return TemplateMatch(
        center_x=int(max_loc[0] + tw // 2),
        center_y=int(max_loc[1] + th // 2),
        width=int(tw),
        height=int(th),
        score=float(max_val),
    )
