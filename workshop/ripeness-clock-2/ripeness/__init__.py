"""Ripeness Clock: degree-day ripening estimates for fruit."""

from .model import (
    BASE_C,
    CAP_C,
    FRUITS,
    STAGES,
    UnknownFruit,
    accumulate,
    daily_rate,
    days_until,
    forecast,
    stage_of,
    thresholds,
)

__all__ = [
    "BASE_C",
    "CAP_C",
    "FRUITS",
    "STAGES",
    "UnknownFruit",
    "accumulate",
    "daily_rate",
    "days_until",
    "forecast",
    "stage_of",
    "thresholds",
]
__version__ = "1.0.0"
