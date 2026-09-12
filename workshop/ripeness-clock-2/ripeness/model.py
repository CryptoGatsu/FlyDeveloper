"""Degree-day ripening model.

Fruit banks ripening in proportion to how warm it is above a base temperature.
One "degree-day" is one day spent one degree above BASE_C.
"""

from __future__ import annotations

BASE_C = 4.0   # below this, ripening effectively stalls (fridge)
CAP_C = 35.0   # above this, extra heat doesn't buy extra ripening

STAGES = ("firm", "ripe", "fly-feast", "compost")
FUTURE_STAGES = STAGES[1:]

# fruit -> degree-days needed to reach (ripe, fly-feast, compost)
FRUITS = {
    "apple": (40.0, 220.0, 400.0),
    "avocado": (90.0, 130.0, 180.0),
    "banana": (55.0, 90.0, 140.0),
    "mango": (75.0, 120.0, 170.0),
    "peach": (45.0, 80.0, 120.0),
    "pear": (60.0, 100.0, 150.0),
    "strawberry": (20.0, 45.0, 70.0),
    "tomato": (70.0, 110.0, 160.0),
}


class UnknownFruit(KeyError):
    """Raised for a fruit we have no thresholds for."""


def thresholds(fruit: str):
    """Return (ripe, fly_feast, compost) degree-days for a fruit."""
    try:
        return FRUITS[str(fruit).strip().lower()]
    except KeyError:
        raise UnknownFruit(fruit) from None


def daily_rate(temp_c: float) -> float:
    """Degree-days banked per day at a steady temperature."""
    return max(0.0, min(float(temp_c), CAP_C) - BASE_C)


def accumulate(temps_c) -> float:
    """Degree-days from a history of one temperature per day."""
    return sum(daily_rate(t) for t in temps_c)


def stage_of(fruit: str, degree_days: float) -> str:
    ripe, feast, compost = thresholds(fruit)
    if degree_days < ripe:
        return "firm"
    if degree_days < feast:
        return "ripe"
    if degree_days < compost:
        return "fly-feast"
    return "compost"


def days_until(fruit: str, degree_days: float, temp_c: float, stage: str):
    """Days from now to `stage` at a steady temperature.

    Returns 0.0 if already past it, or None if it will never get there
    (too cold to accumulate anything).
    """
    if stage not in FUTURE_STAGES:
        raise ValueError(f"stage must be one of {FUTURE_STAGES}, got {stage!r}")
    target = dict(zip(FUTURE_STAGES, thresholds(fruit)))[stage]
    if degree_days >= target:
        return 0.0
    rate = daily_rate(temp_c)
    if rate <= 0.0:
        return None
    return (target - degree_days) / rate


def forecast(fruit: str, degree_days: float, temp_c: float) -> dict:
    """Full picture: where it is now and when each stage arrives."""
    name = str(fruit).strip().lower()
    thresholds(name)  # validate early
    return {
        "fruit": name,
        "temp_c": float(temp_c),
        "degree_days": round(float(degree_days), 1),
        "stage": stage_of(name, degree_days),
        "eta_days": {
            s: days_until(name, degree_days, temp_c, s) for s in FUTURE_STAGES
        },
    }
