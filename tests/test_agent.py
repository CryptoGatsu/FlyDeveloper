import json

from fly.agent import Fly
from fly.brain import Connectome, FlyBrain
from fly.config import FlyConfig
from fly.mind import OfflineMind


class NoNetBrowser:
    def explore(self, mind, memory, topics, budget=None):
        memory.add("pages", {"url": "https://example.test/a", "title": "A page", "gist": "about flies",
                             "interesting": True, "followups": ["fly tools"]})
        return []


def _fly(tmp_path):
    cfg = FlyConfig(root=tmp_path)
    cfg.workshop_dir = tmp_path / "workshop"
    cfg.memes_dir = tmp_path / "memes"
    cfg.memory_path = tmp_path / "memory.json"
    cfg.brain.mode = "phantom"
    cfg.brain.t_run_sec = 0.02
    cfg.brain.seed = 1
    cfg.mind.mode = "offline"
    cfg.launchpad.rpc_url = "http://127.0.0.1:9"
    brain = FlyBrain(Connectome.synthetic(800, seed=1))
    return Fly(cfg, brain=brain, mind=OfflineMind(), browser=NoNetBrowser(), log=lambda s: None)


def test_tick_build_creates_project_and_runs_tests(tmp_path):
    fly = _fly(tmp_path)
    r = fly.tick(force="build", seed=1)
    assert r.action == "build"
    assert r.outcome["ok"] is True, r.outcome["log_tail"]
    proj = tmp_path / "workshop" / r.outcome["path"].split("/")[-1]
    assert (proj / "README.md").is_file()
    assert (proj / "FLY_NOTES.md").is_file()
    mem = json.loads((tmp_path / "memory.json").read_text())
    assert mem["builds"][-1]["ok"] is True


def test_tick_meme_then_dry_launch(tmp_path):
    fly = _fly(tmp_path)
    r = fly.tick(force="meme", seed=2)
    assert (tmp_path / "memes").glob("*.png")
    assert r.outcome["top"]
    r2 = fly.tick(force="launch", seed=3)
    assert r2.outcome["status"] == "planned"
    last = fly.memory.last("launches")
    assert last["live"] is False
    assert last["symbol"] == "FLYDEV" and last["name"] == "The Fly Dev"   # genesis coin first
    assert "hosted URL" in " ".join(last["problems"])


def test_launch_overrides_and_post_genesis(tmp_path):
    from fly.drives import Drives

    fly = _fly(tmp_path)
    d = Drives(0.5, 0.5, 0.5, 0.9, 0.7, 0.1)
    out = fly.act_launch(d, name="Banana Coin", symbol="NANA", description="A joke. No promises.")
    assert fly.memory.last("launches")["symbol"] == "NANA"
    assert fly.memory.last("launches")["description"] == "A joke. No promises."
    # pretend genesis went live: later launches use the mind's own concept
    fly.memory.data["launches"].append({"live": True, "symbol": "FLYDEV", "name": "The Fly Dev", "ts": 0})
    fly.cfg.launchpad.max_launches_per_day = 5
    fly.act_launch(d)
    assert fly.memory.last("launches")["symbol"] != "FLYDEV"


def test_fee_policy_genesis_vs_others(tmp_path):
    from fly.drives import Drives

    fly = _fly(tmp_path)
    d = Drives(0.5, 0.5, 0.5, 0.9, 0.7, 0.1)
    fly.act_launch(d)
    genesis = fly.memory.last("launches")
    assert genesis["genesis"] is True and genesis["buyback"] is False     # fees stay in the wallet
    fly.memory.data["launches"].append({"live": True, "symbol": "FLYDEV", "name": "The Fly Dev", "ts": 0})
    fly.cfg.launchpad.max_launches_per_day = 5
    fly.act_launch(d)
    other = fly.memory.last("launches")
    assert other["genesis"] is False and other["buyback"] is True          # default: buy back and lock
    fly.cfg.launchpad.coin_fee_mode = "wallet"
    fly.act_launch(d)
    assert fly.memory.last("launches")["buyback"] is False


def test_tick_browse_uses_browser_and_rest(tmp_path):
    fly = _fly(tmp_path)
    r = fly.tick(force="browse", seed=4)
    assert fly.memory.last("pages")["title"] == "A page"
    r = fly.tick(force="rest", seed=5)
    assert "rest" in r.outcome


def test_policy_runs_without_force(tmp_path):
    fly = _fly(tmp_path)
    r = fly.tick(seed=6)
    assert r.action in ("browse", "build", "meme", "launch", "rest")
    assert abs(sum(r.probabilities.values()) - 1.0) < 1e-3


def test_build_repairs_broken_before_new(tmp_path):
    from fly.mind import ProjectFix, ProjectFile

    fly = _fly(tmp_path)
    r = fly.tick(force="build", seed=1)
    slug = r.outcome["path"].split("/")[-1]
    proj = tmp_path / "workshop" / slug
    (proj / "test_broken.py").write_text("def test_broken():\n    assert False\n")
    fly.memory.data["builds"][-1]["ok"] = False

    class Fixer(OfflineMind):
        def fix_project(self, idea, files, log):
            return ProjectFix(diagnosis="removed the bad assertion", files=[ProjectFile(path="test_broken.py", content="def test_broken():\n    assert True\n")])

    fly.mind = Fixer()
    r2 = fly.tick(force="build", seed=2)
    assert "repaired" in r2.outcome and r2.outcome["ok"] is True
    assert fly.memory.data["builds"][-1]["ok"] is True


def test_state_marks_built_ideas_and_wallet(tmp_path):
    from fly.publish import build_state

    fly = _fly(tmp_path)
    fly.tick(force="build", seed=1)
    fly.cfg.launchpad.private_key = "0x" + "11" * 32
    st = build_state(fly.cfg, fly.memory)
    assert st["ideas"][0]["built"] is True
    assert st["fly"]["wallet"].startswith("0x") and len(st["fly"]["wallet"]) == 42


def test_backfill_shots_fills_missing(tmp_path, monkeypatch):
    from fly.browser import Browser
    from fly.config import BrowserConfig
    from fly.memory import Memory

    mem = Memory(path=tmp_path / "m.json")
    mem.add("pages", {"url": "https://a.test", "title": "A", "shot": ""})
    mem.add("pages", {"url": "https://b.test", "title": "B", "shot": "browsing/shots/have.jpg"})
    b = Browser(BrowserConfig(), shots_dir=tmp_path / "shots")
    monkeypatch.setattr(b, "snapshot", lambda url: "browsing/shots/new.jpg")
    assert b.backfill_shots(mem) == 1
    assert mem.data["pages"][0]["shot"] == "browsing/shots/new.jpg"


def test_tick_survives_action_crash_and_trips_breaker(tmp_path):
    fly = _fly(tmp_path)

    class Crashy(OfflineMind):
        def caption(self, context, mood, theme=""):
            raise RuntimeError("meme machine jammed")

    fly.mind = Crashy()
    for _ in range(3):
        r = fly.tick(force="meme", seed=1)
        assert "error" in r.outcome
    assert not fly.health.allowed("meme")
    r = fly.tick(seed=2)
    assert r.action != "meme"


def test_visit_coin_after_launch_records_pons_page(tmp_path):
    fly = _fly(tmp_path)

    class Snap:
        _last_tall = None
        calls = []

        def snapshot(self, url):
            self.calls.append(url)
            return "browsing/shots/x.jpg"

    fly.browser = Snap()
    seen = fly.visit_coin("The Fly Dev", "FLYDEV", "0x" + "ab" * 20, "0x" + "cd" * 32)
    assert seen[0] == "https://www.ponsfamily.com/launchpad/0x" + "ab" * 20
    assert seen[1].startswith("https://robinhoodchain.blockscout.com/tx/0x")
    pages = fly.memory.data["pages"]
    assert pages[-2]["coin"] == "FLYDEV" and pages[-2]["shot"] == "browsing/shots/x.jpg"
    assert "Pons" in pages[-2]["title"]


def test_state_exports_pons_link_for_live_coins(tmp_path):
    from fly.publish import build_state

    fly = _fly(tmp_path)
    fly.memory.add("launches", {"name": "The Fly Dev", "symbol": "FLYDEV", "live": True, "status": "confirmed",
                                "token": "0x" + "ab" * 20, "tx": "0x" + "cd" * 32, "genesis": True})
    fly.memory.add("launches", {"name": "Dry", "symbol": "DRY", "live": False, "status": "planned", "token": ""})
    state = build_state(fly.cfg, fly.memory)
    coins = {c["symbol"]: c for c in state["coins"]}
    assert coins["FLYDEV"]["pons"] == "https://www.ponsfamily.com/launchpad/0x" + "ab" * 20
    assert coins["FLYDEV"]["pair"] == ""                         # old records carry no pair
    assert "DRY" not in coins                                   # rehearsals never reach the coins page


def test_dry_runs_are_not_coins_and_can_be_forgotten(tmp_path):
    from fly.publish import build_state

    fly = _fly(tmp_path)
    fly.memory.add("launches", {"name": "Hatched", "symbol": "HATCHED", "live": False, "status": "planned", "token": ""})
    fly.memory.add("launches", {"name": "The Fly Dev", "symbol": "FLYDEV", "live": True, "status": "confirmed",
                                "token": "0x" + "ab" * 20, "tx": "0x" + "cd" * 32, "genesis": True})
    assert [c["symbol"] for c in build_state(fly.cfg, fly.memory)["coins"]] == ["FLYDEV"]
    gone = fly.memory.forget_launches(symbol="hatched")
    assert [l["symbol"] for l in gone] == ["HATCHED"]
    assert fly.memory.forget_launches(symbol="FLYDEV") == []          # live launches stay
    assert [l["symbol"] for l in fly.memory.data["launches"]] == ["FLYDEV"]
