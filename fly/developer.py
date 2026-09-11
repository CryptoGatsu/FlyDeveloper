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

from .mind import ProjectFile, TechIdea

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

    # -- existing projects -----------------------------------------------------
    def load(self, slug: str) -> list[ProjectFile]:
        project = self.dir / slug
        out: list[ProjectFile] = []
        if not project.is_dir():
            return out
        for path in sorted(project.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or ".pytest_cache" in path.parts:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES or path.name == "FLY_NOTES.md":
                continue
            try:
                out.append(ProjectFile(path=path.relative_to(project).as_posix(), content=path.read_text(encoding="utf-8")))
            except UnicodeDecodeError:
                continue
        return out

    def repair(self, slug: str, title: str, mind, repair_rounds: int = 2, log_fn=None) -> BuildResult:
        """Re-check an existing project and let the mind fix what fails."""
        project = self.dir / slug
        files = self.load(slug)
        idea = TechIdea(slug=slug, title=title, pitch="", for_whom="both", why_needed="", language="python",
                        run_hint="", files=files)
        written = [f.path for f in files]
        result = self._check(project, written, idea, [], write_notes=False)
        return self._repair_loop(project, idea, {f.path: f for f in files}, written, result, mind, repair_rounds, log_fn)

    def improve(self, slug: str, title: str, pitch: str, mind, context: str = "", log_fn=None) -> tuple[BuildResult, str]:
        """Ask the mind for one improvement; keep it only if checks still pass."""
        project = self.dir / slug
        before = self.load(slug)
        if not before:
            return BuildResult(slug=slug, path=project, ok=False, log="project missing"), ""
        fix = mind.improve_project(title, pitch, before, context)
        if not fix.files:
            return BuildResult(slug=slug, path=project, ok=True, log="no change", files=[f.path for f in before]), ""
        files = {f.path: f for f in before}
        written = list(files)
        for f in fix.files:
            target = _safe_relpath(project, f.path)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.content, encoding="utf-8")
            files[f.path] = f
            if f.path not in written:
                written.append(f.path)
        idea = TechIdea(slug=slug, title=title, pitch=pitch, for_whom="both", why_needed="", language="python",
                        run_hint="", files=list(files.values()))
        result = self._check(project, written, idea, [f"improvement: {fix.diagnosis}"], write_notes=False)
        result = self._repair_loop(project, idea, files, written, result, mind, 1, log_fn)
        if not result.ok:                                   # roll back to the working version
            for f in before:
                (project / f.path).write_text(f.content, encoding="utf-8")
            for f in fix.files:
                if f.path not in {b.path for b in before}:
                    (project / f.path).unlink(missing_ok=True)
            result.log += "\nimprovement reverted: checks failed"
            result.ok = True
            return result, ""
        return result, fix.diagnosis

    def _repair_loop(self, project, idea, files, written, result, mind, repair_rounds, log_fn):
        log: list[str] = []
        rounds = 0
        while not result.ok and mind is not None and rounds < repair_rounds:
            rounds += 1
            if log_fn:
                log_fn(f"tests failed; the fly is fixing {idea.title} (round {rounds})")
            try:
                fix = mind.fix_project(idea, list(files.values()), result.log)
            except Exception as exc:
                result.log += f"\nrepair round {rounds} failed: {exc}"
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
            result = self._check(project, written, idea, log, write_notes=False)
        return result

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
        return self._repair_loop(project, idea, files, written, result, mind, repair_rounds, log_fn)

    def _check(self, project: Path, written: list[str], idea: TechIdea, log: list[str], write_notes: bool = True) -> BuildResult:
        log = list(log)
        if "README.md" not in written:
            (project / "README.md").write_text(
                f"# {idea.title}\n\n{idea.pitch}\n\nFor: {idea.for_whom}\n\nRun: `{idea.run_hint}`\n",
                encoding="utf-8",
            )
            written.append("README.md")
        if write_notes:
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
