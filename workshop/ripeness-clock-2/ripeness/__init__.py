"""Ripeness Clock: degree-day ripening estimates for fruit."""

from .model import (
    BASE_C,
    CAP_C,
    FRUITS,
    FUTURE_STAGES,
    STAGES,
    UnknownFruit,
    accumulate,
    daily_rate,
    days_until,
    forecast,
    plan,
    stage_of,
    target_for,
    thresholds,
)

__all__ = [
    "BASE_C",
    "CAP_C",
    "FRUITS",
    "FUTURE_STAGES",
    "STAGES",
    "UnknownFruit",
    "accumulate",
    "daily_rate",
    "days_until",
    "forecast",
    "plan",
    "stage_of",
    "target_for",
    "thresholds",
]
__version__ = "1.1.0"
