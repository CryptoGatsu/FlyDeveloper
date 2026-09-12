#!/usr/bin/env python3
"""license-drift: notice when an installed package changes its license.

Snapshot now, check later. Dependency-free.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone

RESTRICTIVE = {
    "BUSL-1.1",
    "SSPL-1.0",
    "Elastic-2.0",
    "FSL-1.1",
    "Commons-Clause",
    "Proprietary",
}

# order matters: narrow / alarming rules first
_RULES = [
    (r"\bUNLICENSE\b|PUBLIC DOMAIN|\bCC0", "Unlicense"),
    (r"\bBUSL|BUSINESS SOURCE", "BUSL-1.1"),
    (r"\bSSPL|SERVER SIDE PUBLIC", "SSPL-1.0"),
    (r"ELASTIC LICENSE|\bELV2\b|ELASTIC-2", "Elastic-2.0"),
    (r"FUNCTIONAL SOURCE|\bFSL-1", "FSL-1.1"),
    (r"COMMONS CLAUSE|COMMONS-CLAUSE", "Commons-Clause"),
    (r"PROPRIETARY|ALL RIGHTS RESERVED", "Proprietary"),
    (r"\bAGPL|AFFERO", "AGPL-3.0"),
    (r"\bLGPL|LESSER GENERAL PUBLIC", "LGPL"),
    (r"\bGPL|GNU GENERAL PUBLIC", "GPL"),
    (r"APACHE", "Apache-2.0"),
    (r"\bMIT\b", "MIT"),
    (r"\bISC\b", "ISC"),
    (r"\bMPL|MOZILLA PUBLIC", "MPL-2.0"),
    (r"BSD.?3|3.CLAUSE", "BSD-3-Clause"),
    (r"BSD.?2|2.CLAUSE", "BSD-2-Clause"),
    (r"\bBSD\b", "BSD"),
    # "Python-2.0" is the SPDX id for the PSF license; keep it here so an
    # expression atom like `MIT AND Python-2.0` is recognised.
    (r"\bPSF\b|PYTHON SOFTWARE FOUNDATION|\bPYTHON-2\b|\bPYTHON-2\.", "PSF-2.0"),
]

_EMPTY = {"", "UNKNOWN", "NONE", "NULL", "SEE LICENSE", "DUAL LICENSE"}

# SPDX-ish operators, always written back in upper case
_CONNECTOR = re.compile(r"\s+(AND|OR|WITH)\s+")
_MAX_ATOMS = 6


def _match_rule(upper_text):
    """Return the short tag for an uppercased blurb, or None if nothing matches."""
    for pattern, tag in _RULES:
        if re.search(pattern, upper_text):
            return tag
    return None


def _parse_expression(upper_text):
    """Split `MIT OR Apache-2.0` style expressions into (tags, connectors).

    Returns None unless every atom is a license we recognise — that guard keeps
    prose like "GNU GPL v2 or later" out of the expression path.
    """
    tokens = _CONNECTOR.split(upper_text)
    if len(tokens) < 3:
        return None
    atoms, connectors = tokens[0::2], tokens[1::2]
    if len(atoms) > _MAX_ATOMS:
        return None
    tags = []
    for atom in atoms:
        atom = atom.replace("(", " ").replace(")", " ").strip()
        if not atom:
            return None
        tag = _match_rule(atom)
        if tag is None:
            return None
        tags.append(tag)
    return tags, connectors


def _canonical_expression(tags, connectors):
    """Render a stable tag. Pure OR / pure AND get sorted so metadata
    reordering is not mistaken for drift; WITH and mixed forms keep order."""
    distinct = set(connectors)
    if distinct in ({"OR"}, {"AND"}):
        ordered = sorted(set(tags))
        if len(ordered) == 1:
            return ordered[0]
        return (" %s " % connectors[0]).join(ordered)
    parts = [tags[0]]
    for connector, tag in zip(connectors, tags[1:]):
        parts.extend([connector, tag])
    return " ".join(parts)


def normalize_license(raw):
    """Turn any license blurb into a short, comparable tag."""
    if not raw:
        return "UNKNOWN"
    cleaned = " ".join(str(raw).split())[:200]
    upper = cleaned.upper()
    if upper in _EMPTY:
        return "UNKNOWN"
    parsed = _parse_expression(upper)
    if parsed:
        return _canonical_expression(*parsed)
    tag = _match_rule(upper)
    if tag:
        return tag
    return cleaned if len(cleaned) <= 40 else "UNKNOWN"


def is_restrictive(tag):
    """Should this tag make CI stop?

    A plain restrictive tag does. In a compound expression, `OR` means you may
    pick a branch, so it only alarms when every option is restrictive; `AND` and
    `WITH` stack obligations, so any restrictive part alarms (this is how a
    quiet `Apache-2.0 WITH Commons-Clause` gets caught).
    """
    if not tag:
        return False
    if tag in RESTRICTIVE:
        return True
    tokens = _CONNECTOR.split(tag)
    if len(tokens) < 3:
        return False
    atoms = [t.strip() for t in tokens[0::2]]
    connectors = set(tokens[1::2])
    if connectors == {"OR"}:
        return all(atom in RESTRICTIVE for atom in atoms)
    return any(atom in RESTRICTIVE for atom in atoms)


def extract_license(expression=None, license_field=None, classifiers=()):
    """Pick the most trustworthy license signal available."""
    if expression:
        tag = normalize_license(expression)
        if tag != "UNKNOWN":
            return tag
    for classifier in classifiers or ():
        if not str(classifier).startswith("License ::"):
            continue
        leaf = str(classifier).split("::")[-1].strip()
        if leaf in ("License", "OSI Approved"):
            continue
        tag = normalize_license(leaf)
        if tag != "UNKNOWN":
            return tag
    return normalize_license(license_field)


def read_installed():
    """Map distribution name -> {version, license} for this environment."""
    from importlib import metadata

    found = {}
    for dist in metadata.distributions():
        try:
            md = dist.metadata
            name = (md.get("Name") or "").strip()
            if not name:
                continue
            classifiers = md.get_all("Classifier") or []
            lic = extract_license(
                md.get("License-Expression"), md.get("License"), classifiers
            )
            found[name.lower()] = {
                "version": (dist.version or "?").strip(),
                "license": lic,
            }
        except Exception:  # a broken .dist-info should not stop the check
            continue
    return found


def build_snapshot(packages):
    return {
        "tool": "license-drift",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "packages": packages,
    }


def load_snapshot(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("packages"), dict):
        return data["packages"]
    if isinstance(data, dict):
        return data
    raise ValueError("snapshot is not an object")


def save_snapshot(path, packages):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build_snapshot(packages), fh, indent=2, sort_keys=True)
        fh.write("\n")


def diff(old, new):
    """Compare two package maps; return a sorted list of change records."""
    changes = []
    for name in sorted(set(old) | set(new)):
        before, after = old.get(name), new.get(name)
        if before is None:
            lic = after.get("license", "UNKNOWN")
            changes.append({
                "kind": "added", "name": "%s@%s" % (name, after.get("version", "?")),
                "old": None, "new": lic, "alarm": is_restrictive(lic)})
        elif after is None:
            changes.append({
                "kind": "removed", "name": "%s@%s" % (name, before.get("version", "?")),
                "old": before.get("license", "UNKNOWN"), "new": None, "alarm": False})
        else:
            old_lic = before.get("license", "UNKNOWN")
            new_lic = after.get("license", "UNKNOWN")
            if old_lic != new_lic:
                changes.append({
                    "kind": "license-change",
                    "name": "%s@%s" % (name, after.get("version", "?")),
                    "old": old_lic, "new": new_lic,
                    "alarm": is_restrictive(new_lic)})
    return changes


def format_report(changes):
    if not changes:
        return "no license drift. the swarm is calm."
    lines = ["license drift: %d change(s)" % len(changes)]
    marks = {"added": "+", "removed": "-", "license-change": "~"}
    for ch in changes:
        mark = "!" if ch["alarm"] else marks[ch["kind"]]
        if ch["kind"] == "license-change":
            detail = "%s -> %s" % (ch["old"], ch["new"])
        elif ch["kind"] == "added":
            detail = "new dependency, %s" % ch["new"]
        else:
            detail = "removed, was %s" % ch["old"]
        tail = "  [source-available]" if ch["alarm"] else ""
        lines.append("  %s %-24s %s%s" % (mark, ch["name"], detail, tail))
    return "\n".join(lines)


def exit_code(changes):
    if any(ch["alarm"] for ch in changes):
        return 2
    return 1 if changes else 0


def main(argv=None, current=None):
    parser = argparse.ArgumentParser(
        prog="license-drift", description="notice when dependencies change license")
    sub = parser.add_subparsers(dest="cmd")
    snap = sub.add_parser("snapshot", help="record current licenses")
    snap.add_argument("path", nargs="?", default="licenses.json")
    chk = sub.add_parser("check", help="compare current licenses to a snapshot")
    chk.add_argument("path", nargs="?", default="licenses.json")
    chk.add_argument("--update", action="store_true", help="rewrite snapshot after reporting")
    sub.add_parser("list", help="print current packages and licenses")

    args = parser.parse_args(argv)
    if not args.cmd:
        parser.print_help()
        return 3

    packages = current if current is not None else read_installed()

    if args.cmd == "list":
        for name in sorted(packages):
            info = packages[name]
            print("%-32s %-12s %s" % (name, info.get("version", "?"), info.get("license", "UNKNOWN")))
        return 0

    if args.cmd == "snapshot":
        save_snapshot(args.path, packages)
        print("wrote %d packages to %s" % (len(packages), args.path))
        return 0

    try:
        baseline = load_snapshot(args.path)
    except FileNotFoundError:
        print("no snapshot at %s — run: license-drift snapshot %s" % (args.path, args.path),
              file=sys.stderr)
        return 3
    except (ValueError, OSError) as exc:
        print("cannot read %s: %s" % (args.path, exc), file=sys.stderr)
        return 3

    changes = diff(baseline, packages)
    print(format_report(changes))
    if args.update and changes:
        save_snapshot(args.path, packages)
        print("snapshot updated.")
    return exit_code(changes)


if __name__ == "__main__":
    sys.exit(main())
