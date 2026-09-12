"""The fly itself: perceive with the connectome, decide, act, remember."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .brain import FlyBrain, SpikeReport, build_brain
from .browser import Browser
from .config import FlyConfig, pons_token_url
from .developer import Workshop
from .drives import Drives, WorldSignals, choose_action, compute_drives
from .hosting import HostingError, host_image
from .launchpad import LaunchGuard, PonsLaunchpad, TokenParams, make_salt
from .memes import render_meme
from .memory import Memory
from .mind import Mind, MindRefused, build_mind
from .neurons import Sense, load_senses
from .x import Post, XClient, XError, engagement_score, mention_skip_reason, post_problems

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
        from .cam import FlyCam

        self.cam = FlyCam(cfg.site_url, cfg.cam_secret, log=log)
        self.browser = browser or Browser(cfg.browser, log=log, shots_dir=cfg.root / "site" / "browsing" / "shots",
                                          cam=self.cam if self.cam.configured else None)
        self.workshop = Workshop(cfg.workshop_dir)
        self._launchpad = launchpad
        try:
            self.x = XClient(cfg.x)
        except Exception as exc:                        # missing dependency etc.: never fatal
            log(f"x client unavailable: {exc}")
            from .x import XClient as _X

            self.x = _X(type(cfg.x)())
        from .health import Health

        self.health = Health(cfg.root, log=log)
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
            actions_last_hour=sum(1 for d in m.recent("drives", 60) if d.get("action") not in (None, "rest")
                                  and time.time() - float(d.get("ts", 0)) < 3600),
            actions_today=m.count_since("drives", 24.0),
            max_actions_per_day=self.cfg.max_actions_per_day,
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
        elif not self.health.allowed(action):
            self.log(f"{action} is suspended after repeated failures; choosing something else")
            probs = {k: (0.0 if k == action else v) for k, v in probs.items()}
            action = max(probs, key=probs.get) if any(probs.values()) else "rest"
        self.memory.add("drives", {"drives": drives.as_dict(), "action": action, "probs": probs,
                                   "brain": {k: r.describe() for k, r in reports.items()}})
        self._last_rasters = {k: r.raster() for k, r in reports.items()}
        self._push_brain(self._last_rasters, mood=self.mood(drives), action=action)
        mood = self.mood(drives)
        self.log(f"fly feels {mood} ({drives.describe()}) -> {action}")
        if action == "launch" and world.genesis_pending and world.launch_armed:
            self.log("the fly wants to hatch its own coin")
        result = TickResult(action=action, drives=drives, probabilities=probs, reports=reports)
        from .website import site_exists

        if action != "website" and not site_exists(self.cfg.root / "site"):
            self.log("the fly has no website yet; building one first")
            try:
                result.outcome["website"] = self.act_website()
            except MindRefused as exc:
                self.memory.note(f"mind refused to build the website: {exc}")
        try:
            if action == "website":
                result.outcome = self.act_website()
            elif action == "repair":
                broken = [b for b in self._tool_builds() if not b.get("ok")]
                result.outcome = self.act_repair(broken[-1]) if broken else {"repair": "nothing is broken"}
            elif action == "improve":
                tools = self._tool_builds()
                result.outcome = self.act_improve(min(tools, key=lambda b: float(b.get("touched_ts") or b.get("ts") or 0))) if tools else {"improve": "nothing built yet"}
            elif action == "browse":
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
            self.health.succeeded(action)
        except MindRefused as exc:
            result.outcome = {"error": f"mind refused: {exc}"}
            self.memory.note(f"mind refused during {action}: {exc}")
        except Exception as exc:
            result.outcome = {"error": f"{type(exc).__name__}: {exc}"}
            self.memory.note(f"{action} failed: {type(exc).__name__}: {str(exc)[:200]}")
            self.log(f"{action} failed: {type(exc).__name__}: {str(exc)[:200]}")
            msg = str(exc).lower()
            if "credit balance" in msg or "billing" in msg or "authentication" in msg or "invalid x-api-key" in msg:
                # the mind is unavailable for reasons a fly cannot fix: rest, do not thrash
                self.health.incident("mind", f"{type(exc).__name__}: {str(exc)[:200]}",
                                     fixed="resting an hour; top up credits or fix ANTHROPIC_API_KEY")
                for a in ("browse", "build", "meme", "launch", "website", "repair", "improve"):
                    b = self.health.state.breakers.setdefault(a, __import__("fly.health", fromlist=["Breaker"]).Breaker())
                    b.open_until = max(b.open_until, time.time() + 3600)
                self.health.save()
                self.log("the mind is unavailable (credits or key); resting an hour")
            elif self.health.failed(action, f"{type(exc).__name__}: {exc}"):
                self.log(f"{action} suspended for a while")
            self._last_exception = exc
        try:
            result.outcome["x"] = self.social_after(action, result.outcome, live=live)
        except Exception as exc:                       # posting must never break a tick
            self.memory.note(f"x error: {exc}")
            result.outcome["x"] = f"error: {exc}"
        finally:
            self.memory.save()
            self._publish(action, mood)
        return result

    _last_rasters: dict[str, Any] = {}

    def _push_brain(self, rasters: dict[str, Any], mood: str, action: str) -> None:
        """Send the latest spike rasters to the fly cam so the home page shows
        the brain firing within seconds (state.json follows on the next publish)."""
        if not getattr(self, "cam", None) or not self.cam.configured:
            return
        import threading

        payload = {"at": self.memory.data["drives"][-1]["at"] if self.memory.data.get("drives") else None,
                   "mood": mood, "action": action, "rasters": rasters}
        threading.Thread(target=self.cam.post_brain, args=(payload,), daemon=True).start()

    # -- X ---------------------------------------------------------------
    def social_after(self, action: str, outcome: dict[str, Any], live: bool = False) -> str:
        """Post about what just happened, refresh engagement, keep a hype cadence."""
        self.refresh_metrics()
        posted: list[str] = []
        if action == "build" and outcome.get("ok") and outcome.get("built"):
            posted.append(self.act_post("build", f"{outcome['built']}: {outcome.get('pitch', '')} "
                                         f"{(self.cfg.site_url or self.cfg.launchpad.website).rstrip('/')}/builds", live=live))
        elif action == "build" and outcome.get("improved") and outcome.get("what"):
            posted.append(self.act_post("build", f"Improved {outcome['improved']}: {outcome['what']} "
                                         f"{(self.cfg.site_url or self.cfg.launchpad.website).rstrip('/')}/builds", live=live))
        elif action == "meme" and outcome.get("meme"):
            posted.append(self.act_post("meme", f"{outcome.get('top')} / {outcome.get('bottom')}", media=outcome["meme"], live=live))
        elif action == "launch" and outcome.get("status") == "confirmed":
            last = self.memory.last("launches") or {}
            site = (self.cfg.site_url or self.cfg.launchpad.website).rstrip("/")
            posted.append(self.act_post("launch", f"{last.get('name')} (${last.get('symbol')}) "
                                         f"{'genesis, my own coin' if last.get('genesis') else 'another joke with a ticker'}, "
                                         f"paired with {last.get('pair') or 'ETH'} on Pons. "
                                         f"Links you may use: buy it at {last.get('pons_url') or site + '/coins'}; "
                                         f"my coins page {site}/coins. Do not link anything else.",
                                         media=last.get("meme") or "", live=live))
        elif action == "browse" and outcome.get("learned"):
            posted.append(self.act_post("learning", outcome["learned"], live=live))
        # unprompted $FLYDEV hype on a cadence
        if self.memory.hours_since_kind("posts", "hype") >= self.cfg.x.hype_every_hours:
            posted.append(self.act_post("hype", "your own coin $FLYDEV, your brain, your builds; pick a fresh angle", live=live))
        if self.x.configured:
            posted.append(self.act_replies(live=live, mood=(self.memory.last("drives") or {}).get("action", "curious")))
        return "; ".join(p for p in posted if p) or "nothing to say"

    def act_replies(self, live: bool = False, mood: str = "curious") -> str:
        """Answer new mentions on X (the fly as a chat you can @)."""
        if not self.x.configured:
            return "x not configured"
        state = self.memory.data.setdefault("journal", [])
        since = ""
        for item in reversed(self.memory.data.get("posts", [])):
            if item.get("kind") == "reply" and item.get("mention_id"):
                since = item["mention_id"]
                break
        try:
            mentions = self.x.mentions(since_id=since)
        except XError as exc:
            self.memory.note(f"could not read mentions: {exc}")
            return f"mentions unavailable ({str(exc)[:60]})"
        me = self.x.me()
        answered = 0
        for m in reversed(mentions):                   # oldest first
            if m.get("author_id") == me or not m.get("text"):
                continue
            if self.memory.count_since("posts", 24.0, kind="reply", live=True) >= self.cfg.x.max_replies_per_day:
                self.memory.note("reply cap reached for today")
                break
            if any(p.get("mention_id") == m["id"] for p in self.memory.data.get("posts", [])):
                continue
            author = m.get("author") or "someone"
            why = mention_skip_reason(m["text"])
            if not why and self.memory.count_since("posts", 24.0, kind="reply", live=True, to=author) >= self.cfg.x.max_replies_per_account_per_day:
                why = f"already answered @{author} today"
            draft = None
            if not why:
                draft = self.mind.reply(author, m["text"], self.context(), mood)
                if draft.ignore or not draft.text.strip():
                    why = draft.why or "nothing worth answering"
            if why:
                self.memory.add("posts", {"kind": "reply", "text": "", "id": "", "url": "", "live": False, "skipped": why,
                                          "mention_id": m["id"], "to": author, "asked": m["text"][:280],
                                          "problems": [], "metrics": {}, "score": 0.0})
                self.log(f"ignored @{author}: {why} :: {m['text'][:100]}")
                continue
            post = Post(text=draft.text.strip(), kind="reply")
            post.problems = post_problems(post.text)
            if not post.problems and live and self.x.armed:
                post = self.x.reply(post.text, m["id"])
            self.memory.add("posts", {"kind": "reply", "text": post.text, "id": post.id, "url": post.url, "live": post.live,
                                      "mention_id": m["id"], "to": m.get("author", ""), "asked": m["text"][:280],
                                      "problems": post.problems, "metrics": {}, "score": 0.0})
            self.log(f"{'replied' if post.live else 'drafted reply'} to @{m.get('author')}: {post.text}")
            answered += 1
        return f"{answered} mention(s) answered" if answered else "no new mentions"

    def act_post(self, kind: str, material: str, media: str = "", live: bool = False) -> str:
        today = sum(1 for x in self.memory.data.get("posts", [])
                    if x.get("live") and x.get("kind") != "reply" and float(x.get("ts", 0)) >= time.time() - 86400)
        if today >= self.cfg.x.max_posts_per_day:
            return f"{kind}: daily post cap reached"
        draft = self.mind.compose_post(kind, material, self.context(), self.playbook_text())
        post = Post(text=draft.text.strip(), kind=kind, media=media)
        post.problems = post_problems(post.text)
        if not post.problems and live and self.x.armed:
            post = self.x.send(post)                    # real post
        entry = {"kind": kind, "text": post.text, "media": media, "id": post.id, "url": post.url, "live": post.live,
                 "why": draft.why, "problems": post.problems, "metrics": {}, "score": 0.0}
        self.memory.add("posts", entry)
        if post.problems:
            self.memory.note(f"held an X post ({kind}): {'; '.join(post.problems)}")
            self.log(f"held post ({kind}): {'; '.join(post.problems)} :: {post.text}")
            return f"{kind}: held ({post.problems[0]})"
        self.log(f"{'posted' if post.live else 'drafted'} on X ({kind}): {post.text}")
        return f"{kind}: {'posted ' + post.url if post.live else 'drafted (dry run)'}"

    def playbook_text(self) -> str:
        pb = self.memory.last("playbook")
        if not pb:
            return ""
        return ("works: " + "; ".join(pb.get("what_works") or []) + "\nflops: " + "; ".join(pb.get("what_flops") or [])
                + "\nnext: " + "; ".join(pb.get("next_bets") or []))

    def refresh_metrics(self) -> None:
        """Pull engagement for live posts and rewrite the playbook when it moved."""
        if not self.x.configured:
            return
        if self.memory.hours_since("playbook", default=1e6) < self.cfg.x.metrics_every_hours and self.memory.last("playbook"):
            return
        live = [p for p in self.memory.data.get("posts", []) if p.get("live") and p.get("id")]
        if not live:
            return
        try:
            found = self.x.metrics([p["id"] for p in live[-100:]])
        except XError as exc:
            self.memory.note(f"could not read X metrics: {exc}")
            return
        for p in live:
            m = found.get(p["id"])
            if m:
                p["metrics"] = m
                p["score"] = round(engagement_score(m), 2)
        scored = sorted((p for p in live if p.get("metrics")), key=lambda p: p.get("score", 0), reverse=True)
        if len(scored) >= 3:
            lines = [f"[{p['kind']}] score {p['score']} likes {p['metrics'].get('like_count', 0)} reposts {p['metrics'].get('retweet_count', 0)} "
                     f"replies {p['metrics'].get('reply_count', 0)} views {p['metrics'].get('impression_count', 0)} media={'yes' if p.get('media') else 'no'} :: {p['text']}"
                     for p in scored[:25]]
            try:
                pb = self.mind.playbook("\n".join(lines))
                self.memory.add("playbook", {"what_works": pb.what_works, "what_flops": pb.what_flops, "next_bets": pb.next_bets,
                                             "posts_scored": len(scored)})
                self.log("updated the engagement playbook: " + "; ".join(pb.next_bets)[:200])
            except MindRefused as exc:
                self.memory.note(f"playbook refused: {exc}")

    def _publish(self, action: str, mood: str) -> None:
        if self.cfg.publish == "none":
            return
        try:
            from .publish import export_site, publish

            export_site(self.cfg, self.memory, extra={"mood": mood, "wallet": self._launchpad.address if self._launchpad else "",
                                                     "health": self.health.summary(), "rasters": self._last_rasters})
            if self.cfg.publish == "git":
                last = self.memory.last(action if action in ("builds",) else {"browse": "pages", "build": "builds", "meme": "memes", "launch": "launches"}.get(action, "journal")) or {}
                what = last.get("title") or last.get("top") or last.get("symbol") or action
                publish(self.cfg, f"{action}: {what}", log=self.log)
        except Exception as exc:
            self.log(f"publish skipped: {exc}")

    _last_exception: BaseException | None = None

    def run(self, ticks: int | None = None, interval_sec: int | None = None, live: bool = False) -> int:
        """Keep living. With a fixed interval the fly acts on a timer; with none
        (the default) it decides how long to rest after each action. Never
        dies on an error: it backs off, checks itself, and tries again.
        Returns an exit code: 0 = restart me on new code, 2 = asked to stop."""
        from . import selfrepair
        from .drives import next_rest_sec

        interval = interval_sec if interval_sec is not None else self.cfg.tick_interval_sec
        self.health.start_watchdog()
        n = 0
        crashes = 0
        while ticks is None or n < ticks:
            self.health.beat("checkup")
            for note in self.health.checkup():
                self.log(f"checkup: {note}")
                self.memory.note(f"checkup: {note}")
            if not self.health.network_up():
                self.health.wait_for_network()
            if self.health.maybe_update():
                self.memory.note("pulled my own updates; restarting")
                self.memory.save()
                return 0
            self._last_exception = None
            try:
                self.health.beat("tick")
                result = self.tick(live=live)
                self.log(result.describe())
                crashes = 0
                action, drives, fingerprint = result.action, result.drives, "".join(r.fingerprint() for r in result.reports.values())
            except KeyboardInterrupt:
                self.log("stopped by hand")
                return 2
            except Exception as exc:                    # a crash outside any single action
                crashes += 1
                self.health.incident("crash", f"{type(exc).__name__}: {str(exc)[:300]}")
                self.log(f"crash #{crashes}: {type(exc).__name__}: {str(exc)[:200]}")
                self._last_exception = exc
                action, drives, fingerprint = "rest", None, ""
            if self._last_exception is not None and crashes >= 2:
                try:                                    # draft a fix for a human to review; never self-apply
                    selfrepair.propose(self.cfg.root, self.mind, self.health, self._last_exception, log=self.log)
                except Exception as exc:
                    self.log(f"self-repair drafting failed: {exc}")
            n += 1
            if ticks is not None and n >= ticks:
                break
            if interval and interval > 0:
                pause = interval
            elif drives is not None:
                pause = next_rest_sec(action, drives, fingerprint)
            else:
                pause = min(1800, 60 * (2 ** min(crashes, 5)))   # crash backoff: 2, 4, 8 ... 30 min
            self.log(f"the fly rests for {pause // 60} min {pause % 60} s")
            try:
                self.rest(pause, live=live)
            except KeyboardInterrupt:
                return 2
        return 2

    _mention_backoff: int = 0

    def rest(self, pause: int, live: bool = False, sleep=time.sleep) -> int:
        """Rest for `pause` seconds, but keep one antenna up: every few minutes
        look for @mentions on X and answer them straight away. Returns how
        many mentions were answered."""
        answered = 0
        end = time.time() + pause
        every = max(60, int(self.cfg.x.mentions_every_sec))
        next_check = time.time() + every
        while True:
            self.health.beat("resting")
            now = time.time()
            if now >= end:
                break
            if self.x.configured and now >= next_check:
                next_check = now + every + self._mention_backoff
                try:
                    out = self.act_replies(live=live, mood=(self.memory.last("drives") or {}).get("action", "curious"))
                except Exception as exc:                # never let a poll take the loop down
                    out = f"mentions failed: {exc}"
                if out.startswith(("mentions unavailable", "mentions failed")):
                    self._mention_backoff = min(1800, (self._mention_backoff or every) * 2)
                    self.log(f"  {out}; checking again in {(every + self._mention_backoff) // 60} min")
                else:
                    self._mention_backoff = 0
                if out.endswith("answered"):
                    answered += int(out.split()[0])
                    self.memory.save()
                    self._publish("reply", (self.memory.last("drives") or {}).get("action", "curious"))
            sleep(min(60, max(1, end - time.time())))
        return answered

    # -- actions ---------------------------------------------------------
    def context(self) -> str:
        return self.memory.summary()

    def act_website(self, refine: bool = False, changes: list[str] | None = None) -> dict[str, Any]:
        from .brand import render_favicons
        from .website import build_website

        site = self.cfg.root / "site"
        render_favicons(site)
        self.log("the fly is polishing its website" if refine else "the fly is designing its website")
        res = build_website(self.mind, site, context=self.context(), log=self.log, refine=refine, changes=changes)
        self.memory.add("builds", {"slug": "website", "title": "The Fly Dev website", "ok": res.ok,
                                   "path": str(self.cfg.root / "site"), "files": res.files,
                                   "log": f"source={res.source}; " + "; ".join(res.problems)[:800]})
        self.memory.note(f"built its website ({res.source}): {res.notes}"[:400])
        return {"website": res.source, "files": res.files, "notes": res.notes, "problems": res.problems}

    def act_brand(self, seed: int | None = None) -> dict[str, Any]:
        """Profile picture and banner for the fly's X page, plus a bio."""
        from .brand import render_banner, render_pfp

        copy = self.mind.brand(self.context())
        seed = seed if seed is not None else int(time.time())
        out = self.cfg.root / "site" / "brand"
        pfp = render_pfp(out / "pfp.png", seed=seed, mood=copy.mood)
        banner = render_banner(out / "banner.png", copy.tagline, seed=seed, mood=copy.mood,
                               symbol=self.cfg.launchpad.genesis_symbol or "FLYDEV")
        (out / "bio.txt").write_text(copy.bio + "\n", encoding="utf-8")
        self.memory.add("builds", {"slug": "brand", "title": "X profile picture and banner", "ok": True,
                                   "path": str(out), "files": ["pfp.png", "banner.png", "bio.txt"], "log": copy.tagline})
        self.memory.note(f"drew its X profile: {copy.tagline}")
        return {"pfp": str(pfp), "banner": str(banner), "tagline": copy.tagline, "bio": copy.bio, "mood": copy.mood}

    def act_browse(self, drives: Drives) -> dict[str, Any]:
        if hasattr(self.browser, "backfill_shots"):
            self.browser.backfill_shots(self.memory)
        topics = list(self.cfg.browser.seeds)
        for page in self.memory.recent("pages", 5):
            topics.extend(page.get("followups") or [])
        # Rotate through topics so successive sessions do not repeat.
        offset = len(self.memory.data["pages"]) % max(1, len(topics))
        topics = topics[offset:] + topics[:offset]
        notes = self.browser.explore(self.mind, self.memory, topics, budget=self.cfg.browser.max_pages_per_session)
        self.memory.note(f"browsed {len(notes)} pages", topics=topics[:3])
        learned = None
        if notes:
            text = "\n".join(f"- {n.title} <{n.url}>: {n.gist} need: {n.need_spotted}" for n in notes)
            try:
                learned = self.mind.reflect(text)
                self.memory.add("learnings", {"summary": learned.summary, "ideas": learned.ideas,
                                              "pages": [n.url for n in notes]})
                self.memory.note(f"learned: {learned.summary}"[:400])
                self.log(f"learned: {learned.summary}")
            except MindRefused as exc:
                self.memory.note(f"could not reflect: {exc}")
        return {"pages": [f"{n.title} -> {n.gist[:100]}" for n in notes], "topics": topics[:3],
                "learned": learned.summary if learned else ""}

    def _tool_builds(self) -> list[dict[str, Any]]:
        return [b for b in self.memory.data.get("builds", [])
                if b.get("slug") not in ("website", "brand") and (self.cfg.workshop_dir / str(b.get("slug"))).is_dir()]

    def act_build(self, drives: Drives) -> dict[str, Any]:
        tools = self._tool_builds()
        broken = [b for b in tools if not b.get("ok")]
        if broken:
            return self.act_repair(broken[-1])
        # Every third build, improve something that already works.
        if tools and len(self.memory.data.get("builds", [])) % 3 == 2:
            oldest = min(tools, key=lambda b: float(b.get("touched_ts") or b.get("ts") or 0))
            return self.act_improve(oldest)
        idea = self.mind.ideate(self.context())
        self.memory.add("ideas", {"slug": idea.slug, "title": idea.title, "for_whom": idea.for_whom,
                                  "pitch": idea.pitch, "why": idea.why_needed})
        for page in self.memory.recent("pages", 20):
            page["used"] = True
        result = self.workshop.build(idea, mind=self.mind, log_fn=self.log)
        self.memory.add("builds", {"slug": result.slug, "title": idea.title, "ok": result.ok,
                                   "path": str(result.path), "files": result.files, "log": result.log[-1500:]})
        return {"built": idea.title, "path": str(result.path), "ok": result.ok, "files": result.files,
                "log_tail": result.log[-600:], "pitch": idea.pitch}

    def has_launched(self) -> bool:
        return any(l.get("live") for l in self.memory.data.get("launches") or [])

    def act_repair(self, build: dict[str, Any]) -> dict[str, Any]:
        slug, title = str(build.get("slug")), str(build.get("title") or build.get("slug"))
        self.log(f"the fly is repairing {title}")
        result = self.workshop.repair(slug, title, self.mind, log_fn=self.log)
        build.update({"ok": result.ok, "log": result.log[-1500:], "touched_ts": time.time(),
                      "touched_at": self.memory.data["journal"][-1]["at"] if self.memory.data["journal"] else None,
                      "files": result.files or build.get("files")})
        self.memory.note(f"repaired {title}: {'tests pass' if result.ok else 'still failing'}")
        return {"repaired": title, "ok": result.ok, "log_tail": result.log[-600:]}

    def act_improve(self, build: dict[str, Any]) -> dict[str, Any]:
        slug, title = str(build.get("slug")), str(build.get("title") or build.get("slug"))
        pitch = next((i.get("pitch", "") for i in self.memory.data.get("ideas", []) if i.get("slug") == slug or i.get("title") == title), "")
        self.log(f"the fly is improving {title}")
        result, what = self.workshop.improve(slug, title, pitch, self.mind, context=self.context(), log_fn=self.log)
        build.update({"ok": result.ok, "log": result.log[-1500:], "touched_ts": time.time(), "files": result.files or build.get("files")})
        changes = build.setdefault("changes", [])
        if what:
            changes.append({"at": self.memory.data["journal"][-1]["at"] if self.memory.data["journal"] else None, "what": what})
            self.memory.note(f"improved {title}: {what}"[:400])
        else:
            self.memory.note(f"looked at {title}; left it alone")
        return {"improved": title, "what": what, "ok": result.ok}

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
            "pair": lp.quote, "pair_token": lp.pair_token,
            "token": plan.token, "curve": plan.curve, "problems": plan.problems, "calldata": plan.calldata[:10],
            "pons_url": pons_token_url(plan.token) if plan.status == "confirmed" else "",
        })
        self.log(plan.describe())
        if plan.status == "confirmed":
            self.memory.note(f"launched ${symbol} on Pons, paired with {lp.quote}: {pons_token_url(plan.token)}", tx=plan.tx_hash)
            self.visit_coin(params.name, symbol, plan.token, plan.tx_hash)
        return {"launch": plan.describe(), "status": plan.status, "tagline": concept.tagline}

    def visit_coin(self, name: str, symbol: str, token: str, tx: str) -> list[str]:
        """After a launch the fly goes to look at its coin: the Pons page and the
        transaction on the explorer, on the fly cam and in the browsing feed."""
        stops = [(pons_token_url(token), f"{name} (${symbol}) on Pons", "the fly checks on its own coin"),
                 (f"{self.cfg.launchpad.explorer}/tx/{tx if tx.startswith('0x') else '0x' + tx}" if tx else "", f"launch transaction for ${symbol}",
                  "the launch transaction on the explorer")]
        seen: list[str] = []
        for url, title, note in stops:
            if not url:
                continue
            try:
                shot = self.browser.snapshot(url)
                tall = getattr(self.browser, "_last_tall", None)
                if getattr(self, "cam", None) and self.cam.configured:
                    self.cam.show_page(url, title, tall, note=note)
                    time.sleep(6)                       # long enough for the cam to pan over it
            except Exception as exc:                    # a missing browser must not undo a launch
                self.log(f"  could not look at {url}: {exc}")
                shot = ""
            self.memory.add("pages", {"url": url, "title": title, "gist": note, "need": "", "interesting": True,
                                      "followups": [], "shot": shot, "coin": symbol})
            seen.append(url)
        self.memory.save()
        return seen
