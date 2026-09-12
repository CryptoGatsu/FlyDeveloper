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
    assert st["counts"] == {"pages": 0, "memes": 0, "coins": 0, "live_coins": 0, "builds": 0, "searches": 0, "posts": 0}


def test_build_links_point_at_github_branch(tmp_path):
    from fly.memory import Memory
    cfg = FlyConfig(root=tmp_path)
    mem = Memory(path=tmp_path / "m.json")
    mem.add("builds", {"slug": "ripeness-clock", "title": "Ripeness Clock", "ok": True, "files": ["README.md"]})
    mem.add("builds", {"slug": "website", "title": "site", "ok": True, "files": []})
    mem.add("builds", {"slug": "website", "title": "site again", "ok": True, "files": []})
    mem.add("searches", {"query": "fly tools", "engine": "duckduckgo", "results": [{"title": "a", "url": "https://a.test"}]})
    mem.add("learnings", {"summary": "learned a thing", "ideas": ["x"]})
    st = build_state(cfg, mem)
    tool = [b for b in st["builds"] if b["slug"] == "ripeness-clock"][0]
    assert tool["url"].startswith("https://github.com/CryptoGatsu/FlyDeveloper/tree/") and tool["url"].endswith("/workshop/ripeness-clock")
    assert "flydev.tech" not in tool["url"]
    assert len([b for b in st["builds"] if b["slug"] == "website"]) == 1      # collapsed
    assert st["fly"]["repo"] == "https://github.com/CryptoGatsu/FlyDeveloper"
    assert st["searches"][0]["query"] == "fly tools" and st["learnings"][0]["summary"] == "learned a thing"


def test_prune_shots(tmp_path):
    from fly.publish import _prune_shots
    d = tmp_path / "shots"; d.mkdir()
    import os, time
    (d / "keep.jpg").write_bytes(b"1"); (d / "old.jpg").write_bytes(b"1"); (d / "fresh.jpg").write_bytes(b"1")
    os.utime(d / "old.jpg", (time.time() - 3 * 86400, time.time() - 3 * 86400))
    _prune_shots(d, {"browsing/shots/keep.jpg"})
    assert (d / "keep.jpg").is_file() and not (d / "old.jpg").exists() and (d / "fresh.jpg").is_file()


def test_literal_unicode_escapes_are_decoded():
    from fly.mind import unescape_text, unescape_model, PageDigest
    assert unescape_text("a \\u2014 b") == "a \u2014 b"
    m = unescape_model(PageDigest(gist="x \\u2019 y", need_spotted="", interesting=True, followups=["\\u00e9"]))
    assert m.gist == "x \u2019 y" and m.followups == ["\u00e9"]
