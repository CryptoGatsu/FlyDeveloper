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
    curiosity_w = _hours_pressure(world.hours_since_browse, 6.0)
    craft_w = 0.6 * _hours_pressure(world.hours_since_build, 24.0) + 0.4 * _squash(world.unread_notes, 3, 2)
    humor_w = _hours_pressure(world.hours_since_meme, 12.0)
    appetite_w = 0.5 * _squash(world.unlaunched_memes, 1, 1) + 0.5 * _hours_pressure(world.hours_since_launch, 72.0)
    if world.launches_today >= world.max_launches_per_day:
        appetite_w *= 0.1
    if world.genesis_pending and world.launch_armed:
        appetite_w = max(appetite_w, 0.95)   # the urge to hatch its own coin

    drives = Drives(
        curiosity=0.5 * curiosity_t + 0.5 * curiosity_w,
        craft=0.5 * craft_t + 0.5 * craft_w,
        humor=0.5 * humor_t + 0.5 * humor_w,
        appetite=0.5 * appetite_t + 0.5 * appetite_w,
        boldness=boldness_t,
        fatigue=0.15,
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
    # Launching needs material: a meme the fly has not launched yet, unless
    # it is about to hatch its own genesis coin (it draws that meme itself).
    if world.genesis_pending and world.launch_armed:
        scores["launch"] = max(scores["launch"], 2.0)
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
