"""The fly builds its own website.

The mind is given a brief (routes, the state.json schema, design rules) and
returns the site's files. They are validated (clean URLs, every route
present, one shared script that reads /data/state.json, JavaScript that
parses) before replacing `site/`. If the mind's attempt fails validation the
built-in template is used, so the public page never breaks.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .mind import ProjectFile

TEMPLATE_DIR = Path(__file__).resolve().parent / "site_template"

ROUTES: list[tuple[str, str]] = [
    ("", "Now"), ("browsing", "Browsing"), ("memes", "Memes"),
    ("coins", "Coins"), ("builds", "Builds"), ("journal", "Journal"),
]

STATE_EXAMPLE = {
    "generated_at": "2026-09-11T18:34:27Z",
    "fly": {"name": "The Fly Dev", "symbol": "FLYDEV", "brain": "connectome", "neurons": 138639,
            "mind": "claude-opus-5", "chain": 4663, "factory": "0x7eD5...", "factory_name": "Pons V2 launch factory (contract)",
            "armed": True, "wallet": "0x68e8...", "repo": "https://github.com/CryptoGatsu/FlyDeveloper",
            "branch": "main", "site": "https://flydev.tech", "x": "https://x.com/TheFlyDev_"},
    "now": {"at": "2026-09-11T18:33:53+00:00", "mood": "scheming", "action": "launch",
            "drives": {"curiosity": 0.73, "craft": 0.82, "humor": 0.28, "appetite": 0.65, "boldness": 0.56, "fatigue": 0.15},
            "probs": {"browse": 0.31, "build": 0.39, "meme": 0.08, "launch": 0.15, "rest": 0.06},
            "brain": {"sugar": "sugar: 1486 spikes, 324 active ...", "walk": "walk: 51 spikes, 28 active ..."}},
    "counts": {"pages": 12, "memes": 4, "coins": 1, "live_coins": 1, "builds": 2, "searches": 5, "posts": 7},
    "pages": [{"at": "...", "url": "https://...", "title": "...", "gist": "...", "need": "...", "interesting": True, "followups": ["..."], "shot": "browsing/shots/20260911-195100-ab12cd34.jpg"}],
    "searches": [{"at": "...", "query": "small tools people wish existed", "engine": "duckduckgo", "results": [{"title": "...", "url": "https://..."}]}],
    "learnings": [{"at": "...", "summary": "...", "ideas": ["..."]}],
    "posts": [{"at": "...", "kind": "hype", "text": "...", "url": "https://x.com/TheFlyDev_/status/1", "live": True, "media": "memes/fly-....png",
               "metrics": {"like_count": 12, "retweet_count": 3, "reply_count": 2, "impression_count": 900}, "score": 24.5, "why": "..."}],
    "playbook": {"at": "...", "what_works": ["..."], "what_flops": ["..."], "next_bets": ["..."]},
    "health": {"uptime_sec": 86400, "restarts": 3, "suspended": [], "incidents": [{"at": "...", "kind": "network", "detail": "no route", "fixed": "resumed"}], "proposals_today": 0},
    "memes": [{"at": "...", "top": "...", "bottom": "...", "alt": "...", "mood": "smug", "src": "memes/fly-2026....png"}],
    "coins": [{"at": "...", "name": "The Fly Dev", "symbol": "FLYDEV", "description": "...", "live": True, "status": "confirmed",
               "tx": "0x...", "token": "0x...", "curve": "0x...", "logo": "https://...", "meme": "memes/fly-....png",
               "genesis": True, "buyback": False, "explorer_tx": "https://robinhoodchain.blockscout.com/tx/0x...",
               "explorer_token": "https://robinhoodchain.blockscout.com/token/0x...",
               "pons": "https://www.ponsfamily.com/launchpad/0x..."}],
    "builds": [{"at": "...", "slug": "ripeness-clock", "title": "Ripeness Clock", "ok": True, "kind": "tool", "files": ["README.md"],
                "repo_path": "workshop/ripeness-clock", "url": "https://github.com/CryptoGatsu/FlyDeveloper/tree/main/workshop/ripeness-clock",
                "readme_url": "https://github.com/CryptoGatsu/FlyDeveloper/blob/main/workshop/ripeness-clock/README.md",
                "changes": [{"at": "...", "what": "handled infinite progress in stage()"}]}],
    "ideas": [{"at": "...", "slug": "ripeness-clock", "title": "...", "pitch": "...", "for_whom": "both", "why": "...", "built": True}],
    "journal": [{"at": "...", "text": "..."}],
    "drives_history": [{"at": "...", "action": "browse", "drives": {"curiosity": 0.7}}],
}


def website_brief() -> str:
    routes = ", ".join(f"/{r}" if r else "/" for r, _ in ROUTES)
    return f"""Design and write your own public website. It shows people what you are doing.

Hard requirements:
- Static files only: HTML, one shared /style.css, one shared /app.js. No frameworks, no CDN, no build step.
- Routes are folders with an index.html: {routes}. So return files "index.html", "browsing/index.html", "memes/index.html", "coins/index.html", "builds/index.html", "journal/index.html", plus "style.css" and "app.js".
- Clean URLs everywhere: links are "/", "/browsing", "/memes", ... Never link to a ".html" file and never use "#" fragment links. Use absolute paths ("/app.js", "/style.css", "/data/state.json", "/memes/<file>").
- Every page's <head> includes <link rel="icon" href="/favicon.png"> and <link rel="apple-touch-icon" href="/apple-touch-icon.png"> (the files exist; do not draw your own).
- Every page loads /style.css and /app.js. app.js reads the current route from document.body.dataset.route, fetches "/data/state.json" (add a cache-busting query, no-store), renders that route's content, and re-fetches every 30 seconds.
- Always dark. Set html color-scheme: dark and a dark background; no light theme.
- Responsive down to 400px wide. No horizontal scrolling.
- Escape all text from state.json before inserting it into HTML.
- There is also a route /ask ("ask the fly": a chat with you, five free questions then a $FLYDEV burn). Its page and script are provided by the house (do NOT write ask/index.html or ask.js); just link "ask" in the nav of every page, after journal.
- Labels: fly.factory is the Pons launch-factory CONTRACT (label it "factory contract"), fly.wallet is your wallet; fly.repo is the GitHub repository, fly.site is https://flydev.tech, fly.x is your X account. fly.branch is the git branch the site is published from.
- Links to builds use build.url (already the correct GitHub tree URL for the branch) and build.readme_url when present; never construct repo URLs yourself.
- Every page the fly reads has a screenshot (page.shot, a site-relative path like "browsing/shots/x.jpg", prefix with "/"; may be empty). Show it prominently in the page card, as an <img> with alt text, linked to the page, so visitors can see the fly really was there; the image is stamped with time and URL.
- "/" starts with the CONNECTOME: put <div id="flybrain"></div> as the first thing in the home page's main content and load <script src="/brain.js"></script> at the end of index.html (brain.js is provided by the house; do not write it). It draws the live spike raster of the fly's brain. Add one lead sentence under it saying these are real spikes from the connectome simulation that decides what the fly does.
- /browsing starts with the FLY CAM: put <div id="flycam"></div> as the first thing in the page's main content and load <script src="/cam.js"></script> at the end of browsing/index.html (cam.js is provided by the house; do not write it). It renders a live panel of what the fly is looking at right now.
- /browsing shows, IN THIS ORDER, newest first: FIRST the pages it read with their screenshots big and up top (state.pages: shot image, title, link, gist, need spotted, followups), THEN what it learned (state.learnings: summary + ideas), THEN the searches (state.searches: query, engine, result titles+urls). Visitors come to see what the fly is looking at right now, so the screenshots lead. Make it read like a fly's field notes, not a log dump.
- X posts: state.posts (kind, text, url, live, media, metrics like like_count/retweet_count/reply_count/impression_count, score) and state.playbook (what_works, what_flops, next_bets). Show the latest post on "/" and a "what I said on X" section on /journal with each post (link to url when live, show the meme when media is set, show metrics when present) and the playbook underneath as "what I've learned about posting".
- Ideas carry `built` (true when a build with that slug/title exists): the "ideas not yet built" list must only show ideas with built == false. Builds carry `changes` (list of {{at, what}}): show them as a short changelog on the build card ("maintained: ...").
- state.health = {{uptime_sec, restarts, suspended: [actions], incidents: [{{at, kind, detail, fixed}}], proposals_today}}. Show a small "vitals" line on "/" (uptime, restarts, anything suspended) and the last incidents with what I did about them on /journal under "things that went wrong and what I did". A fly that fixes itself should show its scars.
- Content per route: "/" = your current mood, drives as bars, last action, the brain readout, counts, the latest meme and coin with links to the full lists; /browsing = pages read with title, link, gist and "need spotted"; /memes = gallery of images (src is relative to the site root: prefix with "/"); /coins = every coin with name, $SYMBOL, genesis/live badges, description, explorer links; /builds = things built with links into the repo (fly.repo + "/tree/HEAD/" + repo_path) and the ideas; /journal = the journal lines.
- The site lives at https://flydev.tech; the source is at https://github.com/CryptoGatsu/FlyDeveloper (link it as "Source"); the fly's X account is https://x.com/TheFlyDev_ (link it as "X").
- A footer on every page saying coins are jokes with a ticker, no utility, no roadmap, no promises, nothing is financial advice; credit fly-brain (Shiu et al.) and Pons.
- Keep it under ~600 lines total. Plain, fast, yours: it should feel like a fly made it (a little buzz, a little insolence), not a corporate dashboard.

The state.json shape (example values):
{json.dumps(STATE_EXAMPLE, indent=1)}
"""


@dataclass
class WebsiteResult:
    ok: bool
    source: str                 # "mind" | "template"
    files: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    notes: str = ""


def template_files() -> list[ProjectFile]:
    shell = (TEMPLATE_DIR / "shell.html").read_text(encoding="utf-8")
    out = [
        ProjectFile(path="style.css", content=(TEMPLATE_DIR / "style.css").read_text(encoding="utf-8")),
        ProjectFile(path="app.js", content=(TEMPLATE_DIR / "app.js").read_text(encoding="utf-8")),
    ]
    for route, label in ROUTES:
        title = "The Fly Dev" if not route else f"{label} · The Fly Dev"
        html = shell.replace("{{ROUTE}}", route).replace("{{TITLE}}", title)
        out.append(ProjectFile(path=(f"{route}/index.html" if route else "index.html"), content=html))
    return out


_HREF_RE = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""", re.I)


def validate_site(files: list[ProjectFile]) -> list[str]:
    problems: list[str] = []
    by_path = {f.path.replace("\\", "/").lstrip("/"): f for f in files}
    for route, _ in ROUTES:
        p = f"{route}/index.html" if route else "index.html"
        if p not in by_path:
            problems.append(f"missing route page {p}")
    for req in ("app.js", "style.css"):
        if req not in by_path:
            problems.append(f"missing {req}")
    for path, f in by_path.items():
        if path.endswith(".html") or path.endswith(".css"):
            if "\\u00" in f.content or "\\u20" in f.content:
                problems.append(f"{path} contains a literal \\u escape sequence that will show as text")
        if path.endswith(".html"):
            if "/app.js" not in f.content or "/style.css" not in f.content:
                problems.append(f"{path} must load /app.js and /style.css")
            if 'data-route' not in f.content:
                problems.append(f"{path} must set data-route on <body>")
            for url in _HREF_RE.findall(f.content):
                if url.startswith("#") or url.lower().endswith(".html"):
                    problems.append(f"{path} links to '{url}' (no # or .html links)")
        if path == "app.js":
            if "state.json" not in f.content:
                problems.append("app.js must fetch /data/state.json")
            if ".html" in f.content.replace("index.html", "") and 'href="/' not in f.content:
                problems.append("app.js appears to build .html links")
            if re.search(r"""href=["']#""", f.content):
                problems.append("app.js builds # links")
    js = by_path.get("app.js")
    if js and not problems and shutil.which("node"):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as tmp:
            tmp.write(js.content)
        res = subprocess.run(["node", "--check", tmp.name], capture_output=True, text=True)
        Path(tmp.name).unlink(missing_ok=True)
        if res.returncode != 0:
            problems.append("app.js does not parse: " + (res.stderr or res.stdout).strip()[-300:])
    return problems


def install_site(site_dir: Path, files: list[ProjectFile]) -> list[str]:
    """Replace the site's pages/assets, keeping data/ and memes/ (and CNAME)."""
    site_dir.mkdir(parents=True, exist_ok=True)
    keep_dirs = ("data", "memes", "brand", "ask")
    keep_files = ("CNAME", "favicon.png", "favicon.ico", "apple-touch-icon.png", "robots.txt", "ask.js", "cam.js", "brain.js")
    for child in site_dir.iterdir():
        if child.name in keep_dirs or child.name in keep_files:
            continue
        if child.is_dir():
            if child.name == "browsing":            # keep the page screenshots
                for sub in child.iterdir():
                    if sub.name != "shots":
                        shutil.rmtree(sub) if sub.is_dir() else sub.unlink()
                continue
            shutil.rmtree(child)
        else:
            child.unlink()
    written = []
    for f in files:
        rel = f.path.replace("\\", "/").lstrip("/")
        target = (site_dir / rel).resolve()
        if site_dir.resolve() not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = ensure_house_panels(ensure_head_tags(f.content), rel) if rel.endswith(".html") else f.content
        target.write_text(content, encoding="utf-8")
        written.append(rel)
    (site_dir / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
    return written


HEAD_TAGS = (
    '<link rel="icon" href="/favicon.png">',
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
)


# House-provided live panels: the connectome raster on "/", the fly cam on
# /browsing. They are injected if the fly's page does not already mount them.
HOUSE_PANELS = {
    "index.html": ("flybrain", "/brain.js"),
    "browsing/index.html": ("flycam", "/cam.js"),
}


def ensure_house_panels(html: str, rel: str) -> str:
    spec = HOUSE_PANELS.get(rel)
    if not spec:
        return html
    div_id, script = spec
    out = html
    if f'id="{div_id}"' not in out and f"id='{div_id}'" not in out:
        m = re.search(r"<main\b[^>]*>", out)
        if m:
            out = out[: m.end()] + f'\n<div id="{div_id}"></div>' + out[m.end():]
        elif "<body" in out:
            m2 = re.search(r"<body\b[^>]*>", out)
            out = out[: m2.end()] + f'\n<div id="{div_id}"></div>' + out[m2.end():]
    if script not in out and "</body>" in out:
        out = out.replace("</body>", f'<script src="{script}"></script>\n</body>', 1)
    return out


def ensure_head_tags(html: str) -> str:
    """House rules every page gets regardless of who wrote it: favicon links."""
    missing = [t for t in HEAD_TAGS if t.split('href="')[1].split('"')[0] not in html]
    if not missing or "</head>" not in html:
        return html
    return html.replace("</head>", "\n".join(missing) + "\n</head>", 1)


def load_site_files(site_dir: Path) -> list[ProjectFile]:
    """Read the current site's pages/assets back as ProjectFiles."""
    out: list[ProjectFile] = []
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(site_dir).as_posix()
        if rel.startswith(("data/", "brand/", "__qa/", "browsing/shots/", "ask/")) or rel in ("CNAME", "ask.js", "cam.js", "brain.js"):
            continue
        if rel.startswith("memes/") and not rel.endswith(".html"):
            continue                                   # the /memes route page shares the images folder
        if path.suffix in (".html", ".css", ".js"):
            out.append(ProjectFile(path=rel, content=path.read_text(encoding="utf-8")))
    return out


OVERFLOW_HINT = ("content is cut off at the right edge of a 400px-wide phone screen (horizontal overflow). "
                 "Usual causes: a grid or flex child without min-width:0, a fixed-width column, long unbroken "
                 "strings, or an image/pre without max-width:100%. Give every grid/flex child min-width:0, "
                 "use overflow-wrap:anywhere on text, stack multi-column layouts below 480px, and keep "
                 "html/body overflow-x:hidden as a last resort")


def qa_loop(mind, files: list[ProjectFile], site_dir: Path, brief: str, log=print, max_rounds: int = 3):
    """Render, look, revise: up to `max_rounds` passes until phones fit."""
    import tempfile

    from .render import edge_overflow, find_chrome, screenshot_site, shrink

    notes = ""
    if not find_chrome():
        return files, notes
    with tempfile.TemporaryDirectory() as tmp:
        for round_no in range(1, max_rounds + 1):
            preview = Path(tmp) / f"site{round_no}"
            install_site(preview, files)
            _seed_preview_data(site_dir, preview)
            shots = screenshot_site(preview, Path(tmp) / f"shots{round_no}", routes=("", "coins", "builds"))
            if not shots:
                break
            seen = [f"{sh.stem}: {OVERFLOW_HINT}" for sh in shots if "phone" in sh.name and edge_overflow(sh) > 0.12]
            if round_no > 1 and not seen:
                break                                  # the revision fixed it
            log(f"the fly is looking at its site ({len(shots)} screenshots" + (f", overflow on {len(seen)}" if seen else "") + ")")
            small = [shrink(sh, 800, 1400) if "desktop" in sh.name else shrink(sh, 400, 1200) for sh in shots]
            revised = mind.revise_website(brief, files, seen, small)
            if validate_site(revised.files):
                log("the revision failed checks; keeping the previous version")
                break
            files, notes = revised.files, revised.notes or notes
    return files, notes


def build_website(mind, site_dir: Path, context: str = "", log=print, visual_qa: bool = True, refine: bool = False,
                  changes: list[str] | None = None) -> WebsiteResult:
    """Ask the mind for a site (or reload the current one with `refine`);
    validate; let it fix problems once; show it screenshots and let it
    revise until phones fit; fall back to the template if it still fails."""
    brief = website_brief()
    files: list[ProjectFile] = []
    notes = ""
    problems: list[str] = []
    source = "mind"
    try:
        if refine and site_exists(site_dir):
            files = load_site_files(site_dir)
            source = "refined"
            log("the fly is polishing its existing site")
            if changes:
                log("with changes: " + "; ".join(changes)[:200])
                result = mind.revise_website(brief, files, [f"CHANGE REQUEST: {c}" for c in changes], [])
                files, notes = result.files, result.notes
        else:
            result = mind.website(brief, context)
            files, notes = result.files, result.notes
        problems = validate_site(files)
        if problems:
            log("checks failed, the fly is fixing its site: " + "; ".join(problems[:3]))
            result = mind.revise_website(brief, files, problems, [])
            files, notes = result.files, result.notes or notes
            problems = validate_site(files)
    except Exception as exc:                       # refusal, timeout, bad JSON
        problems = [f"mind failed: {exc}"]

    if not problems and visual_qa:
        try:
            files, qa_notes = qa_loop(mind, files, site_dir, brief, log=log)
            notes = qa_notes or notes
        except Exception as exc:
            log(f"visual QA skipped: {exc}")

    if problems:
        if site_exists(site_dir):
            # a working site beats a template: keep what is live, just re-apply house rules
            log("the fly's attempt failed (" + "; ".join(problems[:2]) + "); keeping the current site")
            files, source = load_site_files(site_dir), "kept"
            problems = problems[:4]
        else:
            log("the fly's own site did not pass checks: " + "; ".join(problems[:4]))
            files, source = template_files(), "template"
    written = install_site(site_dir, files)
    return WebsiteResult(ok=True, source=source, files=written, problems=problems, notes=notes)


def _seed_preview_data(site_dir: Path, preview: Path) -> None:
    """Give the QA preview real content: the live state.json and memes if the
    site has them, otherwise the example state, so screenshots show pages as
    visitors will see them rather than the offline fallback."""
    src_data, src_memes = site_dir / "data" / "state.json", site_dir / "memes"
    (preview / "data").mkdir(parents=True, exist_ok=True)
    if src_data.is_file():
        shutil.copy2(src_data, preview / "data" / "state.json")
    else:
        (preview / "data" / "state.json").write_text(json.dumps(STATE_EXAMPLE), encoding="utf-8")
    if src_memes.is_dir():
        shutil.copytree(src_memes, preview / "memes", dirs_exist_ok=True)


def site_exists(site_dir: Path) -> bool:
    return (site_dir / "index.html").is_file() and (site_dir / "app.js").is_file()
