"""Gaussian coordinate dispersion for human-like tap targets."""

import random
from typing import Optional


def apply_gaussian_jitter(
    x: int,
    y: int,
    sigma: float = 6.0,
    max_offset: int = 18,
    rng: Optional[random.Random] = None,
) -> tuple[int, int]:
    gen = rng or random
    dx = round(max(-max_offset, min(max_offset, gen.gauss(0.0, sigma))))
    dy = round(max(-max_offset, min(max_offset, gen.gauss(0.0, sigma))))
    return x + dx, y + dy
