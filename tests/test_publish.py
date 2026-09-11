import json

from fly.agent import Fly
from fly.brain import Connectome, FlyBrain
from fly.config import FlyConfig
from fly.mind import OfflineMind
from fly.publish import build_state, export_site


class NoNetBrowser:
    def explore(self, mind, memory, topics, budget=None):
        memory.add("pages", {"url": "https://example.test/a", "title": "A page", "gist": "about flies", "interesting": True})
        return []


def test_export_site_writes_state_and_copies_memes(tmp_path):
    cfg = FlyConfig(root=tmp_path)
    cfg.workshop_dir = tmp_path / "workshop"; cfg.memes_dir = tmp_path / "memes"; cfg.memory_path = tmp_path / "m.json"
    cfg.brain.mode = "phantom"; cfg.brain.t_run_sec = 0.02; cfg.brain.seed = 1; cfg.mind.mode = "offline"
    cfg.publish = "site"; cfg.launchpad.rpc_url = "http://127.0.0.1:9"
    fly = Fly(cfg, brain=FlyBrain(Connectome.synthetic(600, seed=1)), mind=OfflineMind(), browser=NoNetBrowser(), log=lambda s: None)
    fly.tick(force="meme", seed=1)
    fly.tick(force="browse", seed=2)
    fly.tick(force="launch", seed=3)
    state = json.loads((tmp_path / "site" / "data" / "state.json").read_text())
    assert state["counts"]["memes"] >= 1 and state["counts"]["pages"] == 1 and state["counts"]["coins"] >= 1
    assert state["coins"][0]["symbol"] == "FLYDEV" and state["coins"][0]["genesis"] is True
    assert state["memes"][0]["src"].startswith("memes/")
    assert (tmp_path / "site" / state["memes"][0]["src"]).is_file()
    assert "calldata" not in json.dumps(state) and "problems" not in json.dumps(state)
    assert state["now"]["mood"]


def test_build_state_empty_memory(tmp_path):
    from fly.memory import Memory

    cfg = FlyConfig(root=tmp_path)
    st = build_state(cfg, Memory(path=tmp_path / "m.json"))
    assert st["counts"] == {"pages": 0, "memes": 0, "coins": 0, "live_coins": 0, "builds": 0}
