"""fogcast - dew point, condensation risk, and a clear-in countdown.

Stdlib only. Physics: Magnus-Tetens dew point, psychrometric wet bulb,
Newton cooling warm-up toward the wet bulb (a fogged surface is wet, so it
warms toward the wet-bulb temperature, not the air temperature).
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Optional

# Alduchov-Eskridge coefficients for the Magnus formula.
A = 17.625
B = 243.04  # degrees C

E0 = 6.112      # hPa, saturation vapour pressure at 0 C
PSYCHRO = 0.6748  # hPa/K: psychrometer constant 6.66e-4/K times 1013.25 hPa

# key -> (thermal time constant in seconds, human description)
OBJECTS = {
    "glasses": (90.0, "plastic eyeglass lenses"),
    "mirror": (240.0, "bathroom mirror"),
    "phone": (300.0, "phone screen"),
    "camera": (600.0, "camera lens front element"),
    "can": (900.0, "chilled drink can"),
    "window": (1200.0, "single-pane window glass"),
    "fruit": (2400.0, "an apple-sized fruit"),
}


def _gamma(temp_c: float, rh: float) -> float:
    return math.log(rh / 100.0) + (A * temp_c) / (B + temp_c)


def dew_point(air_c: float, rh: float) -> float:
    """Dew point in C for air at air_c with relative humidity rh (0 < rh <= 100]."""
    if not 0.0 < rh <= 100.0:
        raise ValueError("relative humidity must be in (0, 100]")
    if air_c <= -B:
        raise ValueError("air temperature out of range")
    g = _gamma(air_c, rh)
    return (B * g) / (A - g)


def sat_vapour_pressure(temp_c: float) -> float:
    """Saturation vapour pressure in hPa (same Magnus coefficients as dew_point)."""
    if temp_c <= -B:
        raise ValueError("temperature out of range")
    return E0 * math.exp((A * temp_c) / (B + temp_c))


def wet_bulb(air_c: float, rh: float, tol: float = 1e-9) -> float:
    """Wet-bulb temperature in C, by bisection on the psychrometric equation.

    e = es(Tw) - PSYCHRO * (T - Tw).  The root always sits between the dew
    point (where the right side is too small) and the air temperature (too big),
    and es is monotonic, so plain bisection is enough and never diverges.
    """
    lo = dew_point(air_c, rh)       # f(lo) <= 0
    hi = air_c                      # f(hi) >= 0
    e = (rh / 100.0) * sat_vapour_pressure(air_c)
    for _ in range(100):
        if hi - lo < tol:
            break
        mid = 0.5 * (lo + hi)
        if sat_vapour_pressure(mid) - PSYCHRO * (air_c - mid) - e > 0.0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi)


def max_safe_rh(air_c: float, surface_c: float) -> float:
    """Highest relative humidity (%) that keeps surface_c above the dew point."""
    if surface_c >= air_c:
        return 100.0
    rh = 100.0 * math.exp(
        (A * surface_c) / (B + surface_c) - (A * air_c) / (B + air_c)
    )
    return min(100.0, max(0.0, rh))


def warm_up_seconds(surface_c: float, drive_c: float, target_c: float, tau_s: float) -> Optional[float]:
    """Seconds for a surface to warm from surface_c toward drive_c and reach target_c.

    drive_c is the temperature the surface is actually relaxing toward: air
    temperature for a dry surface, wet-bulb temperature for a wet one.
    Returns 0.0 if already there, None if drive_c can never get it there.
    """
    if tau_s <= 0:
        raise ValueError("tau must be positive")
    if surface_c >= target_c:
        return 0.0
    if drive_c <= target_c:
        return None  # asymptote sits below the target: it stays wet
    return -tau_s * math.log((target_c - drive_c) / (surface_c - drive_c))


def human_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "never (this air cannot dry it)"
    seconds = int(round(seconds))
    if seconds < 60:
        return "%d s" % seconds
    return "%d min %02d s" % (seconds // 60, seconds % 60)


@dataclass
class Forecast:
    air_c: float
    rh: float
    surface_c: float
    dew_c: float
    margin_c: float          # surface - dew point; negative means wet
    fogging: bool
    label: str
    tau_s: float
    wet_bulb_c: float
    clear_in_s: Optional[float]
    max_rh: float
    frost: bool

    def report(self) -> str:
        lines = ["", "fogcast \u2014 %s" % self.label]
        lines.append("  air            %.1f C at %.0f%% RH" % (self.air_c, self.rh))
        lines.append("  %s      %.1f C" % ("frost point" if self.frost else "dew point  ", self.dew_c))
        side = "BELOW" if self.margin_c < 0 else "above"
        lines.append(
            "  surface        %.1f C  (%.1f C %s %s point)"
            % (self.surface_c, abs(self.margin_c), side, "frost" if self.frost else "dew")
        )
        if self.fogging:
            what = "Frost/rime" if self.frost else "Condensation"
            lines.append("  verdict        FOGGING. %s forms on contact with this air." % what)
            lines.append(
                "  clear in       ~%s (wet bulb %.1f C, thermal time constant %.0f s)"
                % (human_time(self.clear_in_s), self.wet_bulb_c, self.tau_s)
            )
        else:
            lines.append("  verdict        CLEAR. %.1f C of margin." % self.margin_c)
        lines.append(
            "  dry-air tip    keep RH under %.0f%% to stop condensation on a %.1f C surface"
            % (self.max_rh, self.surface_c)
        )
        if self.label == OBJECTS["fruit"][1] and self.fogging:
            lines.append("  fly note       wet skin molds. Dry it, or let it warm in the bag first.")
        lines.append("")
        return "\n".join(lines)


def forecast(air_c: float, rh: float, surface_c: float, obj: str = "glasses",
             tau_s: Optional[float] = None, safety_c: float = 0.5) -> Forecast:
    """Full condensation forecast for a cold surface meeting warm damp air."""
    if obj not in OBJECTS and tau_s is None:
        raise ValueError("unknown object %r; pass tau_s" % obj)
    default_tau, label = OBJECTS.get(obj, (600.0, obj))
    tau = float(tau_s) if tau_s is not None else default_tau
    dew = dew_point(air_c, rh)
    wb = wet_bulb(air_c, rh)
    margin = surface_c - dew
    fogging = margin < 0
    # A fogged surface is wet, so evaporation holds it near the wet bulb.
    clear = warm_up_seconds(surface_c, wb, dew + safety_c, tau) if fogging else 0.0
    return Forecast(
        air_c=air_c, rh=rh, surface_c=surface_c, dew_c=dew, margin_c=margin,
        fogging=fogging, label=label, tau_s=tau, wet_bulb_c=wb, clear_in_s=clear,
        max_rh=max_safe_rh(air_c, surface_c), frost=dew < 0.0,
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fogcast",
        description="Will it fog? Will it sweat? How long until it's clear?",
    )
    p.add_argument("--air", type=float, required=True, help="air temperature, C")
    p.add_argument("--rh", type=float, required=True, help="relative humidity, %% (0-100]")
    p.add_argument("--surface", type=float, required=True, help="cold surface temperature, C")
    p.add_argument("--object", default="glasses", help="one of: " + ", ".join(sorted(OBJECTS)))
    p.add_argument("--tau", type=float, default=None, help="thermal time constant override, s")
    p.add_argument("--safety", type=float, default=0.5, help="margin above dew point, C")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        f = forecast(args.air, args.rh, args.surface, args.object, args.tau, args.safety)
    except ValueError as exc:
        print("fogcast: %s" % exc)
        return 2
    print(f.report())
    return 1 if f.fogging else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
