"""The fly cam: near-live frames of what the fly is looking at.

While browsing, frames are posted to the site's /api/cam function (which
stores them in Vercel Blob); the /browsing page polls and shows the newest.
Each page yields a tall screenshot that is panned top-to-bottom in a few
crops a couple of seconds apart, so visitors see the fly "reading".
"""

from __future__ import annotations

import base64
import io
import threading
import time
from pathlib import Path


class FlyCam:
    def __init__(self, site_url: str, secret: str, log=None, pan_frames: int = 3, pan_gap_sec: float = 4.0):
        self.site_url = site_url.rstrip("/")
        self.secret = secret
        self.log = log or (lambda m: None)
        self.pan_frames = pan_frames
        self.pan_gap_sec = pan_gap_sec
        self._lock = threading.Lock()
        self._gen = 0

    @property
    def configured(self) -> bool:
        return bool(self.site_url and self.secret)

    # -- transport ---------------------------------------------------------
    def post(self, phase: str, url: str = "", title: str = "", note: str = "", frame_jpeg: bytes | None = None) -> bool:
        if not self.configured:
            return False
        import requests

        payload = {"phase": phase, "url": url, "title": title, "note": note}
        if frame_jpeg:
            payload["frame_b64"] = base64.standard_b64encode(frame_jpeg).decode("ascii")
        try:
            r = requests.post(f"{self.site_url}/api/cam", json=payload, headers={"x-fly-cam": self.secret}, timeout=30)
            if r.status_code >= 300:
                self.log(f"  cam: {r.status_code} {r.text[:120]}")
                return False
            return True
        except Exception as exc:
            self.log(f"  cam: {exc}")
            return False

    # -- frames --------------------------------------------------------------
    @staticmethod
    def crops(png_path: Path, n: int = 3, width: int = 800, height: int = 560) -> list[bytes]:
        """Pan a tall screenshot: n JPEG crops from top to bottom."""
        from PIL import Image

        img = Image.open(png_path).convert("RGB")
        if img.width > width:
            img = img.resize((width, int(img.height * width / img.width)), Image.LANCZOS)
        out = []
        span = max(0, img.height - height)
        for i in range(max(1, n)):
            top = int(span * (i / max(1, n - 1))) if n > 1 else 0
            crop = img.crop((0, top, img.width, min(img.height, top + height)))
            buf = io.BytesIO()
            crop.save(buf, "JPEG", quality=62, optimize=True)
            out.append(buf.getvalue())
        return out

    def show_page(self, url: str, title: str, tall_png: Path | None, note: str = "") -> None:
        """Post a pan over the page in the background while the mind reads it."""
        if not self.configured:
            return
        with self._lock:
            self._gen += 1
            gen = self._gen
        frames = self.crops(tall_png, self.pan_frames) if tall_png and Path(tall_png).is_file() else []

        def run():
            if not frames:
                self.post("browsing", url, title, note)
                return
            for i, fr in enumerate(frames):
                with self._lock:
                    if gen != self._gen:
                        return                       # a newer page took over
                self.post("browsing", url, title, note, fr)
                if i < len(frames) - 1:
                    time.sleep(self.pan_gap_sec)

        threading.Thread(target=run, daemon=True).start()

    def post_brain(self, payload: dict) -> bool:
        """Push the latest spike rasters (a few tens of KB of JSON)."""
        if not self.configured:
            return False
        import json

        import requests

        try:
            body = json.dumps(payload, separators=(",", ":"))
            if len(body) > 700_000:
                for r in payload.get("rasters", {}).values():
                    r["spikes"] = r.get("spikes", [])[:1200]
                body = json.dumps(payload, separators=(",", ":"))
            r = requests.post(f"{self.site_url}/api/brain", data=body, headers={"x-fly-cam": self.secret, "content-type": "application/json"}, timeout=30)
            if r.status_code >= 300:
                self.log(f"  brain cam: {r.status_code} {r.text[:120]}")
                return False
            return True
        except Exception as exc:
            self.log(f"  brain cam: {exc}")
            return False

    def searching(self, query: str) -> None:
        if self.configured:
            threading.Thread(target=self.post, args=("searching", "", "", f"searching: {query}"), daemon=True).start()

    def idle(self, note: str = "") -> None:
        if self.configured:
            with self._lock:
                self._gen += 1
            self.post("idle", note=note)


def tall_screenshot(url: str, out_png: Path, chrome: str | None = None, width: int = 1100, height: int = 2200) -> Path | None:
    """A tall capture of a live page for panning (and for the archive shot)."""
    import subprocess

    from .render import find_chrome

    chrome = chrome or find_chrome()
    if not chrome:
        return None
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
           f"--window-size={width},{height}", f"--screenshot={out_png}", "--virtual-time-budget=6000", url]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out_png if out_png.is_file() and out_png.stat().st_size > 0 else None
