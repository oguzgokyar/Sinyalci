import pytest
from pydantic import ValidationError
from usb_trader.config import TraderConfig


def test_default_config_values():
    cfg = TraderConfig()
    assert cfg.screen_width == 1080
    assert cfg.screen_height == 2400
    assert cfg.dwell_min_ms == 75
    assert cfg.dwell_max_ms == 150
    assert cfg.reaction_min_s == 0.9
    assert cfg.reaction_max_s == 2.5
    assert cfg.jitter_sigma_px == 6.0
    assert cfg.jitter_max_offset_px == 18
    assert cfg.template_threshold == 0.85


def test_invalid_dwell_range_rejected():
    with pytest.raises(ValidationError):
        TraderConfig(dwell_min_ms=200, dwell_max_ms=100)
