import subprocess
import sys
from pathlib import Path

from fly.health import Health
from fly.mind import ProjectFile, ProjectFix
from fly import selfrepair


class PatchMind:
    def __init__(self, good: bool):
        self.good = good
    def fix_project(self, idea, files, log):
        target = next(f for f in files if f.path.endswith("broken.py"))
        content = "def go():\n    return 1\n" if self.good else "def go():\n    return 2\n"
        return ProjectFix(diagnosis="return 1 instead of raising", files=[ProjectFile(path=target.path, content=content)])


def _repo(tmp_path):
    root = tmp_path / "repo"
    (root / "fly").mkdir(parents=True); (root / "tests").mkdir()
    (root / "fly" / "__init__.py").write_text("")
    (root / "fly" / "broken.py").write_text("def go():\n    raise RuntimeError('bad')\n")
    (root / "tests" / "test_go.py").write_text(
        "import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))\n"
        "from fly.broken import go\n\ndef test_go():\n    assert go() == 1\n")
    return root


def _crash(root):
    import importlib.util
    spec = importlib.util.spec_from_file_location("scratch_broken", root / "fly" / "broken.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    try:
        mod.go()
    except RuntimeError as exc:
        return exc


def test_proposal_is_written_and_live_code_untouched(tmp_path):
    root = _repo(tmp_path)
    h = Health(root, log=lambda m: None)
    out = selfrepair.propose(root, PatchMind(good=True), h, _crash(root), log=lambda m: None)
    assert out is not None and (out / "patch.diff").is_file()
    assert "raise RuntimeError" in (root / "fly" / "broken.py").read_text()        # never self-applied
    props = selfrepair.list_proposals(root)
    assert props and props[0]["tests_passed"] is True
    applied = selfrepair.apply_proposal(root, props[0]["stamp"])
    assert applied == ["fly/broken.py"] and "return 1" in (root / "fly" / "broken.py").read_text()


def test_failing_patch_is_marked_and_daily_limit_holds(tmp_path):
    root = _repo(tmp_path)
    h = Health(root, log=lambda m: None)
    out = selfrepair.propose(root, PatchMind(good=False), h, _crash(root), log=lambda m: None)
    assert out is not None and selfrepair.list_proposals(root)[-1]["tests_passed"] is False
    selfrepair.propose(root, PatchMind(good=False), h, _crash(root), log=lambda m: None)
    assert selfrepair.propose(root, PatchMind(good=True), h, _crash(root), log=lambda m: None) is None   # 2 per day
