"""Temperature-driven fruit ripening model.

Ripening units are "days at the reference temperature" (20 C).
"""

from dataclasses import dataclass

REFERENCE_C = 20.0
Q10 = 2.2
HEAT_CAP_C = 35.0  # above this it is damage, not ripening

STAGES = ("green", "ripe", "peak", "overripe", "compost")


@dataclass(frozen=True)
class Fruit:
    name: str
    to_ripe: float
    to_peak: float
    to_overripe: float
    to_compost: float
    chill_floor: float = 4.0

    def boundary(self, stage_key):
        return {
            "green": 0.0,
            "ripe": self.to_ripe,
            "peak": self.to_peak,
            "overripe": self.to_overripe,
            "compost": self.to_compost,
        }[stage_key]


#                      name          ripe  peak  over  compost  chill
FRUITS = {
    f.name: f
    for f in [
        Fruit("banana", 3.0, 5.0, 7.0, 11.0, chill_floor=12.0),
        Fruit("avocado", 5.0, 7.0, 9.0, 14.0, chill_floor=6.0),
        Fruit("tomato", 4.0, 6.0, 9.0, 14.0, chill_floor=10.0),
        Fruit("peach", 3.0, 4.5, 6.5, 10.0),
        Fruit("strawberry", 1.0, 2.0, 3.5, 6.0),
        Fruit("apple", 7.0, 14.0, 25.0, 40.0),
        Fruit("pear", 4.0, 6.0, 8.0, 12.0),
        Fruit("mango", 4.0, 6.0, 8.5, 13.0, chill_floor=10.0),
        Fruit("grape", 3.0, 7.0, 12.0, 20.0),
    ]
}


def ripening_rate(temp_c, chill_floor=4.0):
    """Relative ripening speed at temp_c (1.0 at 20 C)."""
    if temp_c <= chill_floor:
        return 0.0
    effective = min(float(temp_c), HEAT_CAP_C)
    rate = Q10 ** ((effective - REFERENCE_C) / 10.0)
    # near the chill floor ripening tapers rather than snapping on
    span = 3.0
    if temp_c < chill_floor + span:
        rate *= (temp_c - chill_floor) / span
    return rate


def accumulate(fruit, temps_c):
    """Sum ripening units over a list of daily temperatures."""
    return sum(ripening_rate(t, fruit.chill_floor) for t in temps_c)


def stage(fruit, units):
    if units < fruit.to_ripe:
        return "green"
    if units < fruit.to_peak:
        return "ripe"
    if units < fruit.to_overripe:
        return "peak"
    if units < fruit.to_compost:
        return "overripe"
    return "compost"


def next_stage(stage_key):
    i = STAGES.index(stage_key)
    return STAGES[i + 1] if i + 1 < len(STAGES) else None


def days_until(fruit, units, stage_key, temp_c):
    """Days at temp_c until `units` reaches the start of stage_key.

    Returns 0.0 if already there, None if it will never get there.
    """
    target = fruit.boundary(stage_key)
    if units >= target:
        return 0.0
    rate = ripening_rate(temp_c, fruit.chill_floor)
    if rate <= 0:
        return None
    return (target - units) / rate


def progress_bar(fruit, units, width=20):
    frac = min(max(units / fruit.to_compost, 0.0), 1.0)
    filled = int(round(frac * width))
    return "[" + "#" * filled + "." * (width - filled) + "]"


HUMAN = {
    "green": "still firm and shy. Give it counter time, not fridge time.",
    "ripe": "good to eat. Fridge now if you want to stretch it.",
    "peak": "eat it today. This is as good as it gets.",
    "overripe": "sweet, soft, headed for smoothie/bread/sauce.",
    "compost": "past eating. Compost it, or brew something on purpose.",
}

FLY = {
    "green": "nothing here yet. Go loiter on a dish sponge.",
    "ripe": "sugars are up. Scouts only.",
    "peak": "skin still tight, but keep one eye on it.",
    "overripe": "fermentation has started. This is our Woodstock.",
    "compost": "lay eggs, tell your 400 closest relatives, live fast.",
}


def human_advice(stage_key):
    return HUMAN[stage_key]


def fly_advice(stage_key):
    return FLY[stage_key]
