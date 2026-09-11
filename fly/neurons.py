"""Named neuron populations the fly can stimulate.

FlyWire root IDs come from the upstream benchmark experiments (Shiu et al.):
sugar-sensing gustatory receptor neurons and the P9 descending neurons that
drive forward walking. Additional senses can be declared in
`data/fly_senses.json` as {"name": {"ids": [...], "rate_hz": 100}}.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent / "code"


@dataclass(frozen=True)
class Sense:
    name: str
    flywire_ids: tuple[int, ...]
    rate_hz: float
    meaning: str


def _upstream_experiments() -> dict:
    """Import EXPERIMENTS from the upstream benchmark module if importable."""
    if str(CODE_DIR) not in sys.path:
        sys.path.insert(0, str(CODE_DIR))
    try:
        from benchmark import EXPERIMENTS  # type: ignore
        return EXPERIMENTS
    except Exception:  # pragma: no cover - only when upstream code is missing
        return {}


SUGAR_GRN_IDS = (
    720575940624963786, 720575940630233916, 720575940637568838,
    720575940638202345, 720575940617000768, 720575940630797113,
    720575940632889389, 720575940621754367, 720575940621502051,
    720575940640649691, 720575940639332736, 720575940616885538,
    720575940639198653, 720575940639259967, 720575940617937543,
    720575940632425919, 720575940633143833, 720575940612670570,
    720575940628853239, 720575940629176663, 720575940611875570,
)
P9_IDS = (720575940627652358, 720575940635872101)


def default_senses() -> dict[str, Sense]:
    exps = _upstream_experiments()
    sugar = tuple(exps.get("sugar", {}).get("neu_exc") or SUGAR_GRN_IDS)
    p9 = tuple(exps.get("p9", {}).get("neu_exc") or P9_IDS)
    return {
        "sugar": Sense(
            "sugar", sugar, 200.0,
            "sugar-sensing gustatory neurons: appetite, reward, the urge to consume and launch",
        ),
        "walk": Sense(
            "walk", p9, 100.0,
            "P9 descending neurons: forward walking, exploration, browsing",
        ),
    }


def load_senses(extra_path: Path | None = None) -> dict[str, Sense]:
    senses = default_senses()
    if extra_path and extra_path.is_file():
        try:
            raw = json.loads(extra_path.read_text(encoding="utf-8"))
        except ValueError:
            raw = {}
        for name, spec in (raw or {}).items():
            ids = tuple(int(i) for i in spec.get("ids", []))
            if ids:
                senses[name] = Sense(
                    name, ids, float(spec.get("rate_hz", 100.0)), spec.get("meaning", name)
                )
    return senses
