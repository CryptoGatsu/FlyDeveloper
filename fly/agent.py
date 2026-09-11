"""The fly itself: perceive with the connectome, decide, act, remember."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .brain import FlyBrain, SpikeReport, build_brain
from .browser import Browser
from .config import FlyConfig
from .developer import Workshop
from .drives import Drives, WorldSignals, choose_action, compute_drives
from .hosting import HostingError, host_image
from .launchpad import LaunchGuard, PonsLaunchpad, TokenParams, make_salt
from .memes import render_meme
from .memory import Memory
from .mind import Mind, MindRefused, build_mind
from .neurons import Sense, load_senses

Logger = Callable[[str], None]


@dataclass
class TickResult:
    action: str
    drives: Drives
    probabilities: dict[str, float]
    reports: dict[str, SpikeReport]
    outcome: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        lines = [f"drives: {self.drives.describe()}", f"policy: {self.probabilities}", f"action: {self.action}"]
        for r in self.reports.values():
            lines.append("brain " + r.describe())
        for k, v in self.outcome.items():
            lines.append(f"{k}: {v}")
        return "\n".join(lines)


class Fly:
    def __init__(
        self,
        cfg: FlyConfig,
        brain: FlyBrain | None = None,
        mind: Mind | None = None,
        browser: Browser | None = None,
        launchpad: PonsLaunchpad | None = None,
        log: Logger = print,
    ):
        self.cfg = cfg
        self.log = log
        self.memory = Memory.load(cfg.memory_path)
        self.brain = brain or build_brain(cfg.brain)
        self.mind = mind or build_mind(cfg.mind)
        self.browser = browser or Browser(cfg.browser, log=log)
        self.workshop = Workshop(cfg.workshop_dir)
        self._launchpad = launchpad
        self.senses: dict[str, Sense] = load_senses(cfg.root / "data" / "fly_senses.json")

    @property
    def launchpad(self) -> PonsLaunchpad:
        if self._launchpad is None:
            self._launchpad = PonsLaunchpad(self.cfg.launchpad)
        return self._launchpad

    # -- perception ------------------------------------------------------
    def world(self) -> WorldSignals:
        m = self.memory
        pages = m.recent("pages", 20)
        unread = sum(1 for p in pages if p.get("interesting") and not p.get("used"))
        return WorldSignals(
            hours_since_browse=m.hours_since("pages"),
            hours_since_build=m.hours_since("builds"),
            hours_since_meme=m.hours_since("memes"),
            hours_since_launch=m.hours_since("launches"),
            unread_notes=unread,
            unlaunched_memes=len(m.unlaunched_memes()),
            launches_today=m.count_since("launches", 24.0, live=True),
            max_launches_per_day=self.cfg.launchpad.max_launches_per_day,
            launch_armed=self.cfg.launchpad.live,
            genesis_pending=bool(self.cfg.launchpad.genesis_name) and not self.has_launched(),
        )

    def perceive(self, seed: int | None = None) -> dict[str, SpikeReport]:
        reports: dict[str, SpikeReport] = {}
        base_seed = seed if seed is not None else self.cfg.brain.seed
        for i, (name, sense) in enumerate(self.senses.items()):
            idx = self.brain.connectome.index_of(sense.flywire_ids)
            if idx.size == 0:
                # Phantom brains do not contain FlyWire IDs: use a fixed slice.
                n = self.brain.n_neurons
                idx = list(range((i * 37) % n, (i * 37) % n + max(2, len(sense.flywire_ids))))
                idx = [j % n for j in idx]
            reports[name] = self.brain.run(
                name, idx, sense.rate_hz, t_run_sec=self.cfg.brain.t_run_sec,
                seed=None if base_seed is None else base_seed + i,
            )
        return reports

    def mood(self, drives: Drives) -> str:
        best = max(
            ("curious", drives.curiosity), ("hungry", drives.appetite), ("hyped", drives.boldness),
            ("scheming", drives.craft), ("smug", drives.humor), ("tired", drives.fatigue),
            key=lambda kv: kv[1],
        )
        return best[0]

    # -- one heartbeat ---------------------------------------------------
    def tick(self, force: str | None = None, seed: int | None = None, live: bool = False) -> TickResult:
        reports = self.perceive(seed=seed)
        world = self.world()
        drives = compute_drives(reports, world, self.brain.connectome.calibration)
        fingerprint = "".join(r.fingerprint() for r in reports.values())
        action, probs = choose_action(drives, world, fingerprint)
        if force:
            action = force
        self.memory.add("drives", {"drives": drives.as_dict(), "action": action, "probs": probs,
                                   "brain": {k: r.describe() for k, r in reports.items()}})
        mood = self.mood(drives)
        self.log(f"fly feels {mood} ({drives.describe()}) -> {action}")
        if action == "launch" and world.genesis_pending and world.launch_armed:
            self.log("the fly wants to hatch its own coin")
        result = TickResult(action=action, drives=drives, probabilities=probs, reports=reports)
        try:
            if action == "browse":
                result.outcome = self.act_browse(drives)
            elif action == "build":
                result.outcome = self.act_build(drives)
            elif action == "meme":
                result.outcome = self.act_meme(drives, fingerprint)
            elif action == "launch":
                result.outcome = self.act_launch(drives, live=live)
            else:
                result.outcome = {"rest": "the fly grooms its wings"}
                self.memory.note("rested")
        except MindRefused as exc:
            result.outcome = {"error": f"mind refused: {exc}"}
            self.memory.note(f"mind refused during {action}: {exc}")
        finally:
            self.memory.save()
            self._publish(action, mood)
        return result

    def _publish(self, action: str, mood: str) -> None:
        if self.cfg.publish == "none":
            return
        try:
            from .publish import export_site, publish

            export_site(self.cfg, self.memory, extra={"mood": mood, "wallet": self._launchpad.address if self._launchpad else ""})
            if self.cfg.publish == "git":
                last = self.memory.last(action if action in ("builds",) else {"browse": "pages", "build": "builds", "meme": "memes", "launch": "launches"}.get(action, "journal")) or {}
                what = last.get("title") or last.get("top") or last.get("symbol") or action
                publish(self.cfg, f"{action}: {what}", log=self.log)
        except Exception as exc:
            self.log(f"publish skipped: {exc}")

    def run(self, ticks: int | None = None, interval_sec: int | None = None, live: bool = False) -> None:
        interval = interval_sec or self.cfg.tick_interval_sec
        n = 0
        while ticks is None or n < ticks:
            result = self.tick(live=live)
            self.log(result.describe())
            n += 1
            if ticks is not None and n >= ticks:
                break
            time.sleep(interval)

    # -- actions ---------------------------------------------------------
    def context(self) -> str:
        return self.memory.summary()

    def act_browse(self, drives: Drives) -> dict[str, Any]:
        topics = list(self.cfg.browser.seeds)
        for page in self.memory.recent("pages", 5):
            topics.extend(page.get("followups") or [])
        # Rotate through topics so successive sessions do not repeat.
        offset = len(self.memory.data["pages"]) % max(1, len(topics))
        topics = topics[offset:] + topics[:offset]
        notes = self.browser.explore(self.mind, self.memory, topics, budget=self.cfg.browser.max_pages_per_session)
        self.memory.note(f"browsed {len(notes)} pages", topics=topics[:3])
        return {"pages": [f"{n.title} -> {n.gist[:100]}" for n in notes], "topics": topics[:3]}

    def act_build(self, drives: Drives) -> dict[str, Any]:
        idea = self.mind.ideate(self.context())
        self.memory.add("ideas", {"slug": idea.slug, "title": idea.title, "for_whom": idea.for_whom,
                                  "pitch": idea.pitch, "why": idea.why_needed})
        for page in self.memory.recent("pages", 20):
            page["used"] = True
        result = self.workshop.build(idea)
        self.memory.add("builds", {"slug": result.slug, "title": idea.title, "ok": result.ok,
                                   "path": str(result.path), "files": result.files, "log": result.log[-1500:]})
        return {"built": idea.title, "path": str(result.path), "ok": result.ok, "files": result.files,
                "log_tail": result.log[-600:]}

    def has_launched(self) -> bool:
        return any(l.get("live") for l in self.memory.data.get("launches") or [])

    def act_meme(self, drives: Drives, fingerprint: str = "", theme: str = "") -> dict[str, Any]:
        mood = self.mood(drives)
        caption = self.mind.caption(self.context(), mood, theme=theme)
        seed = int(fingerprint[:8], 16) if fingerprint else int(time.time())
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = self.cfg.memes_dir / f"fly-{stamp}-{caption.mood}.png"
        render_meme(caption.top, caption.bottom, path, seed=seed, mood=caption.mood)
        self.memory.add("memes", {"path": str(path), "top": caption.top, "bottom": caption.bottom,
                                  "alt": caption.alt_text, "mood": caption.mood})
        return {"meme": str(path), "top": caption.top, "bottom": caption.bottom}

    def act_launch(
        self, drives: Drives, live: bool = False, meme: dict[str, Any] | None = None,
        name: str = "", symbol: str = "", description: str = "",
    ) -> dict[str, Any]:
        from .mind import MemeCaption

        lp = self.cfg.launchpad
        theme = ""
        # The fly's first coin is its own identity coin (genesis), unless told otherwise.
        is_genesis = bool(lp.genesis_name and not self.has_launched() and (not name or name == lp.genesis_name))
        if is_genesis and not name:
            name, symbol = lp.genesis_name, lp.genesis_symbol
        # Fee policy: genesis fees fund the project (stay claimable by the wallet);
        # other coins buy back and lock, or accrue to the wallet, per config.
        buyback = lp.genesis_buyback if is_genesis else (lp.coin_fee_mode == "buyback")
        if name:
            theme = (f"This meme is the face of the fly's own coin, {name} (${symbol}): a fruit-fly "
                     "connectome that browses, builds tiny tools and draws memes. Make it about that.")

        if meme is None:
            if name or not self.memory.unlaunched_memes():
                self.act_meme(drives, theme=theme)        # a fresh meme for a named coin
            meme = self.memory.unlaunched_memes()[-1]
        caption = MemeCaption(top=meme["top"], bottom=meme["bottom"], alt_text=meme.get("alt", ""), mood=meme.get("mood", "curious"))
        concept = self.mind.coin(caption, self.context(), name=name, symbol=symbol)
        if description:
            concept.description = description
        symbol = "".join(ch for ch in concept.symbol.upper() if ch.isalpha())[:8] or "FLY"

        logo = ""
        meme_path = Path(meme["path"])
        try:
            logo = host_image(meme_path, self.cfg.hosting, name=f"{symbol.lower()}-{meme_path.name}") or ""
        except HostingError as exc:
            self.memory.note(f"could not host meme: {exc}")
        lp = self.cfg.launchpad
        params = TokenParams(
            name=concept.name[:40], symbol=symbol, logo=logo, description=concept.description[:600],
            website=lp.website, twitter=lp.twitter, telegram=lp.telegram,
            creator_tax_bps=lp.creator_tax_bps, buyback_enabled=buyback,
            salt=make_salt(symbol, meme["path"]),
        )
        plan = self.launchpad.plan(params, initial_buy_eth=lp.initial_buy_eth, live=live)
        plan = self.launchpad.execute(plan, LaunchGuard(lp), self.memory)
        self.memory.add("launches", {
            "name": params.name, "symbol": symbol, "description": params.description, "meme": meme["path"],
            "logo": logo, "live": plan.status == "confirmed", "status": plan.status, "tx": plan.tx_hash,
            "genesis": is_genesis, "buyback": buyback, "creator_tax_bps": lp.creator_tax_bps,
            "token": plan.token, "curve": plan.curve, "problems": plan.problems, "calldata": plan.calldata[:10],
        })
        self.log(plan.describe())
        return {"launch": plan.describe(), "status": plan.status, "tagline": concept.tagline}
