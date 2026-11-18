"""Randomized touch dwell time and reaction latency samplers."""

import random
from typing import Optional


def sample_dwell_ms(min_ms: int = 75, max_ms: int = 150, rng: Optional[random.Random] = None) -> int:
    gen = rng or random
    mean = (min_ms + max_ms) / 2.0
    sigma = (max_ms - min_ms) / 5.0
    val = round(gen.gauss(mean, sigma))
    return max(min_ms, min(max_ms, val))


def sample_reaction_delay_s(
    min_s: float = 0.9, max_s: float = 2.5, rng: Optional[random.Random] = None
) -> float:
    gen = rng or random
    val = gen.uniform(min_s, max_s)
    return round(val, 3)
