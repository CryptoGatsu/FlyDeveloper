from PIL import Image

from fly.brand import render_banner, render_pfp


def test_pfp_and_banner_sizes(tmp_path):
    p = render_pfp(tmp_path / "pfp.png", seed=3)
    b = render_banner(tmp_path / "banner.png", "138,639 neurons. ships tiny tools and worse jokes.", seed=3)
    assert Image.open(p).size == (500, 500)
    assert Image.open(b).size == (1500, 500)
    assert p.stat().st_size > 5000 and b.stat().st_size > 10000


def test_favicons(tmp_path):
    from fly.brand import render_favicons
    out = render_favicons(tmp_path)
    assert {p.name for p in out} == {"favicon.png", "apple-touch-icon.png", "favicon.ico"}
    assert Image.open(tmp_path / "favicon.png").size == (64, 64)
