"""fruitwatch - a tiny ripeness & fermentation clock.

Thermal-time model: fruit ripens in warm days, not calendar days.
progress 1.0 = peak for humans, 1.45 = fermentation starts, 2.0 = compost.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

Q10 = 2.3          # rate multiplier per +10 C
REF_C = 20.0       # reference temperature for days_to_ripe
BASE_C = 4.0       # below this, ripening nearly stops
CAP_C = 38.0       # above this it is not ripening, it is cooking

PEAK = 1.0         # best for humans
FERMENT = 1.45     # fly happy hour opens
COMPOST = 2.0      # let it go


@dataclass(frozen=True)
class Fruit:
    name: str
    days_to_ripe: float  # store-bought -> peak, at REF_C
    note: str


FRUITS = {
    f.name: f
    for f in [
        Fruit("strawberry", 2.5, "mould beats fermentation; eat fast"),
        Fruit("peach", 3.0, "smells like an invitation"),
        Fruit("banana", 3.5, "the classic fly cathedral"),
        Fruit("plum", 3.5, "skin splits, party starts"),
        Fruit("avocado", 4.0, "peak lasts about one afternoon"),
        Fruit("mango", 4.0, "loud, sweet, ferments beautifully"),
        Fruit("pear", 4.0, "ripens from the inside out"),
        Fruit("tomato", 4.5, "never refrigerate before peak"),
        Fruit("melon", 5.0, "once cut, halve every number"),
        Fruit("kiwi", 6.0, "hard for days, then suddenly jam"),
        Fruit("grape", 8.0, "wine is just grape happy hour"),
        Fruit("apple", 12.0, "patient; outlives several of me"),
        Fruit("orange", 14.0, "peel protects it from us both"),
    ]
}

STAGES = [
    (0.75, "green", "wait. patience is a virtue flies do not have."),
    (PEAK, "nearly ripe", "tomorrow-ish. keep it out of the sun."),
    (FERMENT, "peak - eat me", "humans: eat today. flies: sniff, do not settle."),
    (COMPOST, "happy hour - fermenting", "flies: bar is open. humans: bread, smoothie, jam."),
    (math.inf, "compost", "let it go. compost feeds the next generation."),
]


def rate(temp_c: float) -> float:
    """Ripening rate relative to REF_C. Monotonic up to CAP_C, then flat."""
    t = min(float(temp_c), CAP_C)
    if t <= BASE_C:
        return 0.03
    r = Q10 ** ((t - REF_C) / 10.0)
    if t < 10.0:  # cold chain slows things more than Q10 alone suggests
        r *= 0.35 + 0.065 * (t - BASE_C)
    return max(0.03, r)


def find_fruit(name: str) -> Fruit:
    key = name.strip().lower()
    if key in FRUITS:
        return FRUITS[key]
    hits = sorted(k for k in FRUITS if k.startswith(key))
    if len(hits) == 1:
        return FRUITS[hits[0]]
    raise KeyError(name)


def progress_after(fruit: Fruit, days: float, temp_c: float, start: float = 0.0) -> float:
    return start + days * rate(temp_c) / fruit.days_to_ripe


def simulate(fruit: Fruit, daily_temps, start: float = 0.0) -> float:
    """Progress after one day at each temperature in daily_temps."""
    p = start
    for t in daily_temps:
        p += rate(t) / fruit.days_to_ripe
    return p


def days_to_reach(fruit: Fruit, target: float, current: float = 0.0, temp_c: float = 22.0) -> float:
    if target <= current:
        return 0.0
    return (target - current) * fruit.days_to_ripe / rate(temp_c)


def stage(progress: float):
    for limit, name, advice in STAGES:
        if progress < limit:
            return name, advice
    raise AssertionError("unreachable")


def report(fruit: Fruit, temp_c: float, days_out: float, fridge_c: float = 5.0) -> list[str]:
    p = progress_after(fruit, days_out, temp_c)
    name, advice = stage(p)
    lines = [
        f"fruitwatch: {fruit.name} @ {temp_c:.1f} C, {days_out:.1f} day(s) out",
        f"  progress {p:.2f}  ->  {name}",
        f"  advice: {advice}",
        f"  note: {fruit.note}",
    ]
    for label, target in (("peak for humans   ", PEAK),
                          ("happy hour (flies)", FERMENT),
                          ("compost           ", COMPOST)):
        d = days_to_reach(fruit, target, p, temp_c)
        when = "now" if d <= 0 else f"in {d:.1f} d"
        lines.append(f"  {label} {when}")
    if p < FERMENT and fridge_c < temp_c:
        cold = days_to_reach(fruit, FERMENT, p, fridge_c)
        lines.append(
            f"  fridge at {fridge_c:.1f} C would delay happy hour to about {cold:.1f} d"
        )
    return lines


def forecast_table(fruit: Fruit, temps, start: float = 0.0) -> list[str]:
    rows = ["  day  temp   progress  stage"]
    p = start
    for i, t in enumerate(temps, start=1):
        p = simulate(fruit, [t], p)
        rows.append(f"  {i:>3}  {t:>4.1f}   {p:>7.2f}  {stage(p)[0]}")
    return rows


def _temps(arg: str) -> list[float]:
    return [float(x) for x in arg.replace(" ", "").split(",") if x]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ripeness & fermentation clock")
    ap.add_argument("fruit", nargs="?", help="fruit name or prefix")
    ap.add_argument("-t", "--temp", type=float, default=22.0)
    ap.add_argument("-d", "--days", type=float, default=0.0)
    ap.add_argument("--fridge", type=float, default=5.0)
    ap.add_argument("--forecast", action="store_true", help="7-day table at --temp")
    ap.add_argument("--forecast-temps", help="comma separated daily temperatures")
    ap.add_argument("--list", action="store_true", help="list known fruit")
    args = ap.parse_args(argv)

    if args.list or not args.fruit:
        print("known fruit (days to peak at 20 C):")
        for f in sorted(FRUITS.values(), key=lambda f: f.days_to_ripe):
            print(f"  {f.name:<11} {f.days_to_ripe:>5.1f}   {f.note}")
        return 0

    try:
        fruit = find_fruit(args.fruit)
    except KeyError:
        print(f"unknown fruit: {args.fruit!r}. try --list")
        return 2

    print("\n".join(report(fruit, args.temp, args.days, args.fridge)))
    if args.forecast or args.forecast_temps:
        temps = _temps(args.forecast_temps) if args.forecast_temps else [args.temp] * 7
        start = progress_after(fruit, args.days, args.temp)
        print("\n".join(forecast_table(fruit, temps, start)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
