import numpy as np

from fly.brain import Connectome, FlyBrain
from fly.drives import ACTIONS, WorldSignals, choose_action, compute_drives


def _reports():
    c = Connectome.synthetic(1000, seed=1)
    b = FlyBrain(c)
    return {
        "sugar": b.run("sugar", np.arange(20), 200.0, 0.03, seed=1),
        "walk": b.run("walk", np.arange(50, 52), 100.0, 0.03, seed=2),
    }, c.calibration


def test_drives_in_unit_range():
    reports, cal = _reports()
    d = compute_drives(reports, WorldSignals(), cal)
    for v in d.as_dict().values():
        assert 0.0 <= v <= 1.0


def test_world_pressure_raises_craft():
    reports, cal = _reports()
    fresh = compute_drives(reports, WorldSignals(hours_since_build=0.0), cal)
    stale = compute_drives(reports, WorldSignals(hours_since_build=100.0, unread_notes=5), cal)
    assert stale.craft > fresh.craft


def test_launch_cap_blocks_launch():
    reports, cal = _reports()
    world = WorldSignals(launches_today=1, max_launches_per_day=1, unlaunched_memes=3)
    d = compute_drives(reports, world, cal)
    action, probs = choose_action(d, world, "abc")
    assert probs["launch"] == 0.0
    assert action in ACTIONS and action != "launch"


def test_choice_is_deterministic_per_fingerprint():
    reports, cal = _reports()
    world = WorldSignals(unlaunched_memes=1)
    d = compute_drives(reports, world, cal)
    a1, _ = choose_action(d, world, "deadbeef")
    a2, _ = choose_action(d, world, "deadbeef")
    assert a1 == a2


def test_genesis_urge_makes_launch_dominant():
    reports, cal = _reports()
    world = WorldSignals(launch_armed=True, genesis_pending=True, unlaunched_memes=0)
    d = compute_drives(reports, world, cal)
    action, probs = choose_action(d, world, "any-fingerprint")
    assert action == "launch"
    assert probs["launch"] > 0.8
    calm = WorldSignals(launch_armed=False, genesis_pending=True, unlaunched_memes=0)
    _, probs2 = choose_action(compute_drives(reports, calm, cal), calm, "x")
    assert probs2["launch"] < 0.2      # not armed: no urge, no material


def test_fatigue_grows_with_activity_and_rest_scales():
    from fly.drives import Drives, next_rest_sec
    reports, cal = _reports()
    fresh = compute_drives(reports, WorldSignals(actions_last_hour=0), cal)
    busy = compute_drives(reports, WorldSignals(actions_last_hour=6), cal)
    spent = compute_drives(reports, WorldSignals(actions_today=80, max_actions_per_day=80), cal)
    assert fresh.fatigue < busy.fatigue < spent.fatigue
    assert next_rest_sec("browse", fresh, "a") < next_rest_sec("build", fresh, "a")
    assert next_rest_sec("browse", fresh, "a") < next_rest_sec("browse", spent, "a")
    for a in ("browse", "build", "launch", "website", "rest", "unknown"):
        assert 60 <= next_rest_sec(a, busy, "x") <= 3600
