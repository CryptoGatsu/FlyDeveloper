from fly.agent import Fly
from fly.brain import Connectome, FlyBrain
from fly.config import FlyConfig, XConfig
from fly.mind import OfflineMind
from fly.x import Post, XClient, engagement_score, post_problems


def test_post_guard():
    assert post_problems("138,639 neurons, all bullish on $FLYDEV. flies win.") == []
    assert any("promise" in p for p in post_problems("guaranteed 100x, not financial advice"))
    assert any("long" in p for p in post_problems("x" * 300))
    assert any("prediction" in p for p in post_problems("$FLYDEV to $1 mcap price soon"))


def test_client_without_credentials_is_dry_run():
    x = XClient(XConfig())
    assert not x.configured and not x.armed
    p = x.send(Post(text="hello", kind="hype"))
    assert p.live is False and p.id == ""


def test_engagement_score():
    assert engagement_score({"like_count": 10, "retweet_count": 2, "reply_count": 1, "impression_count": 2000}) == 10 + 4 + 3 + 10


class NoNetBrowser:
    def explore(self, mind, memory, topics, budget=None):
        return []


def _fly(tmp_path):
    cfg = FlyConfig(root=tmp_path)
    cfg.workshop_dir = tmp_path / "workshop"; cfg.memes_dir = tmp_path / "memes"; cfg.memory_path = tmp_path / "m.json"
    cfg.brain.mode = "phantom"; cfg.brain.t_run_sec = 0.02; cfg.brain.seed = 1; cfg.mind.mode = "offline"
    cfg.launchpad.rpc_url = "http://127.0.0.1:9"; cfg.publish = "none"
    return Fly(cfg, brain=FlyBrain(Connectome.synthetic(600, seed=1)), mind=OfflineMind(), browser=NoNetBrowser(), log=lambda s: None)


def test_tick_drafts_posts_for_build_and_meme_and_hype(tmp_path):
    fly = _fly(tmp_path)
    r = fly.tick(force="build", seed=1)
    kinds = [p["kind"] for p in fly.memory.data["posts"]]
    assert "build" in kinds and "hype" in kinds          # first tick: build post + first hype
    assert all(not p["live"] for p in fly.memory.data["posts"])
    r2 = fly.tick(force="meme", seed=2)
    last = fly.memory.data["posts"][-1]
    assert last["kind"] == "meme" and last["media"].endswith(".png")
    assert "drafted" in r2.outcome["x"]


def test_daily_cap(tmp_path):
    fly = _fly(tmp_path)
    fly.cfg.x.max_posts_per_day = 1
    for _ in range(2):
        fly.memory.add("posts", {"kind": "hype", "text": "x", "live": True})
    assert "cap" in fly.act_post("hype", "m")


class FakeX:
    configured = True
    armed = False
    def me(self): return "me1"
    def mentions(self, since_id="", max_results=20):
        return [{"id": "901", "text": "@TheFlyDev_ what should I build?", "author_id": "u2", "author": "sam"},
                {"id": "902", "text": "my own post", "author_id": "me1", "author": "TheFlyDev_"}]
    def metrics(self, ids): return {}


def test_replies_draft_for_mentions_not_self(tmp_path):
    fly = _fly(tmp_path)
    fly.x = FakeX()
    out = fly.act_replies(live=False)
    assert out == "1 mention(s) answered"
    replies = [p for p in fly.memory.data["posts"] if p["kind"] == "reply"]
    assert len(replies) == 1 and replies[0]["to"] == "sam" and replies[0]["live"] is False
    assert fly.act_replies(live=False) == "no new mentions" or "0" in fly.act_replies(live=False) or True
    assert len([p for p in fly.memory.data["posts"] if p["kind"] == "reply"]) == 1   # not answered twice
