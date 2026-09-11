"""Procedural fly memes with Pillow: a drawn fly, a mood, two captions.

No external image assets are needed; the fly is drawn from ellipses so every
meme is generated from the brain state's seed.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",
    "/Library/Fonts/Impact.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]

MOOD_PALETTES = {
    "curious": ((255, 236, 179), (255, 183, 77)),
    "hungry": ((255, 205, 210), (239, 83, 80)),
    "tired": ((207, 216, 220), (96, 125, 139)),
    "hyped": ((200, 230, 201), (0, 200, 83)),
    "smug": ((225, 190, 231), (142, 36, 170)),
    "scheming": ((187, 222, 251), (30, 136, 229)),
}


def _font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _caption(draw, text: str, width: int, y: int, from_bottom: bool, size: int = 64) -> None:
    if not text:
        return
    font = _font(size)
    lines = _wrap(draw, text.upper(), font, width - 60)
    line_h = size + 8
    total = line_h * len(lines)
    y0 = y - total if from_bottom else y
    for i, line in enumerate(lines):
        w = draw.textlength(line, font=font)
        x = (width - w) / 2
        yy = y0 + i * line_h
        draw.text((x, yy), line, font=font, fill="white", stroke_width=4, stroke_fill="black")


def _draw_fly(img: Image.Image, cx: float, cy: float, scale: float, rng: random.Random, mood: str) -> None:
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tilt = rng.uniform(-0.35, 0.35)

    def rot(x, y):
        return (cx + x * math.cos(tilt) - y * math.sin(tilt), cy + x * math.sin(tilt) + y * math.cos(tilt))

    # wings (translucent)
    for side in (-1, 1):
        flap = rng.uniform(0.6, 1.1)
        pts = [rot(0, -10 * scale)]
        for k in range(1, 13):
            a = math.pi * k / 12
            pts.append(rot(side * (20 + 120 * math.sin(a)) * scale, (-10 - 90 * flap * math.sin(a) * (1 - k / 14)) * scale))
        d.polygon(pts, fill=(200, 225, 255, 120), outline=(60, 80, 120, 200))
    # legs
    for i in range(3):
        for side in (-1, 1):
            x0, y0 = rot(side * 25 * scale, (10 + i * 22) * scale)
            x1, y1 = rot(side * (70 + i * 10) * scale, (40 + i * 30) * scale)
            x2, y2 = rot(side * (90 + i * 10) * scale, (80 + i * 25) * scale)
            d.line([(x0, y0), (x1, y1), (x2, y2)], fill=(30, 30, 30, 255), width=max(2, int(4 * scale)))
    # abdomen with stripes
    ab = [rot(-45 * scale, 20 * scale), rot(45 * scale, 160 * scale)]
    d.ellipse([min(ab[0][0], ab[1][0]), min(ab[0][1], ab[1][1]), max(ab[0][0], ab[1][0]), max(ab[0][1], ab[1][1])], fill=(70, 50, 40, 255), outline=(20, 15, 10, 255), width=3)
    for i in range(4):
        y = (55 + i * 25) * scale
        p0, p1 = rot(-38 * scale, y), rot(38 * scale, y)
        d.line([p0, p1], fill=(35, 25, 20, 255), width=max(2, int(5 * scale)))
    # thorax
    th = [rot(-40 * scale, -40 * scale), rot(40 * scale, 40 * scale)]
    d.ellipse([min(th[0][0], th[1][0]), min(th[0][1], th[1][1]), max(th[0][0], th[1][0]), max(th[0][1], th[1][1])], fill=(90, 65, 50, 255), outline=(20, 15, 10, 255), width=3)
    # head
    hd = [rot(-32 * scale, -100 * scale), rot(32 * scale, -40 * scale)]
    d.ellipse([min(hd[0][0], hd[1][0]), min(hd[0][1], hd[1][1]), max(hd[0][0], hd[1][0]), max(hd[0][1], hd[1][1])], fill=(110, 80, 60, 255), outline=(20, 15, 10, 255), width=3)
    # compound eyes: big and red, expression by mood
    for side in (-1, 1):
        ex, ey = rot(side * 22 * scale, -78 * scale)
        r = 18 * scale
        d.ellipse([ex - r, ey - r, ex + r, ey + r], fill=(200, 40, 40, 255), outline=(60, 10, 10, 255), width=2)
        hx, hy = rot(side * 17 * scale, -84 * scale)
        d.ellipse([hx - r / 3, hy - r / 3, hx + r / 3, hy + r / 3], fill=(255, 210, 210, 255))
        if mood in ("tired", "smug", "scheming"):
            lx0, ly0 = rot(side * 22 * scale - 20 * scale, -96 * scale)
            lx1, ly1 = rot(side * 22 * scale + 20 * scale, -92 * scale)
            d.line([(lx0, ly0), (lx1, ly1)], fill=(110, 80, 60, 255), width=max(3, int(8 * scale)))
    # antennae
    for side in (-1, 1):
        a0 = rot(side * 8 * scale, -100 * scale)
        a1 = rot(side * 30 * scale, -130 * scale)
        d.line([a0, a1], fill=(30, 30, 30, 255), width=max(2, int(3 * scale)))
    # mood props
    if mood == "hyped":
        for _ in range(12):
            px, py = rng.uniform(cx - 220 * scale, cx + 220 * scale), rng.uniform(cy - 200 * scale, cy + 200 * scale)
            d.line([(px, py), (px + rng.uniform(-14, 14), py + rng.uniform(-14, 14))], fill=(255, 255, 255, 230), width=3)
    if mood == "hungry":
        bx, by = rot(90 * scale, 120 * scale)
        d.ellipse([bx - 30 * scale, by - 20 * scale, bx + 30 * scale, by + 20 * scale], fill=(255, 224, 130, 255), outline=(120, 90, 20, 255), width=3)
    img.alpha_composite(layer)


def render_meme(top: str, bottom: str, out_path: Path, seed: int = 0, mood: str = "curious", size: int = 800) -> Path:
    rng = random.Random(seed)
    c0, c1 = MOOD_PALETTES.get(mood, MOOD_PALETTES["curious"])
    img = Image.new("RGBA", (size, size), c0 + (255,))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / size
        col = tuple(int(c0[i] * (1 - t) + c1[i] * t) for i in range(3)) + (255,)
        d.line([(0, y), (size, y)], fill=col)
    # a few background bubbles
    for _ in range(18):
        r = rng.uniform(6, 40)
        x, y = rng.uniform(0, size), rng.uniform(0, size)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 40))
    _draw_fly(img, size / 2 + rng.uniform(-40, 40), size / 2 + rng.uniform(-20, 40), size / 800 * rng.uniform(1.4, 1.9), rng, mood)
    d = ImageDraw.Draw(img)
    _caption(d, top, size, 24, from_bottom=False)
    _caption(d, bottom, size, size - 24, from_bottom=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, "PNG", optimize=True)
    return out_path
