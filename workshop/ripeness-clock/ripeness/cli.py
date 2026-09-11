"""Command line interface for Ripeness Clock."""

import argparse
import datetime as _dt

from . import model as m


def parse_temps(text, days):
    """Parse a comma separated temperature list, repeating the last value."""
    if days <= 0:
        return []
    parts = [p.strip() for p in str(text).split(",") if p.strip()]
    if not parts:
        raise ValueError("no temperatures given")
    vals = [float(p) for p in parts]
    while len(vals) < days:
        vals.append(vals[-1])
    return vals[:days]


def fruit_table():
    lines = ["fruit         ripe  peak  over  compost  chill-floor (days @20C)"]
    for name in sorted(m.FRUITS):
        f = m.FRUITS[name]
        lines.append(
            "%-12s %5.1f %5.1f %5.1f %8.1f %8.1f"
            % (f.name, f.to_ripe, f.to_peak, f.to_overripe, f.to_compost, f.chill_floor)
        )
    return "\n".join(lines)


def report(fruit, bought, today, temps):
    days = (today - bought).days
    units = m.accumulate(fruit, temps)
    st = m.stage(fruit, units)
    mean_t = sum(temps) / len(temps) if temps else 20.0
    out = []
    out.append(
        "%s | bought %s | %d day(s) at %.1f \u00b0C"
        % (fruit.name, bought.isoformat(), days, mean_t)
    )
    out.append("ripeness %.2f units  %s" % (units, m.progress_bar(fruit, units)))
    out.append("stage: %s - %s" % (st.upper(), m.human_advice(st)))
    nxt = m.next_stage(st)
    if nxt is None:
        out.append("next: nothing left to become.")
    else:
        d = m.days_until(fruit, units, nxt, mean_t)
        if d is None:
            out.append("next: %s never, at this temperature (cold storage)." % nxt)
        else:
            when = today + _dt.timedelta(days=int(round(d)))
            out.append(
                "next: %s in %.1f day(s) (about %s)" % (nxt, d, when.isoformat())
            )
    if any(t > m.HEAT_CAP_C for t in temps):
        out.append("warning: it got hotter than 35 \u00b0C - expect heat damage, not ripening.")
    out.append("fly note: %s" % m.fly_advice(st))
    return "\n".join(out)


def build_parser():
    p = argparse.ArgumentParser(
        prog="ripeness", description="Estimate how far along your fruit is."
    )
    p.add_argument("fruit", nargs="?", help="fruit name (see --list)")
    p.add_argument("--bought", help="purchase/harvest date, YYYY-MM-DD")
    p.add_argument("--today", help="date to evaluate, YYYY-MM-DD (default: today)")
    p.add_argument(
        "--temp",
        default="20",
        help="storage temperature(s) in C, comma separated, one per day",
    )
    p.add_argument("--list", action="store_true", help="list known fruits and exit")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.list:
        print(fruit_table())
        return 0
    if not args.fruit:
        print("give me a fruit, or --list. Example: ripeness banana --bought 2024-06-01")
        return 2
    key = args.fruit.strip().lower()
    if key not in m.FRUITS:
        print("unknown fruit %r. Known: %s" % (args.fruit, ", ".join(sorted(m.FRUITS))))
        return 2
    today = _dt.date.fromisoformat(args.today) if args.today else _dt.date.today()
    bought = _dt.date.fromisoformat(args.bought) if args.bought else today
    days = (today - bought).days
    if days < 0:
        print("the fruit has not been bought yet. Time flies, but not backwards.")
        return 2
    try:
        temps = parse_temps(args.temp, days)
    except ValueError as exc:
        print("bad --temp: %s" % exc)
        return 2
    print(report(m.FRUITS[key], bought, today, temps))
    return 0
