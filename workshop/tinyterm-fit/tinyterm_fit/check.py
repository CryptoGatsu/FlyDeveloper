"""Lint captured terminal output against a small-screen budget."""

from collections import namedtuple

from .width import display_width, has_open_sgr, strip_ansi

Issue = namedtuple("Issue", "line col kind message")

# name -> (cols, rows)
PRESETS = {
    "classic": (80, 24),
    "pocket": (64, 20),
    "phone": (38, 16),
    "fly": (40, 12),
}


def check_text(text, cols=80, rows=None):
    """Return a list of Issue tuples for a captured frame.

    cols: column budget (required)
    rows: row budget, or None/0 to skip the height check
    """
    issues = []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    for n, line in enumerate(lines, 1):
        if "\t" in line:
            col = display_width(line.split("\t", 1)[0]) + 1
            issues.append(
                Issue(n, col, "tab", "literal tab: width depends on the terminal, use spaces")
            )
        w = display_width(line)
        if w > cols:
            issues.append(
                Issue(
                    n,
                    cols + 1,
                    "overflow",
                    "line is %d cells wide, %d over the %d-column budget" % (w, w - cols, cols),
                )
            )
        if has_open_sgr(line):
            issues.append(
                Issue(
                    n,
                    max(1, len(strip_ansi(line))),
                    "color-leak",
                    "line ends with an unclosed SGR sequence (add \\x1b[0m)",
                )
            )

    if rows and len(lines) > rows:
        issues.append(
            Issue(
                rows + 1,
                1,
                "rows",
                "%d lines, %d past the %d-row screen" % (len(lines), len(lines) - rows, rows),
            )
        )
    return issues
