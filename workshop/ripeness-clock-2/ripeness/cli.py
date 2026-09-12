"""Command line front end for the Ripeness Clock."""

from __future__ import annotations

import argparse
import json
import sys

from . import model

ADVICE = {
    "firm": "Humans: wait. Flies: come back later, bring friends.",
    "ripe": "Eat it now, human. Fly: hover politely, wait your turn.",
    "fly-feast": "Human: bake it, blend it, or share it. Fly: dinner is served.",
    "compost": "Compost it kindly. The next generation of larvae thanks you.",
}


def bar(degree_days: float, compost: float, width: int = 16) -> str:
    if compost <= 0:
        return "░" * width
    filled = int(min(1.0, max(0.0, degree_days / compost)) * width)
    return "▓" * filled + "░" * (width - filled)


def format_report(rep: dict) -> str:
    _, _, compost = model.thresholds(rep["fruit"])
    lines = [f"{rep['fruit']} at {rep['temp_c']:.1f}°C"]
    lines.append(
        f"  soak      {rep['degree_days']:.1f} °C·days  "
        f"{bar(rep['degree_days'], compost)}"
    )
    lines.append(f"  stage     {rep['stage']}")
    for stage in model.FUTURE_STAGES:
        eta = rep["eta_days"][stage]
        if eta is None:
            text = "never at this temperature (ripening stalled)"
        elif eta == 0.0:
            text = "already there"
        else:
            text = f"in {eta:.1f} days"
        lines.append(f"  {stage:<10} {text}")
    lines.append("  " + ADVICE[rep["stage"]])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ripeness",
        description="Degree-day ripeness estimates for fruit on the counter.",
    )
    p.add_argument("fruit", nargs="?", help="e.g. banana, avocado, tomato")
    p.add_argument("--days", type=float, default=0.0,
                   help="days it has already sat (with --temp)")
    p.add_argument("--temp", type=float, default=None,
                   help="steady temperature in C (default 21)")
    p.add_argument("--temps", default=None,
                   help="comma separated past daily temps, e.g. 26,26,19,8")
    p.add_argument("--fridge", action="store_true",
                   help="forecast ahead at fridge temperature (4 C)")
    p.add_argument("--list", action="store_true", help="list known fruits")
    p.add_argument("--json", action="store_true", help="machine readable output")
    return p


def _parse_temps(raw: str):
    return [float(x) for x in raw.replace(" ", "").split(",") if x]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        for name, (ripe, feast, comp) in sorted(model.FRUITS.items()):
            print(f"{name:<12} ripe {ripe:>6.0f}  fly-feast {feast:>6.0f} "
                  f" compost {comp:>6.0f}  °C·days")
        return 0

    if not args.fruit:
        print("need a fruit (try --list)", file=sys.stderr)
        return 2

    history = None
    if args.temps:
        try:
            history = _parse_temps(args.temps)
        except ValueError:
            print("--temps must be numbers, e.g. 26,26,19", file=sys.stderr)
            return 2

    if history:
        soaked = model.accumulate(history)
        ahead = args.temp if args.temp is not None else history[-1]
    else:
        ahead = args.temp if args.temp is not None else 21.0
        soaked = model.daily_rate(ahead) * max(0.0, args.days)

    if args.fridge:
        ahead = model.BASE_C

    try:
        rep = model.forecast(args.fruit, soaked, ahead)
    except model.UnknownFruit:
        print(f"unknown fruit: {args.fruit} (try --list)", file=sys.stderr)
        return 2

    print(json.dumps(rep) if args.json else format_report(rep))
    return 0
