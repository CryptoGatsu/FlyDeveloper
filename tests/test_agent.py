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
