#!/usr/bin/env python3
"""Lint a powershell.config.json file. Dependency-free, stdlib only."""
from __future__ import annotations

import difflib
import json
import os
import sys
from dataclasses import dataclass

EXECUTION_POLICIES = {"AllSigned", "Bypass", "Default", "RemoteSigned",
                      "Restricted", "Undefined", "Unrestricted"}
LOG_LEVELS = {"None", "Critical", "Error", "Warning", "Informational",
              "Verbose", "Debug"}
LOG_CHANNELS = {"Operational", "Analytic"}
LOG_KEYWORDS = {"Runspace", "Pipeline", "Protocol", "Transport", "Host",
                "Cmdlets", "Serializer", "Session", "ManagedPlugin"}

# key -> (kind, allowed values or None)
KNOWN_KEYS = {
    "ExecutionPolicy": ("str", EXECUTION_POLICIES),
    "PSModulePath": ("str", None),
    "ExperimentalFeatures": ("strlist", None),
    "DisableImplicitWinCompat": ("bool", None),
    "WindowsPowerShellCompatibilityModuleDenyList": ("strlist", None),
    "WindowsPowerShellCompatibilityNoClobberModuleList": ("strlist", None),
    "PowerShellPolicies": ("object", None),
    "LogIdentity": ("str", None),
    "LogLevel": ("str", LOG_LEVELS),
    "LogChannels": ("csv", LOG_CHANNELS),
    "LogKeywords": ("csv", LOG_KEYWORDS),
}


@dataclass
class Finding:
    level: str   # "error" | "warning"
    line: int
    key: str | None
    message: str

    def format(self, path: str) -> str:
        where = f"{path}:{self.line}" if self.line else path
        return f"{where}: {self.level.upper()}: {self.message}"


def _line_of_key(text: str, key: str) -> int:
    needle = '"' + key + '"'
    for n, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return n
    return 0


def scan_syntax(text: str) -> list[Finding]:
    """Textual pass: things that make the JSON parser (or a human) unhappy."""
    out: list[Finding] = []
    if text.startswith("﻿"):
        out.append(Finding("warning", 1, None,
                           "file starts with a UTF-8 BOM - save as UTF-8 "
                           "without BOM to be safe"))
        text = text[1:]
    i, line, n = 0, 1, len(text)
    in_str = esc = False
    seen: set[str] = set()
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == "'":
            if "quote" not in seen:
                seen.add("quote")
                out.append(Finding("error", line, None,
                                   "single-quoted string - JSON requires "
                                   'double quotes'))
        elif c == "/" and i + 1 < n and text[i + 1] in "/*":
            if "comment" not in seen:
                seen.add("comment")
                out.append(Finding("error", line, None,
                                   "comment found - powershell.config.json "
                                   "must be strict JSON, no // or /* */"))
            if text[i + 1] == "/":
                j = text.find("\n", i)
                i = n if j < 0 else j
            else:
                j = text.find("*/", i + 2)
                j = n if j < 0 else j + 2
                line += text.count("\n", i, j)
                i = j
            continue
        elif c == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in "}]":
                out.append(Finding("error", line, None,
                                   f"trailing comma before '{text[j]}' - "
                                   "JSON does not allow it"))
        i += 1
    if in_str:
        out.append(Finding("error", line, None, "unterminated string"))
    return out


def _check_value(key: str, value, text: str) -> list[Finding]:
    out: list[Finding] = []
    ln = _line_of_key(text, key)
    kind, allowed = KNOWN_KEYS[key]
    if kind == "bool":
        if not isinstance(value, bool):
            out.append(Finding("error", ln, key,
                               f"'{key}' must be true or false, got "
                               f"{json.dumps(value)}"))
        return out
    if kind == "object":
        if not isinstance(value, dict):
            out.append(Finding("error", ln, key, f"'{key}' must be an object"))
        return out
    if kind == "strlist":
        if not isinstance(value, list) or not all(
                isinstance(v, str) for v in value):
            out.append(Finding("error", ln, key,
                               f"'{key}' must be an array of strings"))
        elif not value:
            out.append(Finding("warning", ln, key,
                               f"'{key}' is an empty array - it has no effect"))
        return out
    # str / csv
    if not isinstance(value, str):
        out.append(Finding("error", ln, key, f"'{key}' must be a string"))
        return out
    if kind == "csv":
        parts = [p.strip() for p in value.split(",") if p.strip()]
        if not parts:
            out.append(Finding("warning", ln, key, f"'{key}' is empty"))
        for p in parts:
            if p not in allowed:
                out.append(Finding("error", ln, key,
                                   f"'{key}': unknown value '{p}' "
                                   f"(allowed: {', '.join(sorted(allowed))})"))
        return out
    if allowed and value not in allowed:
        hint = difflib.get_close_matches(value, sorted(allowed), 1, 0.5)
        extra = f" - did you mean '{hint[0]}'?" if hint else ""
        out.append(Finding("error", ln, key,
                           f"'{key}': invalid value '{value}'{extra} "
                           f"(allowed: {', '.join(sorted(allowed))})"))
    if key == "PSModulePath":
        if "%" in value or "$env:" in value.lower() or "~" in value:
            out.append(Finding("warning", ln, key,
                               "PSModulePath is not expanded - use fully "
                               "qualified paths, not %VAR% / $env: / ~"))
    return out


def lint_text(text: str, name: str = "powershell.config.json") -> list[Finding]:
    out = scan_syntax(text)
    body = text.lstrip("﻿")
    dups: list[str] = []

    def hook(pairs):
        seen = set()
        for k, _ in pairs:
            if k in seen:
                dups.append(k)
            seen.add(k)
        return dict(pairs)

    try:
        data = json.loads(body or "null", object_pairs_hook=hook)
    except json.JSONDecodeError as exc:
        out.append(Finding("error", exc.lineno, None,
                           f"invalid JSON: {exc.msg} (column {exc.colno})"))
        return out
    for k in dups:
        out.append(Finding("error", _line_of_key(body, k), k,
                           f"duplicate key '{k}' - the last one silently wins"))
    if data is None and not body.strip():
        out.append(Finding("warning", 0, None, "file is empty"))
        return out
    if not isinstance(data, dict):
        out.append(Finding("error", 1, None,
                           "top level must be a JSON object { ... }"))
        return out
    for key, value in data.items():
        if key in KNOWN_KEYS:
            out.extend(_check_value(key, value, body))
            continue
        if key.endswith(":ExecutionPolicy"):  # e.g. Microsoft.PowerShell:...
            out.extend(_check_value("ExecutionPolicy", value,
                                    body.replace(key, "ExecutionPolicy")))
            continue
        ln = _line_of_key(body, key)
        lower = {k.lower(): k for k in KNOWN_KEYS}
        if key.lower() in lower:
            out.append(Finding("error", ln, key,
                               f"unknown key '{key}' - did you mean "
                               f"'{lower[key.lower()]}'? "
                               "(keys are case-sensitive)"))
        else:
            hint = difflib.get_close_matches(key, sorted(KNOWN_KEYS), 1, 0.6)
            extra = f" - did you mean '{hint[0]}'?" if hint else \
                    " - it will be ignored"
            out.append(Finding("warning", ln, key,
                               f"unknown key '{key}'{extra}"))
    if os.path.basename(name) not in ("powershell.config.json", "-", "<text>"):
        out.append(Finding("warning", 0, None,
                           f"file is named '{os.path.basename(name)}'; "
                           "PowerShell only reads 'powershell.config.json'"))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    strict = "--strict" in argv
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")]
    if not paths:
        print("usage: psconfig_lint.py FILE... [--strict] [--json]",
              file=sys.stderr)
        return 2
    rc = 0
    report = []
    for path in paths:
        try:
            text = sys.stdin.read() if path == "-" else \
                open(path, encoding="utf-8-sig").read()
        except OSError as exc:
            print(f"{path}: cannot read: {exc}", file=sys.stderr)
            rc = max(rc, 2)
            continue
        findings = lint_text(text, path)
        for f in findings:
            if as_json:
                report.append({"path": path, "level": f.level, "line": f.line,
                               "key": f.key, "message": f.message})
            else:
                print(f.format(path))
            if f.level == "error" or strict:
                rc = max(rc, 1)
        if not findings and not as_json:
            print(f"{path}: ok")
    if as_json:
        print(json.dumps(report, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
