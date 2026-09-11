"""Command line for the fly."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import FlyConfig


def _fly(args):
    from .agent import Fly

    cfg = FlyConfig.from_env()
    if getattr(args, "brain", None):
        cfg.brain.mode = args.brain
    if getattr(args, "mind", None):
        cfg.mind.mode = args.mind
    if getattr(args, "t_run", None):
        cfg.brain.t_run_sec = args.t_run
    return Fly(cfg)


def cmd_status(args) -> int:
    cfg = FlyConfig.from_env()
    print(f"FlyDeveloper {__version__}")
    print(f"brain: {cfg.brain.mode} (t_run {cfg.brain.t_run_sec}s)")
    print(f"mind: {cfg.mind.mode} ({cfg.mind.model}, effort {cfg.mind.effort})")
    print(f"launchpad: chain {cfg.launchpad.chain_id} factory {cfg.launchpad.factory} live={cfg.launchpad.live} wallet={'set' if cfg.launchpad.private_key else 'unset'}")
    print(f"image host: {cfg.hosting.provider}")
    from .memory import Memory

    mem = Memory.load(cfg.memory_path)
    print("memory:\n" + mem.summary())
    return 0


def cmd_brain(args) -> int:
    fly = _fly(args)
    reports = fly.perceive(seed=args.seed)
    from .drives import compute_drives, choose_action

    world = fly.world()
    drives = compute_drives(reports, world, fly.brain.connectome.calibration)
    for r in reports.values():
        print(r.describe())
    print("drives:", drives.describe())
    action, probs = choose_action(drives, world, "".join(r.fingerprint() for r in reports.values()))
    print("would:", action, probs)
    return 0


def cmd_tick(args) -> int:
    fly = _fly(args)
    result = fly.tick(force=args.force, seed=args.seed, live=args.live)
    print(result.describe())
    return 0


def cmd_live(args) -> int:
    fly = _fly(args)
    fly.run(ticks=args.ticks, interval_sec=args.interval, live=args.live)
    return 0


def cmd_meme(args) -> int:
    from .memes import render_meme

    out = Path(args.out) if args.out else FlyConfig.from_env().memes_dir / "fly-manual.png"
    render_meme(args.top, args.bottom or "", out, seed=args.seed, mood=args.mood)
    print(out)
    return 0


def cmd_launch_status(args) -> int:
    from .launchpad import PonsLaunchpad

    cfg = FlyConfig.from_env()
    lp = PonsLaunchpad(cfg.launchpad)
    print(json.dumps(lp.status(), indent=2, default=str))
    return 0


def cmd_launch(args) -> int:
    fly = _fly(args)
    from .drives import Drives

    drives = Drives(0.5, 0.5, 0.5, 0.9, 0.7, 0.1)
    meme = None
    if args.meme:
        meme = {"path": args.meme, "top": args.top or "FLY", "bottom": args.bottom or "", "mood": args.mood}
    outcome = fly.act_launch(drives, live=args.live, meme=meme)
    fly.memory.save()
    print(outcome["launch"])
    return 0 if outcome["status"] in ("planned", "confirmed") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fly", description="A fly that builds, browses, memes and launches.")
    p.add_argument("--brain", choices=["connectome", "phantom"], help="override FLY_BRAIN")
    p.add_argument("--mind", choices=["claude", "offline"], help="override FLY_MIND")
    p.add_argument("--t-run", type=float, dest="t_run", help="simulated seconds per perception")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show configuration and memory").set_defaults(fn=cmd_status)
    b = sub.add_parser("brain", help="stimulate the connectome and print drives")
    b.add_argument("--seed", type=int)
    b.set_defaults(fn=cmd_brain)
    t = sub.add_parser("tick", help="one heartbeat: perceive, decide, act")
    t.add_argument("--force", choices=["browse", "build", "meme", "launch", "rest"])
    t.add_argument("--seed", type=int)
    t.add_argument("--live", action="store_true", help="allow a real launch (also needs FLY_LIVE_LAUNCH=1)")
    t.set_defaults(fn=cmd_tick)
    l = sub.add_parser("live", help="keep ticking")
    l.add_argument("--ticks", type=int)
    l.add_argument("--interval", type=int)
    l.add_argument("--live", action="store_true")
    l.set_defaults(fn=cmd_live)
    m = sub.add_parser("meme", help="render a meme by hand")
    m.add_argument("top")
    m.add_argument("bottom", nargs="?")
    m.add_argument("--mood", default="curious")
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--out")
    m.set_defaults(fn=cmd_meme)
    sub.add_parser("launch-status", help="read the Pons factory state").set_defaults(fn=cmd_launch_status)
    la = sub.add_parser("launch", help="plan (or, with --live, send) a memecoin launch")
    la.add_argument("--meme", help="path to a meme png to use as the logo")
    la.add_argument("--top")
    la.add_argument("--bottom")
    la.add_argument("--mood", default="curious")
    la.add_argument("--live", action="store_true")
    la.set_defaults(fn=cmd_launch)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
