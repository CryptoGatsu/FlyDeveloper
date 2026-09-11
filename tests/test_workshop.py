from fly.developer import Workshop, safe_slug
from fly.mind import ProjectFile, TechIdea


def _idea(files):
    return TechIdea(slug="Thing One!", title="Thing", pitch="p", for_whom="both", why_needed="w",
                    language="python", run_hint="python x.py", files=files)


def test_unsafe_paths_are_skipped(tmp_path):
    ws = Workshop(tmp_path)
    res = ws.build(_idea([
        ProjectFile(path="../escape.py", content="print(1)"),
        ProjectFile(path="ok.py", content="x = 1\n"),
        ProjectFile(path="bin.exe", content="nope"),
    ]))
    assert res.files == ["ok.py", "README.md"]
    assert not (tmp_path / "escape.py").exists()
    assert "skipped unsafe path" in res.log
    assert res.ok


def test_failing_test_marks_build_not_ok(tmp_path):
    ws = Workshop(tmp_path)
    res = ws.build(_idea([
        ProjectFile(path="README.md", content="# x"),
        ProjectFile(path="test_bad.py", content="def test_bad():\n    assert False\n"),
    ]))
    assert res.ok is False


def test_slug_collision_gets_suffix(tmp_path):
    ws = Workshop(tmp_path)
    a = ws.build(_idea([ProjectFile(path="README.md", content="# a")]))
    b = ws.build(_idea([ProjectFile(path="README.md", content="# b")]))
    assert a.slug == "thing-one" and b.slug == "thing-one-2"
    assert safe_slug("!!!") == "untitled"


class FixingMind:
    calls = 0

    def fix_project(self, idea, files, log):
        from fly.mind import ProjectFix
        self.calls += 1
        assert "assert False" in "".join(f.content for f in files) or "AssertionError" in log
        return ProjectFix(diagnosis="the test asserted False", files=[ProjectFile(path="test_bad.py", content="def test_ok():\n    assert True\n")])


def test_repair_loop_fixes_failing_build(tmp_path):
    ws = Workshop(tmp_path)
    mind = FixingMind()
    res = ws.build(_idea([ProjectFile(path="README.md", content="# x"),
                          ProjectFile(path="test_bad.py", content="def test_bad():\n    assert False\n")]), mind=mind)
    assert res.ok is True and mind.calls == 1
    assert "repair round 1: the test asserted False" in res.log
