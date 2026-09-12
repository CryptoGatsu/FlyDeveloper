"""CLI: python -m tinyterm_fit [--preset pocket] [--cols N] [--rows N] [FILE...]"""

import argparse
import sys

from .check import PRESETS, check_text


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="tinyterm-fit",
        description="Check captured terminal UI output against a small-screen budget.",
    )
    p.add_argument("files", nargs="*", help="files with captured output (default: stdin)")
    p.add_argument("--preset", choices=sorted(PRESETS), default="classic")
    p.add_argument("--cols", type=int, default=None, help="override preset columns")
    p.add_argument("--rows", type=int, default=None, help="override preset rows (0 = no limit)")
    p.add_argument("-q", "--quiet", action="store_true", help="no output, just exit status")
    args = p.parse_args(argv)

    cols, rows = PRESETS[args.preset]
    if args.cols is not None:
        cols = args.cols
    if args.rows is not None:
        rows = args.rows

    sources = []
    if args.files:
        for name in args.files:
            try:
                with open(name, encoding="utf-8", errors="replace") as fh:
                    sources.append((name, fh.read()))
            except OSError as exc:
                print("%s: cannot read: %s" % (name, exc), file=sys.stderr)
                return 2
    else:
        sources.append(("<stdin>", sys.stdin.read()))

    total = 0
    for name, text in sources:
        for iss in check_text(text, cols=cols, rows=rows):
            total += 1
            if not args.quiet:
                print("%s:%d:%d: %s: %s" % (name, iss.line, iss.col, iss.kind, iss.message))
    if not args.quiet:
        print("%d issue(s) at %dx%d (%s)" % (total, cols, rows, args.preset))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
