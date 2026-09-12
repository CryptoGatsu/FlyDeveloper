import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinyterm_fit import (  # noqa: E402
    check_text,
    display_width,
    fit_line,
    has_open_sgr,
    pad,
    strip_ansi,
    truncate,
)
from tinyterm_fit.__main__ import main  # noqa: E402

RED = "\x1b[31m"
RESET = "\x1b[0m"


def test_plain_width():
    assert display_width("banana") == 6
    assert display_width("") == 0


def test_ansi_does_not_count():
    s = RED + "banana" + RESET
    assert len(s) > 6
    assert display_width(s) == 6
    assert strip_ansi(s) == "banana"


def test_osc_sequence_stripped():
    s = "\x1b]0;window title\x07ok"
    assert display_width(s) == 2


def test_wide_and_zero_width():
    assert display_width("日本語") == 6  # CJK, 2 cells each
    assert display_width("é") == 1  # e + combining acute
    assert display_width("\U0001f34c") == 2  # banana emoji


def test_truncate_plain():
    assert truncate("rotting fruit", 8) == "rotting…"
    assert truncate("short", 40) == "short"
    assert truncate("anything", 0) == ""


def test_truncate_keeps_escapes_and_resets():
    out = truncate(RED + "rotting fruit" + RESET, 8)
    assert out.startswith(RED)
    assert out.endswith(RESET)
    assert display_width(out) <= 8
    assert not has_open_sgr(out)


def test_truncate_never_splits_wide_char():
    out = truncate("日本語日", 5)
    assert display_width(out) <= 5


def test_pad_and_fit_line():
    assert pad("ab", 5) == "ab   "
    assert pad("ab", 5, align="right") == "   ab"
    assert pad("ab", 6, align="center") == "  ab  "
    assert display_width(fit_line(RED + "status bar here" + RESET, 10)) == 10
    assert display_width(fit_line("hi", 10)) == 10


def test_has_open_sgr():
    assert has_open_sgr(RED + "oops")
    assert not has_open_sgr(RED + "fine" + RESET)
    assert not has_open_sgr("no colour at all")


def test_check_overflow_and_rows():
    frame = "\n".join(["x" * 10, "y" * 3, "z" * 3])
    issues = check_text(frame, cols=5, rows=2)
    kinds = [i.kind for i in issues]
    assert "overflow" in kinds
    assert "rows" in kinds
    over = [i for i in issues if i.kind == "overflow"][0]
    assert over.line == 1
    assert "5 over" in over.message


def test_check_clean_frame():
    frame = "box\n" + RED + "line" + RESET + "\n"
    assert check_text(frame, cols=20, rows=10) == []


def test_check_tab_and_leak():
    issues = check_text("a\tb\n" + RED + "leaky\n", cols=40, rows=None)
    kinds = sorted(i.kind for i in issues)
    assert kinds == ["color-leak", "tab"]


def test_cli_clean(tmp_path, capsys):
    f = tmp_path / "frame.txt"
    f.write_text("tiny\nframe\n", encoding="utf-8")
    assert main(["--preset", "fly", str(f)]) == 0
    assert "0 issue(s)" in capsys.readouterr().out


def test_cli_reports_and_exits_nonzero(tmp_path, capsys):
    f = tmp_path / "wide.txt"
    f.write_text("-" * 100 + "\n", encoding="utf-8")
    assert main(["--cols", "40", "--rows", "0", str(f)]) == 1
    out = capsys.readouterr().out
    assert "overflow" in out
    assert "wide.txt:1:41" in out


def test_cli_quiet(tmp_path, capsys):
    f = tmp_path / "wide.txt"
    f.write_text("-" * 100 + "\n", encoding="utf-8")
    assert main(["--cols", "40", "-q", str(f)]) == 1
    assert capsys.readouterr().out == ""
