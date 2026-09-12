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


def describe_temp(temp_c: float) -> str:
    """Turn a number into somewhere that actually exists in a kitchen."""
    if temp_c <= 6.0:
        return "the fridge"
    if temp_c < 12.0:
        return "a cold pantry, cellar, or unheated hall"
    if temp_c < 18.0:
        return "a cool room or a shaded shelf"
    if temp_c < 24.0:
        return "normal room temperature, out on the counter"
    if temp_c < 30.0:
        return "a warm spot: on top of the fridge, or a sunny sill"
    return "very warm: a closed paper bag somewhere sunny"


def chill_note(rep: dict) -> str | None:
    """Say the thing the degree-day arithmetic cannot say by itself."""
    floor = rep["chill_safe_c"]
    if rep["temp_c"] >= floor:
        return None
    if rep["chill_risk"]:
        return (
            f"  chill     {rep['temp_c']:.1f}°C is under {rep['fruit']}'s "
            f"{floor:.0f}°C chill line: while it is still\n"
            "            firm, this cold can stop ripening for good, even back "
            "on the counter."
        )
    return (
        f"  chill     under {rep['fruit']}'s {floor:.0f}°C chill line, but it is "
        f"already {rep['stage']} —\n"
        "            cold from here only costs looks, not flavour."
    )


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
    note = chill_note(rep)
    if note:
        lines.append(note)
    lines.append("  " + ADVICE[rep["stage"]])
    return "\n".join(lines)


def format_plan(p: dict) -> str:
    lines = [
        f"{p['fruit']}: {p['degree_days']:.1f} °C·days soaked, "
        f"want {p['stage']} in {p['days']:g} days"
    ]
    if p["status"] == "passed":
        lines.append(f"  it is already at or past {p['stage']}")
        lines.append("  put it in the fridge to hold it roughly where it is")
    elif p["status"] == "too-late":
        lines.append(
            f"  not possible: even at {model.CAP_C:.0f}°C it needs "
            f"{p['earliest_days']:.1f} days"
        )
        lines.append("  buy one that is further along, or move the party")
    else:
        lines.append(
            f"  hold it at {p['temp_c']:.1f}°C  ({describe_temp(p['temp_c'])})"
        )
        if p.get("chill_risk"):
            lines.append(
                f"  but that is under {p['fruit']}'s {p['chill_safe_c']:.0f}°C "
                "chill line: firm fruit held that cold"
            )
            if p.get("counter_days") is not None:
                lines.append(
                    "  may never ripen. Use the two-step below instead — cold "
                    "after ripening is fine."
                )
            else:
                lines.append(
                    "  may never ripen. Better: a shorter warm stint, then the "
                    "fridge once it is ripe."
                )
        if p.get("counter_days") is not None:
            lines.append(
                f"  or, in a real kitchen: {p['counter_days']:.1f} days out at "
                f"{p['counter_c']:.1f}°C, then {p['fridge_days']:.1f} days "
                "in the fridge"
            )
        lines.append(f"  soonest possible, at 35°C: {p['earliest_days']:.1f} days")
        lines.append("  Fly: put it in your calendar. Bring exactly one friend.")
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
    p.add_argument("--ready-in", type=float, default=None, metavar="DAYS",
                   help="plan backwards: what temperature hits the target "
                        "stage in DAYS days")
    p.add_argument("--counter", type=float, default=None, metavar="TEMP",
                   help="your counter temperature for the counter-then-fridge "
                        "plan (default: --temp, else 21)")
    p.add_argument("--stage", default="ripe", choices=list(model.FUTURE_STAGES),
                   help="target stage for --ready-in (default: ripe)")
    p.add_argument("--list", action="store_true", help="list known fruits")
    p.add_argument("--json", action="store_true", help="machine readable output")
    return p


def _parse_temps(raw: str):
    return [float(x) for x in raw.replace(" ", "").split(",") if x]


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        for name, (ripe, feast, comp) in sorted(model.FRUITS.items()):
            floor = model.chill_floor(name)
            cold = ("fridge-safe any time" if floor <= model.BASE_C
                    else f"keep above {floor:.0f}°C until ripe")
            print(f"{name:<12} ripe {ripe:>6.0f}  fly-feast {feast:>6.0f} "
                  f" compost {comp:>6.0f}  °C·days   ({cold})")
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
        ahead = args.temp if args.temp is not None else model.ROOM_C
        soaked = model.daily_rate(ahead) * max(0.0, args.days)

    room = ahead  # before --fridge overrides the forecast
    if args.fridge:
        ahead = model.BASE_C

    counter = args.counter if args.counter is not None else room

    try:
        if args.ready_in is not None:
            if args.ready_in <= 0:
                print("--ready-in needs a positive number of days",
                      file=sys.stderr)
                return 2
            result = model.plan(args.fruit, soaked, args.ready_in,
                                args.stage, counter)
            text = format_plan(result)
        else:
            result = model.forecast(args.fruit, soaked, ahead)
            text = format_report(result)
    except model.UnknownFruit:
        print(f"unknown fruit: {args.fruit} (try --list)", file=sys.stderr)
        return 2

    print(json.dumps(result) if args.json else text)
    return 0
