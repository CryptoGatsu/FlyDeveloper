"""Command line for the fly."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import FlyConfig, config_warnings


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
    from .render import find_chrome

    chrome = find_chrome()
    print(f"screenshots: {chrome if chrome else 'NO BROWSER FOUND (set FLY_CHROME in .env)'}")
    print(f"fly cam: {'on -> ' + cfg.site_url + '/api/cam' if cfg.cam_secret else 'off (set FLY_CAM_SECRET)'}")
    for w in config_warnings(cfg):
        print(f"WARNING: {w}")
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
    """Supervisor: runs the loop in a child process and brings it back after
    any crash or self-update. `--child` is the loop itself."""
    import subprocess
    import sys as _sys
    import time as _time

    if args.child or args.ticks:
        fly = _fly(args)
        return fly.run(ticks=args.ticks, interval_sec=args.interval, live=args.live)
    cmd = [_sys.executable, str(Path(__file__).resolve().parent.parent / "fly.py")]
    for flag, val in (("--brain", args.brain), ("--mind", args.mind)):
        if val:
            cmd += [flag, val]
    cmd += ["live", "--child"]
    if args.live:
        cmd.append("--live")
    if args.interval:
        cmd += ["--interval", str(args.interval)]
    backoff = 10
    while True:
        started = _time.time()
        try:
            code = subprocess.call(cmd)
        except KeyboardInterrupt:
            return 0
        if code == 2:
            return 0                                     # stopped on purpose
        if code == 0:
            print("supervisor: restarting the fly on new code")
            backoff = 10
            continue
        ran = _time.time() - started
        backoff = 10 if ran > 600 else min(600, backoff * 2)
        print(f"supervisor: the fly exited with code {code} after {int(ran)}s; back in {backoff}s")
        try:
            _time.sleep(backoff)
        except KeyboardInterrupt:
            return 0


def cmd_browse(args) -> int:
    """A browsing session you can watch: search, read, digest, remember."""
    fly = _fly(args)
    topics = args.topics or list(fly.cfg.browser.seeds)
    notes = []
    try:
        fly.browser.backfill_shots(fly.memory)
        notes = fly.browser.explore(fly.mind, fly.memory, topics, budget=args.pages)
    except KeyboardInterrupt:
        print("\nstopped early; keeping what was read so far")
    fly.memory.note(f"browsed {len(notes)} pages", topics=topics[:3])
    fly.memory.save()
    fly._publish("browse", "curious")
    print()
    print(f"read {len(notes)} pages:")
    for n in notes:
        print(f"- {n.title}\n  {n.url}\n  {n.gist}")
        if n.need_spotted:
            print(f"  need: {n.need_spotted}")
        if n.followups:
            print(f"  next: {', '.join(n.followups)}")
    return 0


def cmd_meme(args) -> int:
    from .memes import render_meme

    out = Path(args.out) if args.out else FlyConfig.from_env().memes_dir / "fly-manual.png"
    render_meme(args.top, args.bottom or "", out, seed=args.seed, mood=args.mood)
    print(out)
    return 0


def cmd_launch_status(args) -> int:
    from .hosting import check_host
    from .launchpad import PonsLaunchpad

    cfg = FlyConfig.from_env()
    lp = PonsLaunchpad(cfg.launchpad)
    print(json.dumps(lp.status(), indent=2, default=str))
    print()
    lpc = cfg.launchpad
    recipient = lpc.creator_fee_recipient or lp.address or "(the launching wallet)"
    print("genesis fee policy (locked in at launch, cannot be changed after):")
    print(f"  coin: {lpc.genesis_name} (${lpc.genesis_symbol})")
    print(f"  creator share of the 1% curve fee -> {recipient}")
    print(f"  creator tax on top: {lpc.creator_tax_bps} bps ({lpc.creator_tax_bps / 100:.2f}%) -> same wallet  [FLY_CREATOR_TAX_BPS, max 1000]")
    print(f"  buyback-and-lock: {'ON (a slice of creator fees buys the coin back)' if lpc.genesis_buyback else 'OFF (all creator fees stay in the wallet to fund the project)'}")
    if lpc.pair_is_native:
        print("  quote asset: native ETH (buyers pay ETH, creator fees accrue in ETH)  [FLY_PAIR_TOKEN]")
    else:
        print(f"  quote asset: {lpc.pair_symbol} at {lpc.pair_token} (buyers pay {lpc.pair_symbol}, creator fees accrue in {lpc.pair_symbol}; the launch fee itself is ETH)  [FLY_PAIR_TOKEN]")
    if lpc.creator_tax_bps == 0:
        print("  note: with 0 bps the wallet only earns its share of the base fee; set FLY_CREATOR_TAX_BPS (e.g. 250 = 2.5%) to fund the project")
    print()
    hosting = check_host(cfg.hosting)
    checks = lp.readiness(hosting)
    for ok, msg in checks:
        print(f"  [{'ok' if ok else '--'}] {msg}")
    ready = all(ok for ok, _ in checks)
    print("\nready for a real launch" if ready else "\nnot ready: fix the [--] lines above (dry runs still work)")
    return 0 if ready else 1


def cmd_wallet(args) -> int:
    from .launchpad import PonsLaunchpad

    cfg = FlyConfig.from_env()
    lp = PonsLaunchpad(cfg.launchpad)
    if not lp.address:
        print("no wallet: set FLY_WALLET_PRIVATE_KEY in .env (use a fresh hot wallet)")
        return 1
    print(f"address: {lp.address}")
    print(f"explorer: {cfg.launchpad.explorer}/address/{lp.address}")
    if lp.connected():
        bal = lp.w3.eth.get_balance(lp.address)
        print(f"balance: {bal / 1e18:.6f} ETH on chain {cfg.launchpad.chain_id}")
    else:
        print("rpc unreachable, balance unknown")
    return 0


def cmd_fees(args) -> int:
    """Show creator fees; optionally sweep curves and claim from escrow."""
    from .launchpad import PonsLaunchpad
    from .memory import Memory

    cfg = FlyConfig.from_env()
    lp = PonsLaunchpad(cfg.launchpad)
    mem = Memory.load(cfg.memory_path)
    curves = [l["curve"] for l in mem.data.get("launches", []) if l.get("live") and l.get("curve")]
    if args.curve:
        curves = [args.curve]
    print(json.dumps(lp.fees(curves), indent=2, default=str))
    if args.sweep:
        for c in curves:
            info = lp.fees([c])["curves"].get(c)
            if isinstance(info, dict) and info.get("buybackEnabled") and not args.min_buyback_out:
                print(f"skip sweep {c}: buyback is enabled, pass --min-buyback-out (token wei) to set a price floor")
                continue
            print(f"sweep {c}: {lp.sweep_fees(c, live=args.live, min_buyback_tokens_out=args.min_buyback_out)}")
    if args.claim:
        print(f"claim ETH: {lp.claim_fees(live=args.live)}")
        if not cfg.launchpad.pair_is_native:
            print(f"claim {cfg.launchpad.quote}: {lp.claim_fees(live=args.live, token=cfg.launchpad.pair_token)}")
    if (args.sweep or args.claim) and not (args.live and cfg.launchpad.live):
        print("(dry run: printed calldata only; add --live with FLY_LIVE_LAUNCH=1 to send)")
    return 0


def cmd_website(args) -> int:
    """The fly designs and writes its own website into site/."""
    fly = _fly(args)
    out = fly.act_website(refine=args.refine, changes=args.change or None)
    fly.memory.save()
    fly._publish("website", "scheming")
    print(f"site source: {out['website']}")
    print("files: " + ", ".join(out["files"]))
    if out["problems"]:
        print("problems with the fly's own attempt: " + "; ".join(out["problems"]))
    print(out["notes"])
    return 0


def cmd_brand(args) -> int:
    """The fly draws its X profile picture (500x500) and banner (1500x500)."""
    fly = _fly(args)
    out = fly.act_brand(seed=args.seed)
    fly.memory.save()
    print(f"pfp:    {out['pfp']}")
    print(f"banner: {out['banner']}")
    print(f"tagline: {out['tagline']}")
    print(f"bio:     {out['bio']}")
    return 0


def cmd_sync(args) -> int:
    """Pull the repo without fighting over the fly's generated files."""
    import subprocess
    import sys as _sys

    from .memory import Memory
    from .publish import export_site

    cfg = FlyConfig.from_env()
    root = str(cfg.root)

    def git(*a):
        return subprocess.run(["git", "-C", root, *a], capture_output=True, text=True)

    # generated: the fly rewrites it after every tick, so never let it block a pull
    git("checkout", "--", "site/data/state.json")
    r = git("pull", "--rebase", "--autostash", "-X", "theirs")
    print((r.stdout + r.stderr).strip()[-600:] or "up to date")
    if r.returncode != 0:
        print("pull failed; resolve the files above, then run: git rebase --continue")
        return 1
    export_site(cfg, Memory.load(cfg.memory_path))
    print("state.json regenerated from your memory; run `python fly.py publish --push` to publish it")
    if "requirements-fly.txt" in (r.stdout + r.stderr):
        print("requirements changed: installing")
        subprocess.run([_sys.executable, "-m", "pip", "install", "-q", "-r", str(cfg.root / "requirements-fly.txt")])
    return 0


def cmd_post(args) -> int:
    """Compose (and with --live, send) one X post."""
    fly = _fly(args)
    material = args.material or {"hype": "your own coin $FLYDEV; pick a fresh angle",
                                 "build": (fly.memory.last("builds") or {}).get("title", "a tiny tool"),
                                 "meme": f"{(fly.memory.last('memes') or {}).get('top', '')} / {(fly.memory.last('memes') or {}).get('bottom', '')}",
                                 "learning": (fly.memory.last("learnings") or {}).get("summary", "")}.get(args.kind, "")
    media = args.media or ((fly.memory.last("memes") or {}).get("path", "") if args.kind == "meme" else "")
    print(fly.act_post(args.kind, material, media=media, live=args.live))
    fly.memory.save()
    fly._publish("post", "smug")
    return 0


def cmd_replies(args) -> int:
    """Answer new X mentions (drafts unless --live with FLY_X_POST=1)."""
    fly = _fly(args)
    print(fly.act_replies(live=args.live))
    fly.memory.save()
    return 0


def cmd_cam_test(args) -> int:
    """Post a test frame to the fly cam and read it back."""
    from .cam import FlyCam
    from .memes import render_meme

    cfg = FlyConfig.from_env()
    cam = FlyCam(cfg.site_url, cfg.cam_secret, log=print)
    if not cam.configured:
        print("cam not configured: set FLY_CAM_SECRET in .env (and the same value on Vercel)")
        return 1
    path = cfg.memes_dir / "cam-test.png"
    render_meme("FLY CAM TEST", "if you can see this the eye works", path, seed=2, mood="hyped", size=600)
    frames = cam.crops(path, 1, width=600, height=600)
    ok = cam.post("browsing", "https://flydev.tech", "fly cam test", "test frame", frames[0])
    print("posted" if ok else "post failed")
    import requests

    r = requests.get(f"{cfg.site_url}/api/cam", timeout=30)
    print(r.status_code, r.text[:300])
    cam.idle("test over")
    return 0 if ok else 2


def cmd_health(args) -> int:
    from .health import Health

    cfg = FlyConfig.from_env()
    h = Health(cfg.root, log=lambda m: None)
    h.state.restarts -= 1                                # this command is not a restart
    h.save()
    s = h.summary()
    print(f"uptime since last start: {s['uptime_sec'] // 60} min; restarts: {s['restarts']}; fix drafts today: {s['proposals_today']}")
    print("suspended actions: " + (", ".join(s["suspended"]) or "none"))
    print("network: " + ("up" if h.network_up() else "DOWN"))
    for n in h.checkup(force=True):
        print("checkup: " + n)
    for i in s["incidents"]:
        print(f"- {i.get('at', '')[:16]} {i.get('kind')}: {i.get('detail')}" + (f"  -> {i.get('fixed')}" if i.get("fixed") else ""))
    return 0


def cmd_forget(args) -> int:
    """Forget dry-run launches (rehearsals) so they stop showing on the site."""
    from .memory import Memory
    from .publish import export_site

    cfg = FlyConfig.from_env()
    memory = Memory(cfg.memory_path)
    if not args.symbol and not args.dry_runs:
        dry = [l for l in memory.data.get("launches") or []
               if not l.get("live") and l.get("status") in (None, "", "planned", "blocked")]
        print(f"{len(dry)} dry-run launch(es) on record: " + ", ".join(f"${l.get('symbol')}" for l in dry))
        print("usage: python fly.py forget <SYMBOL> | --dry-runs   (live launches are never forgotten)")
        return 0
    gone = memory.forget_launches(symbol=args.symbol or "", dry_runs=args.dry_runs)
    memory.save()
    print("forgot: " + (", ".join(f"${l.get('symbol')} ({l.get('status')})" for l in gone) or "nothing matched"))
    export_site(cfg, memory)
    print("site data re-exported; run  python fly.py publish --push  (or let the fly publish on its next tick)")
    return 0


def cmd_repairs(args) -> int:
    """List the fly's drafted fixes for its own crashes, or apply one."""
    from . import selfrepair

    cfg = FlyConfig.from_env()
    if args.action == "apply":
        if not args.stamp:
            print("usage: python fly.py repairs apply <stamp>")
            return 1
        applied = selfrepair.apply_proposal(cfg.root, args.stamp)
        print("applied: " + (", ".join(applied) or "nothing"))
        print("now run the tests, then commit:  python -m pytest -q tests && git add fly && git commit -m 'apply fly self-repair'")
        return 0
    props = selfrepair.list_proposals(cfg.root)
    if not props:
        print("no drafted fixes (the fly has not crashed in its own code, or it fixed itself by restarting)")
        return 0
    for pr in props:
        print(f"- {pr['stamp']}  tests {'PASS' if pr.get('tests_passed') else 'FAIL'}  {pr.get('error', '')[:80]}")
        print(f"    {pr.get('diagnosis', '')[:160]}")
        print(f"    files: {', '.join(pr.get('files', []))}   diff: data/self-repair/{pr['stamp']}/patch.diff")
    print("apply one with:  python fly.py repairs apply <stamp>")
    return 0


def cmd_x_status(args) -> int:
    from .x import XClient

    cfg = FlyConfig.from_env()
    x = XClient(cfg.x)
    print(f"handle: {cfg.x.handle}")
    print(f"credentials: {'set' if x.configured else 'missing (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)'}")
    print(f"posting: {'ARMED (FLY_X_POST=1)' if x.armed else 'dry run'}; cap {cfg.x.max_posts_per_day}/day; hype every {cfg.x.hype_every_hours}h")
    from .memory import Memory

    mem = Memory.load(cfg.memory_path)
    for p in mem.recent("posts", 8):
        print(f"- [{p.get('kind')}] {'live' if p.get('live') else 'draft'} score {p.get('score', 0)} :: {p.get('text')}")
    pb = mem.last("playbook")
    if pb:
        print("playbook next bets: " + "; ".join(pb.get("next_bets") or []))
    return 0


SYSTEMD_UNIT = "flydev"


def systemd_unit(root, python: str, live: bool, user: str, log) -> str:
    """A systemd service that keeps the fly alive on a Linux host: restarts on
    any exit (the supervisor exits 0 on a self-update, so that restarts too),
    starts at boot, logs to data/fly-daemon.log."""
    return (
        "[Unit]\nDescription=The Fly Dev agent (flydev.tech)\nAfter=network-online.target\nWants=network-online.target\n\n"
        f"[Service]\nType=simple\nUser={user}\nWorkingDirectory={root}\n"
        f"ExecStart={python} {root}/fly.py live{' --live' if live else ''}\n"
        "Restart=always\nRestartSec=10\nEnvironment=PYTHONUNBUFFERED=1\n"
        f"StandardOutput=append:{log}\nStandardError=append:{log}\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )


def _daemon_linux(args, cfg) -> int:
    """systemd flavour of `fly daemon` (install/uninstall need sudo)."""
    import getpass
    import os as _os
    import subprocess
    import sys as _sys
    from pathlib import Path as _P

    unit = _P("/etc/systemd/system") / f"{SYSTEMD_UNIT}.service"
    log = cfg.root / "data" / "fly-daemon.log"
    if args.action == "status":
        r = subprocess.run(["systemctl", "is-active", SYSTEMD_UNIT], capture_output=True, text=True)
        print("installed" if unit.is_file() else "not installed", "|", r.stdout.strip() or "unknown", "|", f"log: {log}")
        return 0
    if _os.geteuid() != 0:
        print(f"run this with sudo (it writes {unit}):  sudo -E $(which python) fly.py daemon {args.action}"
              + (" --live" if getattr(args, "live", False) else ""))
        return 1
    if args.action == "uninstall":
        subprocess.run(["systemctl", "disable", "--now", SYSTEMD_UNIT], capture_output=True)
        unit.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        print("uninstalled")
        return 0
    user = _os.environ.get("SUDO_USER") or getpass.getuser()
    (cfg.root / "data").mkdir(parents=True, exist_ok=True)
    unit.write_text(systemd_unit(cfg.root, _sys.executable, args.live, user, log), encoding="utf-8")
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    r = subprocess.run(["systemctl", "enable", "--now", SYSTEMD_UNIT], capture_output=True, text=True)
    if r.returncode != 0:
        print("systemctl enable failed:", (r.stderr or r.stdout).strip())
        return 1
    print(f"installed and started ({'live' if args.live else 'dry-run launches/posts'}) as {user}; it restarts on crash and at boot")
    print(f"follow it with:  tail -F {log}")
    print("stop it with:    sudo -E $(which python) fly.py daemon uninstall")
    return 0


def cmd_daemon(args) -> int:
    """Run the fly as a background service (launchd on macOS, systemd on
    Linux) so it lives without a terminal open. Logs go to data/fly-daemon.log."""
    import plistlib
    import subprocess
    import sys as _sys
    from pathlib import Path as _P

    cfg = FlyConfig.from_env()
    if _sys.platform.startswith("linux"):
        return _daemon_linux(args, cfg)
    label = "tech.flydev.fly"
    plist = _P.home() / "Library" / "LaunchAgents" / f"{label}.plist"
    log = cfg.root / "data" / "fly-daemon.log"
    if args.action == "status":
        r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
        print("installed" if plist.is_file() else "not installed", "|", "running" if label in r.stdout else "not running", "|", f"log: {log}")
        return 0
    if args.action == "uninstall":
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
        plist.unlink(missing_ok=True)
        print("uninstalled")
        return 0
    if _sys.platform != "darwin":
        print("daemon install supports macOS (launchd) and Linux (systemd)")
        return 1
    argv = ["/usr/bin/caffeinate", "-i", _sys.executable, str(cfg.root / "fly.py"), "live"]
    if args.live:
        argv.append("--live")
    data = {
        "Label": label, "ProgramArguments": argv, "WorkingDirectory": str(cfg.root),
        "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": str(log), "StandardErrorPath": str(log),
        "EnvironmentVariables": {"PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "PYTHONUNBUFFERED": "1"},
    }
    plist.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)
    with plist.open("wb") as fh:
        plistlib.dump(data, fh)
    r = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if r.returncode != 0:
        print("launchctl load failed:", (r.stderr or r.stdout).strip())
        return 1
    print(f"installed and started ({'live' if args.live else 'dry-run launches/posts'}); it restarts on crash and at login")
    print(f"follow it with:  tail -f {log}")
    print("stop it with:    python fly.py daemon uninstall")
    return 0


def cmd_publish(args) -> int:
    from .memory import Memory
    from .publish import export_site, publish

    cfg = FlyConfig.from_env()
    out = export_site(cfg, Memory.load(cfg.memory_path))
    print(f"exported {out}")
    if args.push:
        pushed = publish(cfg, "manual publish")
        print("pushed" if pushed else "nothing new to push")
    return 0


def cmd_serve(args) -> int:
    """Serve site/ locally so you can watch (and record) the fly."""
    import functools
    import http.server
    import threading

    from .memory import Memory
    from .publish import export_site

    cfg = FlyConfig.from_env()
    export_site(cfg, Memory.load(cfg.memory_path))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(cfg.root / "site"))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler)

    def refresh():
        while True:
            __import__("time").sleep(10)
            try:
                export_site(cfg, Memory.load(cfg.memory_path))
            except Exception:
                pass

    threading.Thread(target=refresh, daemon=True).start()
    print(f"watching the fly at http://127.0.0.1:{args.port}  (ctrl-c to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_host_test(args) -> int:
    from .hosting import check_host, host_image, verify_url
    from .memes import render_meme

    cfg = FlyConfig.from_env()
    print(check_host(cfg.hosting))
    if cfg.hosting.provider == "none":
        return 1
    path = Path(args.image) if args.image else cfg.memes_dir / "host-test.png"
    if not path.is_file():
        render_meme("HOST TEST", "if you can read this the fly can launch", path, seed=1, mood="hyped", size=400)
    print(f"uploading {path} ...")
    url = host_image(path, cfg.hosting, name=f"host-test-{int(__import__('time').time())}.png")
    print(f"url: {url}")
    print("verifying it serves an image ...", end=" ", flush=True)
    ok = verify_url(url)
    print("ok" if ok else "not yet (gateway may lag; open the url in a browser)")
    return 0 if ok else 2


def cmd_launch(args) -> int:
    fly = _fly(args)
    from .drives import Drives

    drives = Drives(0.5, 0.5, 0.5, 0.9, 0.7, 0.1)
    meme = None
    if args.meme:
        meme = {"path": args.meme, "top": args.top or "FLY", "bottom": args.bottom or "", "mood": args.mood}
    outcome = fly.act_launch(drives, live=args.live, meme=meme, name=args.name or "",
                             symbol=(args.symbol or "").upper(), description=args.description or "")
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
    t.add_argument("--force", choices=["browse", "build", "meme", "launch", "rest", "website", "repair", "improve"])
    t.add_argument("--seed", type=int)
    t.add_argument("--live", action="store_true", help="allow real launches (FLY_LIVE_LAUNCH=1) and real X posts (FLY_X_POST=1)")
    t.set_defaults(fn=cmd_tick)
    l = sub.add_parser("live", help="keep living: the fly paces itself (or --interval for a fixed timer)")
    l.add_argument("--ticks", type=int)
    l.add_argument("--interval", type=int, help="seconds between actions; omit for free will")
    l.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    l.add_argument("--live", action="store_true")
    l.set_defaults(fn=cmd_live)
    br = sub.add_parser("browse", help="watch the fly browse: search, read, digest")
    br.add_argument("topics", nargs="*", help="search topics (default: the fly's seed topics)")
    br.add_argument("--pages", type=int, default=None, help="how many pages to read")
    br.set_defaults(fn=cmd_browse)
    m = sub.add_parser("meme", help="render a meme by hand")
    m.add_argument("top")
    m.add_argument("bottom", nargs="?")
    m.add_argument("--mood", default="curious")
    m.add_argument("--seed", type=int, default=0)
    m.add_argument("--out")
    m.set_defaults(fn=cmd_meme)
    sub.add_parser("launch-status", help="read the Pons factory state and a readiness checklist").set_defaults(fn=cmd_launch_status)
    sub.add_parser("wallet", help="show the launch wallet address and balance").set_defaults(fn=cmd_wallet)
    fe = sub.add_parser("fees", help="creator fees: pending on curves, claimable in escrow; --sweep/--claim to collect")
    fe.add_argument("--curve", help="a specific curve address (default: every live launch in memory)")
    fe.add_argument("--sweep", action="store_true", help="push pending curve fees into the escrow")
    fe.add_argument("--claim", action="store_true", help="claim the escrow balance to the wallet")
    fe.add_argument("--min-buyback-out", type=int, default=0, dest="min_buyback_out")
    fe.add_argument("--live", action="store_true")
    fe.set_defaults(fn=cmd_fees)
    ws = sub.add_parser("website", help="the fly designs and writes its own website into site/")
    ws.add_argument("--refine", action="store_true", help="keep the current design; only run the look-and-fix loop")
    ws.add_argument("--change", action="append", help="with --refine: a change request for the fly (repeatable)")
    ws.set_defaults(fn=cmd_website)
    bd = sub.add_parser("brand", help="the fly draws its X profile picture and banner into site/brand/")
    bd.add_argument("--seed", type=int)
    bd.set_defaults(fn=cmd_brand)
    sub.add_parser("sync", help="git pull without conflicts on the fly's generated state file").set_defaults(fn=cmd_sync)
    dm = sub.add_parser("daemon", help="run the fly as a background service on macOS (install | uninstall | status)")
    dm.add_argument("action", choices=["install", "uninstall", "status"])
    dm.add_argument("--live", action="store_true", help="install with real launches and posts enabled")
    dm.set_defaults(fn=cmd_daemon)
    po = sub.add_parser("post", help="compose one X post (dry run unless --live with FLY_X_POST=1)")
    po.add_argument("--kind", choices=["hype", "build", "meme", "launch", "learning"], default="hype")
    po.add_argument("--material", help="what the post is about (default: the latest of that kind)")
    po.add_argument("--media", help="image to attach")
    po.add_argument("--live", action="store_true")
    po.set_defaults(fn=cmd_post)
    sub.add_parser("x-status", help="X credentials, posting state, recent posts and the playbook").set_defaults(fn=cmd_x_status)
    sub.add_parser("health", help="uptime, suspended actions, recent incidents and what the fly did about them").set_defaults(fn=cmd_health)
    fg = sub.add_parser("forget", help="drop a dry-run launch from memory and the site (never a live one)")
    fg.add_argument("symbol", nargs="?", help="ticker of the dry run to forget")
    fg.add_argument("--dry-runs", action="store_true", help="forget every dry-run launch")
    fg.set_defaults(fn=cmd_forget)
    rp2 = sub.add_parser("repairs", help="fixes the fly drafted for its own crashes (list | apply <stamp>)")
    rp2.add_argument("action", nargs="?", choices=["list", "apply"], default="list")
    rp2.add_argument("stamp", nargs="?")
    rp2.set_defaults(fn=cmd_repairs)
    sub.add_parser("cam-test", help="post a test frame to the fly cam and read it back").set_defaults(fn=cmd_cam_test)
    rp = sub.add_parser("replies", help="answer new mentions on X")
    rp.add_argument("--live", action="store_true")
    rp.set_defaults(fn=cmd_replies)
    pu = sub.add_parser("publish", help="export site/data/state.json (+ --push to commit and push)")
    pu.add_argument("--push", action="store_true")
    pu.set_defaults(fn=cmd_publish)
    sv = sub.add_parser("serve", help="serve the website locally and keep it refreshed")
    sv.add_argument("--port", type=int, default=8642)
    sv.set_defaults(fn=cmd_serve)
    ht = sub.add_parser("host-test", help="upload a test image to the configured host and verify it")
    ht.add_argument("image", nargs="?")
    ht.set_defaults(fn=cmd_host_test)
    la = sub.add_parser("launch", help="plan (or, with --live, send) a memecoin launch")
    la.add_argument("--meme", help="path to a meme png to use as the logo")
    la.add_argument("--top")
    la.add_argument("--bottom")
    la.add_argument("--mood", default="curious")
    la.add_argument("--name", help="force the token name (default: genesis coin for the first launch, else the mind's idea)")
    la.add_argument("--symbol", help="force the ticker, 2-8 letters")
    la.add_argument("--description", help="force the on-chain description")
    la.add_argument("--live", action="store_true")
    la.set_defaults(fn=cmd_launch)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
