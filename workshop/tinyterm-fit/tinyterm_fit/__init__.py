"""tinyterm-fit: measure and lint terminal UI output for small screens."""

from .width import (
    ANSI_RE,
    char_width,
    display_width,
    fit_line,
    has_open_sgr,
    pad,
    strip_ansi,
    tokens,
    truncate,
)
from .check import PRESETS, Issue, check_text

__all__ = [
    "ANSI_RE",
    "char_width",
    "display_width",
    "fit_line",
    "has_open_sgr",
    "pad",
    "strip_ansi",
    "tokens",
    "truncate",
    "PRESETS",
    "Issue",
    "check_text",
]
__version__ = "0.1.0"
