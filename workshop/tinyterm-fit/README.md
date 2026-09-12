# tinyterm-fit

*Does your terminal UI fit on a tiny screen? Measure before you crash into it.*

A fruit fly learns the size of a gap by flying into it. You have a better option:
measure the gap first.

`tinyterm-fit` is a tiny, dependency-free (stdlib only) Python package that:

* computes the **true display width** of a string — ANSI escapes stripped,
  CJK/fullwidth/emoji counted as 2 cells, combining marks as 0;
* **truncates and pads** strings to a cell budget *without* chopping an escape
  sequence in half;
* **lints** captured TUI output against a small-screen budget.

## Why

Terminal UI frameworks give you lovely boxes at 120 columns. Then somebody runs
your dashboard in a tmux split, or on a 7-inch pocket laptop in a server rack,
and the borders tear, the status bar wraps, and a stray `\x1b[31m` escapes into
their shell prompt and dyes it red forever.

`len(s)` will not warn you. It counts escape bytes and undercounts 漢字 and 🍌.

## Install

Nothing to install. Copy the `tinyterm_fit/` directory, or run from this folder.

## CLI

```sh
# capture your app's frame and check it
my-tui --render-once > frame.txt
python -m tinyterm_fit --preset pocket frame.txt

# or just pipe
my-tui --render-once | python -m tinyterm_fit --cols 64 --rows 20
```

Output looks like:

```
frame.txt:3:65: overflow: line is 71 cells wide, 7 over the 64-column budget
frame.txt:9:40: color-leak: line ends with an unclosed SGR sequence (add \x1b[0m)
2 issue(s) at 64x20 (pocket)
```

Exit status is `1` when issues are found, so it drops straight into CI or a
pre-commit hook next to your golden-frame snapshots.

### Presets

| preset    | size  | who lives there |
|-----------|-------|-----------------|
| `classic` | 80x24 | the default everyone forgot to test |
| `pocket`  | 64x20 | 7-inch field laptop, half a tmux window |
| `phone`   | 38x16 | SSH from a phone on the train |
| `fly`     | 40x12 | very small screen, very short life |

## Library

```python
from tinyterm_fit import display_width, truncate, pad, fit_line, check_text

display_width("\x1b[1mbanana\x1b[0m")   # 6, not 14
display_width("日本語")                 # 6
truncate("\x1b[31mrotting fruit\x1b[0m", 8)  # keeps colour, appends reset
fit_line("status", 10)                  # 'status    '
for issue in check_text(frame, cols=64, rows=20):
    print(issue.kind, issue.message)
```

## Checks

* `overflow` — line wider than the column budget
* `rows` — frame taller than the row budget
* `tab` — literal tab, whose width depends on the terminal's mood
* `color-leak` — SGR opened and never reset before end of line

## Tests

```sh
python -m pytest -q
```

MIT-ish: do whatever you like, be kind to flies.
