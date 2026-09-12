"""Display-width helpers for terminal strings. Standard library only."""

import re
import unicodedata

# CSI sequences, OSC sequences (BEL or ST terminated), and simple two-byte escapes.
ANSI_RE = re.compile(
    r"\x1b\[[0-9;:?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)

SGR_RE = re.compile(r"\x1b\[([0-9;:]*)m")

# Emoji blocks that older Python unicodedata tables call 'Neutral' but every
# modern terminal renders double width.
_EXTRA_WIDE = (
    (0x1F300, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F900, 0x1F9FF),
    (0x1FA70, 0x1FAFF),
)


def char_width(ch):
    """Cells occupied by a single character: 0, 1 or 2."""
    cp = ord(ch)
    if cp < 32 or 0x7F <= cp < 0xA0:
        return 0  # control characters occupy no cells (tabs are flagged elsewhere)
    if unicodedata.combining(ch):
        return 0
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    for lo, hi in _EXTRA_WIDE:
        if lo <= cp <= hi:
            return 2
    return 1


def strip_ansi(s):
    """Remove escape sequences, leaving printable text."""
    return ANSI_RE.sub("", s)


def tokens(s):
    """Yield ('ansi', sequence) and ('char', character) pairs in order."""
    pos = 0
    for m in ANSI_RE.finditer(s):
        for ch in s[pos:m.start()]:
            yield ("char", ch)
        yield ("ansi", m.group(0))
        pos = m.end()
    for ch in s[pos:]:
        yield ("char", ch)


def display_width(s):
    """Number of terminal cells `s` will occupy."""
    return sum(char_width(c) for c in strip_ansi(s))


def has_open_sgr(s):
    """True if the string turns styling on and never resets it."""
    open_style = False
    for m in SGR_RE.finditer(s):
        params = m.group(1)
        if params in ("", "0", "00") or params.split(";")[-1] in ("0", "00"):
            open_style = False
        else:
            open_style = True
    return open_style


def truncate(s, width, ellipsis="…"):
    """Cut `s` to `width` cells, keeping escape sequences intact.

    If anything is cut, `ellipsis` is appended and styling is reset so colour
    does not leak into the rest of the line.
    """
    if width <= 0:
        return ""
    if display_width(s) <= width:
        return s
    limit = max(0, width - display_width(ellipsis))
    out = []
    used = 0
    styled = False
    for kind, tok in tokens(s):
        if kind == "ansi":
            out.append(tok)
            if SGR_RE.fullmatch(tok):
                styled = True
            continue
        w = char_width(tok)
        if used + w > limit:
            break
        out.append(tok)
        used += w
    out.append(ellipsis)
    if styled:
        out.append("\x1b[0m")
    return "".join(out)


def pad(s, width, fill=" ", align="left"):
    """Pad `s` to `width` cells. Never truncates; see `fit_line`."""
    missing = width - display_width(s)
    if missing <= 0:
        return s
    if align == "right":
        return fill * missing + s
    if align == "center":
        left = missing // 2
        return fill * left + s + fill * (missing - left)
    return s + fill * missing


def fit_line(s, width, align="left", ellipsis="…"):
    """Truncate *and* pad so the result is exactly `width` cells."""
    return pad(truncate(s, width, ellipsis), width, align=align)
