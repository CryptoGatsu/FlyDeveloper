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
REPO_URL = "https://github.com/CryptoGatsu/FlyDeveloper"


def current_branch(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=10)
        name = out.stdout.strip()
        return name if out.returncode == 0 and name and name != "HEAD" else "main"
    except Exception:
        return "main"


def _meme_public_path(path: str) -> str:
    return f"memes/{Path(path).name}"


def _wallet_address(cfg: FlyConfig) -> str:
    key = cfg.launchpad.private_key.strip()
    if not key:
        return ""
    try:
        from eth_account import Account

        return Account.from_key(key).address
    except Exception:
        return ""


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
         "need": p.get("need"), "interesting": p.get("interesting"), "followups": p.get("followups") or [],
         "shot": p.get("shot") or ""}
        for p in d.get("pages", [])
    ]
    branch = current_branch(cfg.root)
    builds = []
    for b in d.get("builds", []):
        slug = b.get("slug") or ""
        if slug == "website":
            repo_path, kind = "site", "website"
        elif slug == "brand":
            repo_path, kind = "site/brand", "brand"
        else:
            repo_path, kind = f"workshop/{slug}", "tool"
        builds.append({
            "at": b.get("at"), "slug": slug, "title": b.get("title"), "ok": b.get("ok"), "kind": kind,
            "files": b.get("files") or [], "repo_path": repo_path,
            "changes": [{"at": c.get("at"), "what": c.get("what")} for c in (b.get("changes") or [])][-5:],
            "url": f"{REPO_URL}/tree/{branch}/{repo_path}",
            "readme_url": f"{REPO_URL}/blob/{branch}/{repo_path}/README.md" if kind == "tool" else "",
        })
    # keep only the latest website/brand build; the rest is history noise
    seen_kinds: set[str] = set()
    collapsed = []
    for b in reversed(builds):
        if b["kind"] in ("website", "brand"):
            if b["kind"] in seen_kinds:
                continue
            seen_kinds.add(b["kind"])
        collapsed.append(b)
    builds = list(reversed(collapsed))
    searches = [{"at": x.get("at"), "query": x.get("query"), "results": x.get("results") or [], "engine": x.get("engine")}
                for x in d.get("searches", [])]
    learnings = [{"at": x.get("at"), "summary": x.get("summary"), "ideas": x.get("ideas") or []}
                 for x in d.get("learnings", [])]
    built_slugs = {b.get("slug") for b in d.get("builds", [])} | {b.get("title") for b in d.get("builds", [])}
    ideas = [{"at": i.get("at"), "slug": i.get("slug"), "title": i.get("title"), "pitch": i.get("pitch"),
              "for_whom": i.get("for_whom"), "why": i.get("why"),
              "built": (i.get("slug") in built_slugs) or (i.get("title") in built_slugs)}
             for i in d.get("ideas", [])]
    journal = [{"at": j.get("at"), "text": j.get("text")} for j in d.get("journal", [])]
    drives = last_drives.get("drives") or {}
    mood = (extra or {}).get("mood") or _mood_from(drives)
    wallet = (extra or {}).get("wallet") or _wallet_address(cfg)
    state = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fly": {
            "name": "The Fly Dev", "symbol": cfg.launchpad.genesis_symbol,
            "brain": cfg.brain.mode, "neurons": 138639 if cfg.brain.mode == "connectome" else cfg.brain.phantom_neurons,
            "mind": cfg.mind.model if cfg.mind.mode == "claude" else "offline",
            "chain": cfg.launchpad.chain_id, "factory": cfg.launchpad.factory,
            "armed": bool(cfg.launchpad.live), "wallet": wallet,
            "factory_name": "Pons V2 launch factory (contract)",
            "repo": REPO_URL, "branch": branch, "site": cfg.launchpad.website, "x": cfg.launchpad.twitter,
        },
        "now": {
            "at": last_drives.get("at"), "mood": mood,
            "action": last_drives.get("action"), "drives": last_drives.get("drives") or {},
            "probs": last_drives.get("probs") or {}, "brain": last_drives.get("brain") or {},
        },
        "counts": {"pages": len(pages), "memes": len(memes), "coins": len(coins),
                   "live_coins": sum(1 for c in coins if c["live"]), "builds": len(builds),
                   "searches": len(searches)},
        "pages": pages[::-1][:60],
        "searches": searches[::-1][:40],
        "learnings": learnings[::-1][:20],
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
    if not (site / "favicon.png").is_file():
        try:
            from .brand import render_favicons

            render_favicons(site)
        except Exception:
            pass
    state = build_state(cfg, mem, extra)
    _prune_shots(site / "browsing" / "shots", {p["shot"] for p in state["pages"] if p.get("shot")})
    out = site / "data" / "state.json"
    out.write_text(json.dumps(state, indent=1, default=str), encoding="utf-8")
    return out


def _prune_shots(shots_dir: Path, keep: set[str]) -> None:
    """Keep only screenshots still referenced by the published pages."""
    if not shots_dir.is_dir():
        return
    keep_names = {Path(k).name for k in keep}
    for f in shots_dir.glob("*.jpg"):
        if f.name not in keep_names:
            f.unlink(missing_ok=True)


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
