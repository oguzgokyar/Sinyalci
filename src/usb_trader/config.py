"""Configuration models for USB Trader."""

from pydantic import BaseModel, Field, model_validator


class TraderConfig(BaseModel):
    screen_width: int = Field(default=1080, gt=0)
    screen_height: int = Field(default=2400, gt=0)
    dwell_min_ms: int = Field(default=75, ge=20)
    dwell_max_ms: int = Field(default=150, le=500)
    reaction_min_s: float = Field(default=0.9, ge=0.0)
    reaction_max_s: float = Field(default=2.5, le=10.0)
    jitter_sigma_px: float = Field(default=6.0, gt=0.0)
    jitter_max_offset_px: int = Field(default=18, ge=1)
    template_threshold: float = Field(default=0.85, ge=0.5, le=1.0)
    lot_tolerance: float = Field(default=1e-4, ge=0.0)

    @model_validator(mode="after")
    def validate_ranges(self) -> "TraderConfig":
        if self.dwell_min_ms > self.dwell_max_ms:
            raise ValueError("dwell_min_ms must be <= dwell_max_ms")
        if self.reaction_min_s > self.reaction_max_s:
            raise ValueError("reaction_min_s must be <= reaction_max_s")
        return self
