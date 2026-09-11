"""The workshop: where the fly turns an idea into files, then checks them.

Generated code is executed locally (byte-compilation and the project's own
tests). Run the fly inside a container or VM if that worries you; it should.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .mind import TechIdea

SLUG_RE = re.compile(r"[^a-z0-9-]+")
TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".json", ".yaml", ".yml",
    ".js", ".mjs", ".ts", ".html", ".css", ".sh", ".csv", ".rs", ".go", ".c", ".h", "",
}


@dataclass
class BuildResult:
    slug: str
    path: Path
    ok: bool
    log: str
    files: list[str] = field(default_factory=list)


def safe_slug(raw: str) -> str:
    slug = SLUG_RE.sub("-", raw.lower()).strip("-")[:40]
    return slug or "untitled"


def _safe_relpath(root: Path, rel: str) -> Path | None:
    rel = rel.replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        return None
    if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
        return None
    return target


class Workshop:
    def __init__(self, workshop_dir: Path, test_timeout_sec: int = 180):
        self.dir = workshop_dir
        self.test_timeout_sec = test_timeout_sec

    def build(self, idea: TechIdea, mind=None, repair_rounds: int = 2, log_fn=None) -> BuildResult:
        """Write the project, check it, and let the mind repair failures."""
        slug = safe_slug(idea.slug)
        project = self.dir / slug
        n = 2
        while project.exists():
            project = self.dir / f"{slug}-{n}"
            n += 1
        project.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        log: list[str] = []
        files = {f.path: f for f in idea.files}
        for f in idea.files:
            target = _safe_relpath(project, f.path)
            if target is None:
                log.append(f"skipped unsafe path: {f.path}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content, encoding="utf-8")
            written.append(str(target.relative_to(project)))
        result = self._check(project, written, idea, log)
        rounds = 0
        while not result.ok and mind is not None and rounds < repair_rounds:
            rounds += 1
            if log_fn:
                log_fn(f"tests failed; the fly is fixing {idea.title} (round {rounds})")
            try:
                fix = mind.fix_project(idea, list(files.values()), result.log)
            except Exception as exc:
                log.append(f"repair round {rounds} failed: {exc}")
                break
            if not fix.files:
                break
            log.append(f"repair round {rounds}: {fix.diagnosis}")
            for f in fix.files:
                target = _safe_relpath(project, f.path)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f.content, encoding="utf-8")
                files[f.path] = f
                rel = str(target.relative_to(project))
                if rel not in written:
                    written.append(rel)
            result = self._check(project, written, idea, log)
        return result

    def _check(self, project: Path, written: list[str], idea: TechIdea, log: list[str]) -> BuildResult:
        log = list(log)
        if "README.md" not in written:
            (project / "README.md").write_text(
                f"# {idea.title}\n\n{idea.pitch}\n\nFor: {idea.for_whom}\n\nRun: `{idea.run_hint}`\n",
                encoding="utf-8",
            )
            written.append("README.md")
        (project / "FLY_NOTES.md").write_text(
            f"# Why the fly built this\n\n{idea.why_needed}\n\nPitch: {idea.pitch}\n",
            encoding="utf-8",
        )
        for stale in project.rglob("__pycache__"):
            shutil.rmtree(stale, ignore_errors=True)

        ok = True
        py_files = [project / w for w in written if w.endswith(".py")]
        if py_files:
            res = self._run([sys.executable, "-m", "py_compile", *map(str, py_files)], project)
            log.append(res)
            ok = ok and res.startswith("exit 0")
        tests = [w for w in written if Path(w).name.startswith("test_") and w.endswith(".py")]
        if ok and tests:
            res = self._run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], project)
            log.append(res)
            ok = ok and res.startswith("exit 0")
        js_tests = [w for w in written if w.endswith(".test.js") or w.endswith(".test.mjs")]
        if ok and js_tests:
            res = self._run(["node", "--test"], project)
            log.append(res)
            ok = ok and res.startswith("exit 0")

        return BuildResult(slug=project.name, path=project, ok=ok, log="\n".join(log), files=written)

    def _run(self, cmd: list[str], cwd: Path) -> str:
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(cwd),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C.UTF-8",
        }
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                timeout=self.test_timeout_sec,
            )
        except FileNotFoundError:
            return f"exit 127: {cmd[0]} not found"
        except subprocess.TimeoutExpired:
            return f"exit 124: timed out after {self.test_timeout_sec}s: {' '.join(cmd)}"
        out = (proc.stdout + proc.stderr).strip()[-4000:]
        return f"exit {proc.returncode}: {' '.join(cmd)}\n{out}"
