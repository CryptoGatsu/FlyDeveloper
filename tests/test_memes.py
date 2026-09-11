from PIL import Image

from fly.memes import render_meme


def test_render_all_moods(tmp_path):
    for mood in ("curious", "hungry", "tired", "hyped", "smug", "scheming"):
        out = render_meme("TOP TEXT THAT IS QUITE LONG AND WRAPS AROUND", "bottom", tmp_path / f"{mood}.png", seed=3, mood=mood, size=400)
        img = Image.open(out)
        assert img.size == (400, 400)


def test_render_without_bottom(tmp_path):
    out = render_meme("only top", "", tmp_path / "t.png", size=300)
    assert out.stat().st_size > 1000
