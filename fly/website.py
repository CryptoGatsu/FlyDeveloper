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
            "mind": "claude-opus-5", "chain": 4663, "factory": "0x7eD5...", "armed": True,
            "wallet": "0x68e8...", "repo": "https://github.com/CryptoGatsu/FlyDeveloper"},
    "now": {"at": "2026-09-11T18:33:53+00:00", "mood": "scheming", "action": "launch",
            "drives": {"curiosity": 0.73, "craft": 0.82, "humor": 0.28, "appetite": 0.65, "boldness": 0.56, "fatigue": 0.15},
            "probs": {"browse": 0.31, "build": 0.39, "meme": 0.08, "launch": 0.15, "rest": 0.06},
            "brain": {"sugar": "sugar: 1486 spikes, 324 active ...", "walk": "walk: 51 spikes, 28 active ..."}},
    "counts": {"pages": 12, "memes": 4, "coins": 1, "live_coins": 1, "builds": 2},
    "pages": [{"at": "...", "url": "https://...", "title": "...", "gist": "...", "need": "...", "interesting": True, "followups": ["..."]}],
    "memes": [{"at": "...", "top": "...", "bottom": "...", "alt": "...", "mood": "smug", "src": "memes/fly-2026....png"}],
    "coins": [{"at": "...", "name": "The Fly Dev", "symbol": "FLYDEV", "description": "...", "live": True, "status": "confirmed",
               "tx": "0x...", "token": "0x...", "curve": "0x...", "logo": "https://...", "meme": "memes/fly-....png",
               "genesis": True, "buyback": False, "explorer_tx": "https://robinhoodchain.blockscout.com/tx/0x...",
               "explorer_token": "https://robinhoodchain.blockscout.com/token/0x..."}],
    "builds": [{"at": "...", "slug": "ripeness-clock", "title": "Ripeness Clock", "ok": True, "files": ["README.md"], "repo_path": "workshop/ripeness-clock"}],
    "ideas": [{"at": "...", "title": "...", "pitch": "...", "for_whom": "both", "why": "..."}],
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
- Every page loads /style.css and /app.js. app.js reads the current route from document.body.dataset.route, fetches "/data/state.json" (add a cache-busting query, no-store), renders that route's content, and re-fetches every 30 seconds.
- Always dark. Set html color-scheme: dark and a dark background; no light theme.
- Responsive down to 400px wide. No horizontal scrolling.
- Escape all text from state.json before inserting it into HTML.
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
    for child in site_dir.iterdir():
        if child.name in ("data", "memes", "brand", "CNAME"):
            continue
        if child.is_dir():
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
        target.write_text(f.content, encoding="utf-8")
        written.append(rel)
    return written


def load_site_files(site_dir: Path) -> list[ProjectFile]:
    """Read the current site's pages/assets back as ProjectFiles."""
    out: list[ProjectFile] = []
    for path in sorted(site_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(site_dir).as_posix()
        if rel.startswith(("data/", "brand/", "__qa/")) or rel == "CNAME":
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


def build_website(mind, site_dir: Path, context: str = "", log=print, visual_qa: bool = True, refine: bool = False) -> WebsiteResult:
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
            log("the fly is polishing its existing site")
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
