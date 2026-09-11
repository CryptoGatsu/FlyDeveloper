"""Export the fly's state for the website and (optionally) push it.

`export_site` writes `site/data/state.json` plus copies of every meme into
`site/memes/`, sanitized for the public: no calldata, no wallet balances, no
problems text beyond a short status. `publish` commits `site/`, `memes/` and
`workshop/` and pushes to the current branch so a static host (Vercel,
GitHub Pages) redeploys.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import FlyConfig
from .memory import Memory

EXPLORER = "https://robinhoodchain.blockscout.com"


def _meme_public_path(path: str) -> str:
    return f"memes/{Path(path).name}"


def _mood_from(drives: dict[str, float]) -> str:
    if not drives:
        return ""
    names = {"curiosity": "curious", "appetite": "hungry", "boldness": "hyped", "craft": "scheming", "humor": "smug", "fatigue": "tired"}
    best = max(names, key=lambda k: float(drives.get(k, 0)))
    return names[best]


def build_state(cfg: FlyConfig, mem: Memory, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    d = mem.data
    last_drives = mem.last("drives") or {}
    memes = [
        {"at": m.get("at"), "top": m.get("top"), "bottom": m.get("bottom"), "alt": m.get("alt"),
         "mood": m.get("mood"), "src": _meme_public_path(m.get("path", ""))}
        for m in d.get("memes", []) if m.get("path") and Path(m["path"]).is_file()
    ]
    coins = []
    for l in d.get("launches", []):
        coins.append({
            "at": l.get("at"), "name": l.get("name"), "symbol": l.get("symbol"),
            "description": l.get("description"), "live": bool(l.get("live")), "status": l.get("status"),
            "tx": l.get("tx") or "", "token": l.get("token") or "", "curve": l.get("curve") or "",
            "logo": l.get("logo") or "", "meme": _meme_public_path(l.get("meme", "")) if l.get("meme") else "",
            "genesis": bool(l.get("genesis")), "buyback": l.get("buyback"),
            "explorer_tx": f"{EXPLORER}/tx/{l['tx']}" if l.get("tx") else "",
            "explorer_token": f"{EXPLORER}/token/{l['token']}" if l.get("token") else "",
        })
    pages = [
        {"at": p.get("at"), "url": p.get("url"), "title": p.get("title"), "gist": p.get("gist"),
         "need": p.get("need"), "interesting": p.get("interesting"), "followups": p.get("followups") or []}
        for p in d.get("pages", [])
    ]
    builds = [
        {"at": b.get("at"), "slug": b.get("slug"), "title": b.get("title"), "ok": b.get("ok"),
         "files": b.get("files") or [], "repo_path": f"workshop/{b.get('slug')}"}
        for b in d.get("builds", [])
    ]
    ideas = [{"at": i.get("at"), "title": i.get("title"), "pitch": i.get("pitch"), "for_whom": i.get("for_whom"),
              "why": i.get("why")} for i in d.get("ideas", [])]
    journal = [{"at": j.get("at"), "text": j.get("text")} for j in d.get("journal", [])]
    drives = last_drives.get("drives") or {}
    mood = (extra or {}).get("mood") or _mood_from(drives)
    state = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fly": {
            "name": "The Fly Dev", "symbol": cfg.launchpad.genesis_symbol,
            "brain": cfg.brain.mode, "neurons": 138639 if cfg.brain.mode == "connectome" else cfg.brain.phantom_neurons,
            "mind": cfg.mind.model if cfg.mind.mode == "claude" else "offline",
            "chain": cfg.launchpad.chain_id, "factory": cfg.launchpad.factory,
            "armed": bool(cfg.launchpad.live), "wallet": extra.get("wallet", "") if extra else "",
            "repo": cfg.launchpad.website,
        },
        "now": {
            "at": last_drives.get("at"), "mood": mood,
            "action": last_drives.get("action"), "drives": last_drives.get("drives") or {},
            "probs": last_drives.get("probs") or {}, "brain": last_drives.get("brain") or {},
        },
        "counts": {"pages": len(pages), "memes": len(memes), "coins": len(coins),
                   "live_coins": sum(1 for c in coins if c["live"]), "builds": len(builds)},
        "pages": pages[::-1][:60],
        "memes": memes[::-1],
        "coins": coins[::-1],
        "builds": builds[::-1],
        "ideas": ideas[::-1][:20],
        "journal": journal[::-1][:40],
        "drives_history": [{"at": x.get("at"), "action": x.get("action"), "drives": x.get("drives")} for x in d.get("drives", [])][-96:],
    }
    return state


def export_site(cfg: FlyConfig, mem: Memory, extra: dict[str, Any] | None = None) -> Path:
    site = cfg.root / "site"
    (site / "data").mkdir(parents=True, exist_ok=True)
    (site / "memes").mkdir(parents=True, exist_ok=True)
    for m in mem.data.get("memes", []):
        src = Path(m.get("path", ""))
        if src.is_file():
            dst = site / "memes" / src.name
            if not dst.is_file() or dst.stat().st_mtime < src.stat().st_mtime:
                shutil.copy2(src, dst)
    if cfg.site_domain:
        (site / "CNAME").write_text(cfg.site_domain + "\n", encoding="utf-8")
    state = build_state(cfg, mem, extra)
    out = site / "data" / "state.json"
    out.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    return out


def publish(cfg: FlyConfig, message: str, log=print) -> bool:
    """git add + commit + push the public artefacts. Returns True on a push."""
    root = cfg.root
    paths = ["site", "workshop"]
    shutil.rmtree(root / "site" / "__qa", ignore_errors=True)
    try:
        subprocess.run(["git", "-C", str(root), "add", "-A", *paths], check=True, capture_output=True, text=True)
        diff = subprocess.run(["git", "-C", str(root), "diff", "--cached", "--quiet"])
        if diff.returncode == 0:
            return False                                   # nothing new
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", f"fly: {message}"], check=True, capture_output=True, text=True)
        for attempt in range(3):
            # Bring in anything pushed elsewhere first; on a clash in the fly's
            # own generated files, the fly's newer copy wins.
            subprocess.run(["git", "-C", str(root), "pull", "--rebase", "--autostash", "-X", "theirs", "-q"],
                           capture_output=True, text=True)
            push = subprocess.run(["git", "-C", str(root), "push"], capture_output=True, text=True)
            if push.returncode == 0:
                log(f"published: {message}")
                return True
            time.sleep(2 ** attempt)
        log(f"publish failed: {push.stderr.strip()[-300:]}")
    except subprocess.CalledProcessError as exc:
        log(f"publish failed: {(exc.stderr or str(exc)).strip()[-300:]}")
    return False
