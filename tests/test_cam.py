from pathlib import Path

from fly.cam import FlyCam
from fly.memes import render_meme


def test_crops_pan_top_to_bottom(tmp_path):
    png = render_meme("a", "b", tmp_path / "tall.png", size=900)
    frames = FlyCam.crops(png, 3, width=400, height=200)
    assert len(frames) == 3 and all(f[:2] == b"\xff\xd8" for f in frames)


def test_unconfigured_cam_is_silent(tmp_path):
    cam = FlyCam("", "")
    assert not cam.configured
    assert cam.post("browsing") is False
    cam.show_page("https://x", "t", None); cam.searching("q"); cam.idle()


def test_show_page_posts_frames(tmp_path, monkeypatch):
    import time
    cam = FlyCam("https://flydev.tech", "s", pan_frames=2, pan_gap_sec=0.05)
    posted = []
    monkeypatch.setattr(cam, "post", lambda phase, url="", title="", note="", frame_jpeg=None: posted.append((phase, url, bool(frame_jpeg))) or True)
    png = render_meme("a", "b", tmp_path / "t.png", size=600)
    cam.show_page("https://a.test", "A", png)
    time.sleep(0.5)
    assert posted and all(p[0] == "browsing" and p[2] for p in posted) and len(posted) == 2
