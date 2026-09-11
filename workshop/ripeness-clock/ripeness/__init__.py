"""Ripeness Clock: estimate where fruit is on the ripening curve."""

from .model import (
    FRUITS,
    Fruit,
    accumulate,
    days_until,
    fly_advice,
    human_advice,
    progress_bar,
    ripening_rate,
    stage,
)

__all__ = [
    "FRUITS",
    "Fruit",
    "accumulate",
    "days_until",
    "fly_advice",
    "human_advice",
    "progress_bar",
    "ripening_rate",
    "stage",
]
__version__ = "0.1.0"
