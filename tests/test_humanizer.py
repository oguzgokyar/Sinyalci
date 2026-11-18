import random
from usb_trader.humanizer.jitter import apply_gaussian_jitter
from usb_trader.humanizer.timing import sample_dwell_ms, sample_reaction_delay_s
from usb_trader.humanizer.bezier import generate_cubic_bezier_path


def test_gaussian_jitter_respects_bounds_and_varies():
    rng = random.Random(42)
    samples = [apply_gaussian_jitter(500, 1000, sigma=6.0, max_offset=18, rng=rng) for _ in range(100)]
    assert all(abs(x - 500) <= 18 and abs(y - 1000) <= 18 for x, y in samples)
    assert len(set(samples)) > 50


def test_timing_distributions_stay_within_bounds():
    rng = random.Random(7)
    for _ in range(50):
        dwell = sample_dwell_ms(75, 150, rng=rng)
        delay = sample_reaction_delay_s(0.9, 2.5, rng=rng)
        assert 75 <= dwell <= 150
        assert 0.9 <= delay <= 2.5


def test_cubic_bezier_path_endpoints_and_non_linearity():
    rng = random.Random(99)
    path = generate_cubic_bezier_path((200, 1800), (200, 600), num_points=25, rng=rng)
    assert len(path) == 25
    assert path[0] == (200, 1800)
    assert path[-1] == (200, 600)
    # Must deviate slightly in X (non-robotic curve)
    assert any(x != 200 for x, _ in path[1:-1])
