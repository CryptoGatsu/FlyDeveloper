"""Degree-day ripening model.

Fruit banks ripening in proportion to how warm it is above a base temperature.
One "degree-day" is one day spent one degree above BASE_C.
"""

from __future__ import annotations

BASE_C = 4.0   # below this, ripening effectively stalls (fridge)
CAP_C = 35.0   # above this, extra heat doesn't buy extra ripening
ROOM_C = 21.0  # a plausible kitchen counter, used as the default "out" temp

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

# Cold is not a pause button for everything. Tropical and warm-season fruit
# kept below these temperatures *while still firm* takes chilling injury: the
# ripening machinery breaks, and it stays hard/mealy/flavourless even after it
# warms back up. Fruit missing from this table is happy in the fridge at any
# stage (BASE_C), so the degree-day math tells the whole story for it.
CHILL_SAFE_C = {
    "avocado": 7.0,   # unripe avocado in the fridge often never comes back
    "banana": 13.0,   # the classic: cold peel goes black, flesh stays hard
    "mango": 12.0,
    "peach": 7.0,     # long cold storage = mealy, dry stone fruit
    "tomato": 12.0,   # cold kills tomato flavour compounds, permanently
}


class UnknownFruit(KeyError):
    """Raised for a fruit we have no thresholds for."""


def thresholds(fruit: str):
    """Return (ripe, fly_feast, compost) degree-days for a fruit."""
    try:
        return FRUITS[str(fruit).strip().lower()]
    except KeyError:
        raise UnknownFruit(fruit) from None


def chill_floor(fruit: str) -> float:
    """Coldest temperature this fruit tolerates while it is still firm.

    Below this, cold does not merely stop the clock -- it can break it.
    Fridge-tolerant fruit returns BASE_C, i.e. "no special warning".
    """
    name = str(fruit).strip().lower()
    thresholds(name)  # validate
    return CHILL_SAFE_C.get(name, BASE_C)


def target_for(fruit: str, stage: str) -> float:
    """Degree-days at which `fruit` enters `stage`."""
    if stage not in FUTURE_STAGES:
        raise ValueError(f"stage must be one of {FUTURE_STAGES}, got {stage!r}")
    return dict(zip(FUTURE_STAGES, thresholds(fruit)))[stage]


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
    target = target_for(fruit, stage)
    if degree_days >= target:
        return 0.0
    rate = daily_rate(temp_c)
    if rate <= 0.0:
        return None
    return (target - degree_days) / rate


def forecast(fruit: str, degree_days: float, temp_c: float) -> dict:
    """Full picture: where it is now and when each stage arrives.

    ``chill_risk`` is True when the fruit is still firm *and* the forecast
    temperature is under its chill line -- the one case where the degree-day
    model is optimistic, because the fruit may not resume ripening at all.
    """
    name = str(fruit).strip().lower()
    thresholds(name)  # validate early
    stage = stage_of(name, degree_days)
    floor = chill_floor(name)
    return {
        "fruit": name,
        "temp_c": float(temp_c),
        "degree_days": round(float(degree_days), 1),
        "stage": stage,
        "chill_safe_c": floor,
        "chill_risk": bool(stage == "firm" and float(temp_c) < floor),
        "eta_days": {
            s: days_until(name, degree_days, temp_c, s) for s in FUTURE_STAGES
        },
    }


def plan(
    fruit: str,
    degree_days: float,
    days: float,
    stage: str = "ripe",
    counter_c: float = ROOM_C,
) -> dict:
    """Solve the clock backwards: how do I hit `stage` in `days` days?

    Two answers come back, because kitchens are not incubators:

    * ``temp_c`` -- the single steady temperature that lands it exactly on
      time. Honest arithmetic, hard to actually do.
    * ``counter_days`` / ``fridge_days`` -- leave it out at ``counter_c``
      for a while, then move it to the fridge, where the clock stops. Same
      landing day, and you own both of those appliances.

    ``status`` is one of:

    * ``"ok"``       -- it can be done; see the fields above.
    * ``"passed"``   -- it is already at or past that stage; nothing to plan.
    * ``"too-late"`` -- even at CAP_C it cannot get there in time;
      ``earliest_days`` says the soonest it could possibly arrive.

    The two-step plan is omitted (``None``) when the counter is too cold to
    make it in time, or when it is so cold that nothing ripens at all.

    ``chill_risk`` is True when the single steady temperature is under the
    fruit's ``chill_safe_c``: that hold would chill a firm fruit for the whole
    stretch, which it may never recover from. The counter-then-fridge plan is
    the safe way out, because the cold only arrives *after* it is ripe.
    """
    name = str(fruit).strip().lower()
    target = target_for(name, stage)
    days = float(days)
    if days <= 0:
        raise ValueError("days must be greater than 0")

    soaked = float(degree_days)
    floor = chill_floor(name)
    out = {
        "fruit": name,
        "stage": stage,
        "days": days,
        "degree_days": round(soaked, 1),
        "target_degree_days": target,
        "temp_c": None,
        "counter_c": None,
        "counter_days": None,
        "fridge_days": None,
        "earliest_days": None,
        "chill_safe_c": floor,
        "chill_risk": False,
        "status": "ok",
    }

    if soaked >= target:
        out["status"] = "passed"
        out["earliest_days"] = 0.0
        return out

    out["earliest_days"] = round((target - soaked) / daily_rate(CAP_C), 2)
    needed_rate = (target - soaked) / days
    temp = BASE_C + needed_rate
    if temp > CAP_C:
        out["status"] = "too-late"
        return out

    out["temp_c"] = round(temp, 1)
    out["chill_risk"] = bool(temp < floor)

    # The version you can actually do: counter, then fridge.
    counter_rate = daily_rate(counter_c)
    if counter_rate > 0.0:
        out_days = (target - soaked) / counter_rate
        chill = days - out_days
        if chill >= 0.05:  # otherwise it's just "leave it out", no plan needed
            out["counter_c"] = round(float(counter_c), 1)
            out["counter_days"] = round(out_days, 1)
            out["fridge_days"] = round(chill, 1)

    return out
