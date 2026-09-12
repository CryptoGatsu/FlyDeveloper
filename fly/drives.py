"""Turn spike statistics and world pressure into drives, and drives into a
choice of action.

The connectome supplies temperament (how broadly a sugar stimulus spreads
today, how bursty the walking circuit is, how irregular the spike trains
are). The world supplies pressure (how long since the fly last built
something, whether it has memes it never launched). Neither alone decides;
the policy samples an action from the combination, seeded by the spike
fingerprint so a given brain state always makes the same call.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, asdict

import numpy as np

from .brain import SpikeReport

ACTIONS = ("browse", "build", "meme", "launch", "rest")


@dataclass
class WorldSignals:
    hours_since_browse: float = 1e6
    hours_since_build: float = 1e6
    hours_since_meme: float = 1e6
    hours_since_launch: float = 1e6
    unread_notes: int = 0
    unlaunched_memes: int = 0
    launches_today: int = 0
    max_launches_per_day: int = 1
    launch_armed: bool = False
    genesis_pending: bool = False   # the fly has not launched its own coin yet
    actions_last_hour: int = 0      # how busy it has been; feeds fatigue
    actions_today: int = 0
    max_actions_per_day: int = 80


@dataclass
class Drives:
    curiosity: float   # want to browse
    craft: float       # want to build
    humor: float       # want to draw memes
    appetite: float    # want to launch
    boldness: float    # risk tolerance
    fatigue: float     # want to rest

    def as_dict(self) -> dict[str, float]:
        return {k: round(float(v), 4) for k, v in asdict(self).items()}

    def describe(self) -> str:
        return ", ".join(f"{k} {v:.2f}" for k, v in self.as_dict().items())


def _squash(x: float, mid: float, width: float) -> float:
    """Logistic squash of x into (0, 1) centred on `mid`."""
    if width <= 0:
        return 1.0 if x >= mid else 0.0
    return 1.0 / (1.0 + math.exp(-(x - mid) / width))


def _hours_pressure(hours: float, half_life_h: float) -> float:
    """0 right after doing something, approaching 1 as hours pass."""
    return 1.0 - math.exp(-max(0.0, hours) / half_life_h)


def compute_drives(reports: dict[str, SpikeReport], world: WorldSignals, calibration: dict[str, float] | None = None) -> Drives:
    sugar = reports.get("sugar")
    walk = reports.get("walk")

    # Temperament from the connectome. Breadth values are tiny fractions of
    # the brain (a sugar stimulus recruits a few hundred to a few thousand of
    # ~138k neurons), so the squash midpoints are set in that regime.
    cal = {"sugar_mid": 0.002, "sugar_w": 0.0008, "walk_mid": 0.0002, "walk_w": 0.0001}
    cal.update(calibration or {})
    appetite_t = _squash(sugar.breadth, cal["sugar_mid"], cal["sugar_w"]) if sugar else 0.5
    curiosity_t = _squash(walk.breadth, cal["walk_mid"], cal["walk_w"]) if walk else 0.5
    irregularity = float(np.mean([r.isi_cv for r in reports.values()])) if reports else 0.5
    humor_t = _squash(irregularity, 0.5, 0.2)
    persistence = float(np.mean([r.persistence for r in reports.values()])) if reports else 1.0
    craft_t = _squash(persistence, 1.0, 0.3)
    burst = float(np.mean([r.burstiness for r in reports.values()])) if reports else 1.0
    boldness_t = _squash(burst, 1.0, 0.4)

    # Pressure from the world.
    curiosity_w = _hours_pressure(world.hours_since_browse, 1.0)   # a fly gets itchy antennae within the hour
    craft_w = 0.6 * _hours_pressure(world.hours_since_build, 24.0) + 0.4 * _squash(world.unread_notes, 3, 2)
    humor_w = _hours_pressure(world.hours_since_meme, 12.0)
    appetite_w = 0.5 * _squash(world.unlaunched_memes, 1, 1) + 0.5 * _hours_pressure(world.hours_since_launch, 72.0)
    if world.launches_today >= world.max_launches_per_day:
        appetite_w *= 0.1
    if world.genesis_pending and world.launch_armed:
        appetite_w = max(appetite_w, 0.95)   # the urge to hatch its own coin

    fatigue = min(0.9, 0.12 + 0.09 * world.actions_last_hour)
    if world.actions_today >= world.max_actions_per_day:
        fatigue = 0.95                      # out of budget for today: it will mostly rest
    drives = Drives(
        curiosity=0.5 * curiosity_t + 0.5 * curiosity_w,
        craft=0.5 * craft_t + 0.5 * craft_w,
        humor=0.5 * humor_t + 0.5 * humor_w,
        appetite=0.5 * appetite_t + 0.5 * appetite_w,
        boldness=boldness_t,
        fatigue=fatigue,
    )
    return drives


def choose_action(drives: Drives, world: WorldSignals, fingerprint: str, temperature: float = 0.35) -> tuple[str, dict[str, float]]:
    """Softmax over action scores, sampled with a seed derived from the brain
    state so the same spikes always pick the same action."""
    scores = {
        "browse": drives.curiosity,
        "build": drives.craft,
        "meme": drives.humor,
        "launch": drives.appetite * (0.4 + 0.6 * drives.boldness),
        "rest": drives.fatigue,
    }
    # Itchy antennae: past an hour without browsing the urge grows until it
    # wins outright, so the fly is never off the web for long.
    if world.hours_since_browse >= 1.0:
        scores["browse"] += min(1.5, 0.8 * (world.hours_since_browse - 1.0) + 0.4)
    # Launching needs material: a meme the fly has not launched yet, unless
    # it is about to hatch its own genesis coin (it draws that meme itself).
    if world.genesis_pending and world.launch_armed:
        scores["launch"] = max(scores.values()) + 1.5      # nothing outranks hatching its own coin
    elif world.unlaunched_memes == 0:
        scores["launch"] *= 0.15
    if world.launches_today >= world.max_launches_per_day:
        scores.pop("launch")

    names = list(scores)
    logits = np.array([scores[n] / max(temperature, 1e-6) for n in names])
    probs = np.exp(logits - logits.max())
    probs /= probs.sum()
    if "launch" not in scores:
        names.append("launch")
        probs = np.append(probs, 0.0)
    seed = int(hashlib.sha256(fingerprint.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    action = str(rng.choice(names, p=probs))
    return action, {n: round(float(p), 4) for n, p in zip(names, probs)}


# How long the fly rests after an action, in seconds, before its brain decides
# again. Light actions come back quickly; heavy ones earn a longer nap. Fatigue
# stretches every rest; the spike fingerprint adds jitter so it is never metronomic.
# Typical rest after each action, in seconds. The fly is a fly: it naps in
# minutes, not hours. Fatigue stretches these; the ceiling caps them.
BASE_REST_SEC = {"browse": 120, "meme": 120, "build": 240, "repair": 180, "improve": 180,
                 "launch": 240, "website": 240, "rest": 150, "brand": 180}
MAX_REST_SEC = 300


def next_rest_sec(action: str, drives: Drives, fingerprint: str = "", floor: int = 60, ceiling: int = MAX_REST_SEC) -> int:
    base = BASE_REST_SEC.get(action, 150)
    stretch = 0.6 + 1.8 * drives.fatigue                    # 0.6x when fresh, ~2.2x when worn out
    seed = int(hashlib.sha256((fingerprint or action).encode()).hexdigest()[:8], 16)
    jitter = 0.75 + (seed % 1000) / 2000.0                  # 0.75x .. 1.25x
    return int(max(floor, min(ceiling, base * stretch * jitter)))