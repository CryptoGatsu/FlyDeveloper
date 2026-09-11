from PIL import Image

from fly.brand import render_banner, render_pfp


def test_pfp_and_banner_sizes(tmp_path):
    p = render_pfp(tmp_path / "pfp.png", seed=3)
    b = render_banner(tmp_path / "banner.png", "138,639 neurons. ships tiny tools and worse jokes.", seed=3)
    assert Image.open(p).size == (500, 500)
    assert Image.open(b).size == (1500, 500)
    assert p.stat().st_size > 5000 and b.stat().st_size > 10000
