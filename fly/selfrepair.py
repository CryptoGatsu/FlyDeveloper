"""When the fly's own code crashes, the fly drafts a fix for a human to apply.

It never edits the running code. It copies the repository to a scratch
directory, applies the mind's patch there, runs the test-suite there, and
writes the result under data/self-repair/<stamp>/: the traceback, the
diagnosis, the patched files, a unified diff, and whether the tests passed.
`python fly.py repairs` lists proposals; `python fly.py repairs apply <stamp>`
applies one after you have looked at it. At most a couple of drafts a day.
"""

from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import sys
import time
import traceback as tb_mod
from pathlib import Path

from .mind import ProjectFile

MAX_PER_DAY = 2


def proposals_dir(root: Path) -> Path:
    return root / "data" / "self-repair"


def _files_from_traceback(root: Path, tb: str) -> list[Path]:
    out: list[Path] = []
    for line in tb.splitlines():
        line = line.strip()
        if line.startswith('File "') and "/fly/" in line:
            path = Path(line.split('"')[1])
            try:
                rel = path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            if rel.parts and rel.parts[0] == "fly" and path.is_file() and path not in out:
                out.append(path)
    return out


def propose(root: Path, mind, health, exc: BaseException, log=print) -> Path | None:
    """Draft a fix for the crash described by `exc`. Returns the proposal
    directory, or None if there is nothing to propose."""
    today = time.strftime("%Y-%m-%d")
    if health.state.proposal_day != today:
        health.state.proposal_day, health.state.proposals_today = today, 0
    if health.state.proposals_today >= MAX_PER_DAY:
        log("self-repair: drafted enough fixes for today; leaving it for a human")
        return None
    tb = "".join(tb_mod.format_exception(type(exc), exc, exc.__traceback__))
    files = _files_from_traceback(root, tb)
    if not files:
        return None                                         # not our code
    health.state.proposals_today += 1
    health.state.last_proposal = time.time()
    health.save()
    log(f"self-repair: the fly is drafting a fix for its crash in {', '.join(f.name for f in files)}")

    originals = {f: f.read_text(encoding="utf-8") for f in files}
    project_files = [ProjectFile(path=f.relative_to(root).as_posix(), content=c) for f, c in originals.items()]
    from .mind import TechIdea

    idea = TechIdea(slug="fly", title="The Fly Dev agent (my own code)", pitch="the code that runs me",
                    for_whom="flies", why_needed="it crashed", language="python", run_hint="python fly.py live",
                    files=project_files)
    try:
        fix = mind.fix_project(idea, project_files, tb)
    except Exception as e:
        health.incident("self-repair", f"could not draft a fix: {e}")
        return None
    patches = {pf.path.replace("\\", "/"): pf.content for pf in fix.files if pf.path.replace("\\", "/").startswith("fly/")}
    if not patches:
        health.incident("self-repair", "no usable patch drafted")
        return None

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = proposals_dir(root) / stamp
    out.mkdir(parents=True, exist_ok=True)
    (out / "traceback.txt").write_text(tb, encoding="utf-8")
    (out / "diagnosis.txt").write_text(fix.diagnosis + "\n", encoding="utf-8")
    diff_lines: list[str] = []
    for rel, content in patches.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text(content, encoding="utf-8")
        before = (root / rel).read_text(encoding="utf-8") if (root / rel).is_file() else ""
        diff_lines += difflib.unified_diff(before.splitlines(True), content.splitlines(True), f"a/{rel}", f"b/{rel}")
    (out / "patch.diff").write_text("".join(diff_lines), encoding="utf-8")

    # prove it in a scratch copy, never in the live tree
    passed, output = _test_in_scratch(root, patches)
    (out / "tests.txt").write_text(("PASSED\n" if passed else "FAILED\n") + output[-4000:], encoding="utf-8")
    (out / "proposal.json").write_text(json.dumps({
        "stamp": stamp, "files": list(patches), "tests_passed": passed, "diagnosis": fix.diagnosis,
        "error": tb.strip().splitlines()[-1][:200] if tb.strip() else "",
    }, indent=1), encoding="utf-8")
    health.incident("self-repair", f"crash: {tb.strip().splitlines()[-1][:160]}",
                    fixed=f"drafted a fix ({'tests pass' if passed else 'tests fail'}); review with: python fly.py repairs")
    log(f"self-repair: proposal saved to {out} ({'tests pass' if passed else 'tests FAIL'}); apply it with  python fly.py repairs apply {stamp}")
    return out


def _test_in_scratch(root: Path, patches: dict[str, str]) -> tuple[bool, str]:
    scratch = Path(root / "data" / "self-repair" / "_scratch")
    if scratch.exists():
        shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    for name in ("fly", "tests", "fly.py", "requirements-fly.txt"):
        src = root / name
        if src.is_dir():
            shutil.copytree(src, scratch / name, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        elif src.is_file():
            shutil.copy2(src, scratch / name)
    for rel, content in patches.items():
        (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
        (scratch / rel).write_text(content, encoding="utf-8")
    try:
        res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "tests", "-p", "no:cacheprovider"],
                             cwd=str(scratch), capture_output=True, text=True, timeout=900)
        return res.returncode == 0, res.stdout + res.stderr
    except subprocess.TimeoutExpired:
        return False, "tests timed out"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def list_proposals(root: Path) -> list[dict]:
    out = []
    base = proposals_dir(root)
    if not base.is_dir():
        return out
    for d in sorted(base.iterdir()):
        meta = d / "proposal.json"
        if meta.is_file():
            try:
                out.append(json.loads(meta.read_text(encoding="utf-8")))
            except ValueError:
                continue
    return out


def apply_proposal(root: Path, stamp: str) -> list[str]:
    """Copy a reviewed proposal's files into the live tree. Returns the paths."""
    d = proposals_dir(root) / stamp
    meta = json.loads((d / "proposal.json").read_text(encoding="utf-8"))
    applied = []
    for rel in meta.get("files", []):
        src = d / rel
        if src.is_file() and rel.startswith("fly/"):
            (root / rel).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            applied.append(rel)
    return applied
