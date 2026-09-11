"""Headless-browser screenshots of the site, used as visual QA for the fly's
own website. Needs a Chrome/Chromium binary; otherwise returns nothing."""

from __future__ import annotations

import functools
import glob
import http.server
import os
import shutil
import socket
import subprocess
import threading
from pathlib import Path

CHROME_CANDIDATES = [
    os.environ.get("FLY_CHROME", ""),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
    "C:/Program Files/Google/Chrome/Application/chrome.exe",
]


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if not c:
            continue
        if os.path.isfile(c):
            return c
        found = shutil.which(c)
        if found:
            return found
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",
                    os.path.expanduser("~/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium"),
                    os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome")):
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # noqa: D401
        pass


def screenshot_site(site_dir: Path, out_dir: Path, routes=("", "coins"), chrome: str | None = None) -> list[Path]:
    """Serve `site_dir` on a free port and screenshot routes at desktop and
    phone widths. Returns the PNG paths (possibly empty)."""
    chrome = chrome or find_chrome()
    if not chrome:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    handler = functools.partial(_Quiet, directory=str(site_dir))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    shots: list[Path] = []
    # Chrome refuses windows narrower than 500px, so the phone view is a
    # 400px-wide iframe inside a 520px window, then cropped to the frame.
    qa_dir = site_dir / "__qa"
    qa_dir.mkdir(exist_ok=True)
    try:
        for route in routes:
            name = route or "home"
            wrapper = qa_dir / f"phone-{name}.html"
            wrapper.write_text(
                "<!doctype html><html><body style='margin:0;background:#000'>"
                f"<iframe src='/{route}' style='display:block;border:0;width:400px;height:1400px'></iframe>"
                "</body></html>", encoding="utf-8")
            targets = (
                ("desktop", "1200,1600", f"http://127.0.0.1:{port}/{route}", None),
                ("phone", "520,1400", f"http://127.0.0.1:{port}/__qa/phone-{name}.html", (0, 0, 400, 1400)),
            )
            for label, size, url, crop in targets:
                out = out_dir / f"{name}-{label}.png"
                cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                       f"--window-size={size}", f"--screenshot={out}", "--virtual-time-budget=5000", url]
                try:
                    subprocess.run(cmd, capture_output=True, timeout=60)
                except (subprocess.TimeoutExpired, OSError):
                    continue
                if out.is_file() and out.stat().st_size > 0:
                    if crop:
                        from PIL import Image

                        Image.open(out).crop(crop).save(out)
                    shots.append(out)
    finally:
        server.shutdown()
        shutil.rmtree(qa_dir, ignore_errors=True)
    return shots


def shrink(path: Path, max_w: int, max_h: int) -> Path:
    """Downscale/crop a screenshot so it stays cheap to send to the mind."""
    from PIL import Image

    img = Image.open(path)
    img = img.crop((0, 0, img.width, min(img.height, max_h)))
    if img.width > max_w:
        img = img.resize((max_w, int(img.height * max_w / img.width)))
    out = path.with_name(path.stem + "-small.png")
    img.convert("RGB").save(out, "PNG", optimize=True)
    return out


def edge_overflow(path: Path, edge_px: int = 3) -> float:
    """Fraction of image rows whose right edge holds non-background pixels.
    A page that fits its viewport ends in padding (background) on the right;
    content cut off at the edge (overflow) shows up as a high fraction."""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()
    # background = most common colour in the left edge column
    from collections import Counter

    bg = Counter(px[0, y] for y in range(0, h, 2)).most_common(1)[0][0]

    def differs(c):
        return sum(abs(c[i] - bg[i]) for i in range(3)) > 60

    rows = 0
    for y in range(h):
        if any(differs(px[w - 1 - k, y]) for k in range(edge_px)):
            rows += 1
    return rows / max(1, h)


def screenshot_url(url: str, out_path: Path, chrome: str | None = None, stamp: str = "",
                   width: int = 1100, height: int = 800, final_width: int = 720) -> Path | None:
    """Screenshot a live web page as the fly sees it, downscale to a small
    JPEG and stamp it with the time and URL so viewers can tell it is real."""
    chrome = chrome or find_chrome()
    if not chrome:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".raw.png")
    cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
           f"--window-size={width},{height}", f"--screenshot={tmp}", "--virtual-time-budget=6000", url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if not tmp.is_file() or tmp.stat().st_size == 0:
        return None
    from PIL import Image, ImageDraw

    from .memes import _font

    img = Image.open(tmp).convert("RGB")
    if img.width > final_width:
        img = img.resize((final_width, int(img.height * final_width / img.width)), Image.LANCZOS)
    if stamp:
        d = ImageDraw.Draw(img)
        font = _font(13)
        text = stamp[:140]
        tw = d.textlength(text, font=font)
        d.rectangle([0, img.height - 22, min(img.width, tw + 16), img.height], fill=(11, 13, 12))
        d.text((8, img.height - 19), text, font=font, fill=(158, 240, 122))
    img.save(out_path, "JPEG", quality=72, optimize=True)
    tmp.unlink(missing_ok=True)
    return out_path
