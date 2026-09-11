"""Brand assets the fly draws for itself: an X/Twitter profile picture
(500x500) and header banner (1500x500). Same procedural fly as the memes,
on a dark chitin background with a faint connectome behind it."""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .memes import _draw_fly, _font

BG = (11, 13, 12)
PANEL = (19, 23, 21)
GREEN = (158, 240, 122)
AMBER = (255, 209, 102)
INK = (216, 226, 218)
DIM = (138, 151, 142)


def _dark_gradient(w: int, h: int, seed: int) -> Image.Image:
    img = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        col = tuple(int(BG[i] * (1 - t) + PANEL[i] * t) for i in range(3)) + (255,)
        d.line([(0, y), (w, y)], fill=col)
    return img


def _connectome(img: Image.Image, seed: int, n: int = 90, alpha: int = 70, region=None) -> None:
    """A faint random graph: neurons as dots, synapses as thin lines."""
    rng = random.Random(seed)
    w, h = img.size
    x0, y0, x1, y1 = region or (0, 0, w, h)
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    pts = [(rng.uniform(x0, x1), rng.uniform(y0, y1)) for _ in range(n)]
    for i, (ax, ay) in enumerate(pts):
        for j in range(i + 1, n):
            bx, by = pts[j]
            if math.hypot(ax - bx, ay - by) < (x1 - x0) * 0.16 and rng.random() < 0.35:
                d.line([(ax, ay), (bx, by)], fill=GREEN + (alpha // 2,), width=1)
    for (ax, ay) in pts:
        r = rng.uniform(1.2, 3.2)
        d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=GREEN + (alpha,))
    img.alpha_composite(layer)


def _glow(img: Image.Image, cx: float, cy: float, radius: float, color, alpha: int = 90) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=color + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(radius / 2.5))
    img.alpha_composite(layer)


def render_pfp(out_path: Path, seed: int = 0, mood: str = "smug", size: int = 500) -> Path:
    rng = random.Random(seed)
    img = _dark_gradient(size, size, seed)
    _connectome(img, seed + 1, n=70, alpha=60)
    _glow(img, size / 2, size / 2 + 20, size * 0.36, GREEN, alpha=70)
    # thin ring
    d = ImageDraw.Draw(img)
    d.ellipse([size * 0.06, size * 0.06, size * 0.94, size * 0.94], outline=GREEN + (120,), width=3)
    _draw_fly(img, size / 2, size / 2 + 10, size / 800 * 2.15, rng, mood)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path


def render_banner(out_path: Path, tagline: str, seed: int = 0, mood: str = "scheming",
                  handle: str = "@TheFlyDev_", site: str = "flydev.tech", symbol: str = "FLYDEV",
                  size: tuple[int, int] = (1500, 500)) -> Path:
    w, h = size
    rng = random.Random(seed)
    img = _dark_gradient(w, h, seed)
    _connectome(img, seed + 2, n=140, alpha=55, region=(w * 0.55, 0, w, h))
    _connectome(img, seed + 3, n=40, alpha=28, region=(0, 0, w * 0.55, h))
    _glow(img, w * 0.78, h * 0.55, h * 0.42, GREEN, alpha=60)
    _draw_fly(img, w * 0.78, h * 0.52, h / 800 * 2.0, rng, mood)

    d = ImageDraw.Draw(img)
    title_font = _font(int(h * 0.19))
    tag_font = _font(int(h * 0.075))
    small_font = _font(int(h * 0.06))
    x = int(w * 0.06)
    d.text((x, int(h * 0.20)), "The Fly Dev", font=title_font, fill=INK)
    # tagline, wrapped to the left 55% of the banner
    max_w = int(w * 0.50)
    words, lines, cur = tagline.split(), [], ""
    for word in words:
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=tag_font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    y = int(h * 0.20) + int(h * 0.19) + int(h * 0.06)
    for line in lines[:2]:
        d.text((x, y), line, font=tag_font, fill=DIM)
        y += int(h * 0.075) + 8
    footer = f"{site}   ·   ${symbol}   ·   {handle}"
    d.text((x, int(h * 0.84)), footer, font=small_font, fill=GREEN)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path
