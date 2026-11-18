"""Cubic Bezier path generator for natural human finger swipes."""

import random
from typing import Optional


def generate_cubic_bezier_path(
    start: tuple[int, int],
    end: tuple[int, int],
    num_points: int = 20,
    arc_spread_px: int = 45,
    rng: Optional[random.Random] = None,
) -> list[tuple[int, int]]:
    if num_points < 2:
        raise ValueError("num_points must be >= 2")
    gen = rng or random
    x0, y0 = start
    x3, y3 = end
    c1x = x0 + (x3 - x0) * 0.33 + gen.uniform(-arc_spread_px, arc_spread_px)
    c1y = y0 + (y3 - y0) * 0.33 + gen.uniform(-arc_spread_px * 0.3, arc_spread_px * 0.3)
    c2x = x0 + (x3 - x0) * 0.66 + gen.uniform(-arc_spread_px, arc_spread_px)
    c2y = y0 + (y3 - y0) * 0.66 + gen.uniform(-arc_spread_px * 0.3, arc_spread_px * 0.3)

    points: list[tuple[int, int]] = []
    for i in range(num_points):
        u = i / (num_points - 1)
        # Smoothstep ease-in-out timing parameter
        t = u * u * (3.0 - 2.0 * u)
        mt = 1.0 - t
        bx = (mt**3) * x0 + 3 * (mt**2) * t * c1x + 3 * mt * (t**2) * c2x + (t**3) * x3
        by = (mt**3) * y0 + 3 * (mt**2) * t * c1y + 3 * mt * (t**2) * c2y + (t**3) * y3
        points.append((round(bx), round(by)))
    points[0] = start
    points[-1] = end
    return points
