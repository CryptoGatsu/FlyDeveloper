#!/usr/bin/env python3
"""psd1peek - parse and lint PowerShell module manifests without PowerShell."""
from __future__ import annotations

import argparse
import json
import re
import sys

__all__ = ["loads", "lint", "Psd1Error", "main"]


class Psd1Error(ValueError):
    """Raised when a .psd1 file is not a plain data hashtable."""


_PUNCT = "{}(),;="
_WORD_CHARS = set("$._-+\\/:*")
_DQ_ESC = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a",
           "b": "\b", "`": "`", '"': '"', "'": "'", "$": "$"}


def _tokenize(text):
    toks, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c in " \t\r\n﻿":
            i += 1
            continue
        if c == "`" and i + 1 < n and text[i + 1] in "\r\n":
            i += 2
            continue
        if c == "#":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("<#", i):
            end = text.find("#>", i + 2)
            if end < 0:
                raise Psd1Error("unterminated block comment")
            i = end + 2
            continue
        if text.startswith("@{", i) or text.startswith("@(", i):
            toks.append((text[i:i + 2], None))
            i += 2
            continue
        if c in _PUNCT:
            toks.append((c, None))
            i += 1
            continue
        if c == "'":
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise Psd1Error("unterminated single-quoted string")
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        buf.append("'")
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(text[i])
                i += 1
            toks.append(("str", "".join(buf)))
            continue
        if c == '"':
            i += 1
            buf = []
            while True:
                if i >= n:
                    raise Psd1Error("unterminated double-quoted string")
                ch = text[i]
                if ch == "`" and i + 1 < n:
                    buf.append(_DQ_ESC.get(text[i + 1], text[i + 1]))
                    i += 2
                    continue
                if ch == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        buf.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(ch)
                i += 1
            toks.append(("str", "".join(buf)))
            continue
        # bare word; PowerShell also honours backtick escapes here
        j, buf, escaped = i, [], False
        while j < n:
            ch = text[j]
            if ch == "`" and j + 1 < n and text[j + 1] not in "\r\n":
                buf.append(_DQ_ESC.get(text[j + 1], text[j + 1]))
                j += 2
                escaped = True
                continue
            if ch.isalnum() or ch in _WORD_CHARS:
                buf.append(ch)
                j += 1
                continue
            break
        if j == i:
            raise Psd1Error("unexpected character %r at offset %d" % (c, i))
        # an escape means the author meant text, not $true / 42 / 5.1
        toks.append(("str" if escaped else "word", "".join(buf)))
        i = j
    return toks


def _word_value(w):
    low = w.lower()
    if low == "$true":
        return True
    if low == "$false":
        return False
    if low == "$null":
        return None
    if low.startswith("$"):
        raise Psd1Error("variable %s is not allowed in a data file" % w)
    try:
        return int(w, 0)
    except ValueError:
        pass
    try:
        return float(w)
    except ValueError:
        pass
    return w


class _Parser:
    def __init__(self, toks):
        self.toks = toks
        self.i = 0

    def peek(self):
        return self.toks[self.i][0] if self.i < len(self.toks) else None

    def take(self):
        if self.i >= len(self.toks):
            raise Psd1Error("unexpected end of manifest")
        tok = self.toks[self.i]
        self.i += 1
        return tok

    def expect(self, kind):
        tok = self.take()
        if tok[0] != kind:
            raise Psd1Error("expected %r, got %r" % (kind, tok[1] or tok[0]))
        return tok

    def hashtable(self):
        self.expect("@{")
        out = {}
        while True:
            kind = self.peek()
            if kind is None:
                raise Psd1Error("unterminated hashtable")
            if kind == "}":
                self.take()
                return out
            if kind in (";", ","):
                self.take()
                continue
            kind, val = self.take()
            if kind not in ("word", "str"):
                raise Psd1Error("expected a key, got %r" % (val or kind))
            self.expect("=")
            out[val] = self.comma_list()

    def comma_list(self):
        first = self.value()
        if self.peek() != ",":
            return first
        items = [first]
        while self.peek() == ",":
            self.take()
            items.append(self.value())
        return items

    def value(self):
        kind = self.peek()
        if kind == "@{":
            return self.hashtable()
        if kind == "@(":
            self.take()
            items = []
            while True:
                k = self.peek()
                if k is None:
                    raise Psd1Error("unterminated array")
                if k == ")":
                    self.take()
                    return items
                if k in (",", ";"):
                    self.take()
                    continue
                items.append(self.value())
        if kind == "(":
            self.take()
            inner = self.comma_list()
            self.expect(")")
            return inner
        kind, val = self.take()
        if kind == "str":
            return val
        if kind == "word":
            return _word_value(val)
        raise Psd1Error("unexpected token %r" % (val or kind))


def loads(text):
    """Parse .psd1 text into Python data. Raises Psd1Error on anything weird."""
    parser = _Parser(_tokenize(text))
    if parser.peek() != "@{":
        raise Psd1Error("manifest must be a single @{ ... } hashtable")
    data = parser.hashtable()
    if parser.peek() is not None:
        raise Psd1Error("trailing content after the hashtable")
    return data


KNOWN_KEYS = {k.lower() for k in (
    "RootModule ModuleToProcess ModuleVersion CompatiblePSEditions GUID Author "
    "CompanyName Copyright Description PowerShellVersion PowerShellHostName "
    "PowerShellHostVersion DotNetFrameworkVersion ClrVersion CLRVersion "
    "ProcessorArchitecture RequiredModules RequiredAssemblies ScriptsToProcess "
    "TypesToProcess FormatsToProcess NestedModules FunctionsToExport "
    "CmdletsToExport VariablesToExport AliasesToExport DscResourcesToExport "
    "ModuleList FileList PrivateData HelpInfoURI DefaultCommandPrefix"
).split()}

_VERSION_RE = re.compile(r"^\d+(\.\d+){0,3}$")


def _version_tuple(value):
    text = repr(value) if isinstance(value, float) else str(value)
    if not _VERSION_RE.match(text):
        return None
    return tuple(int(p) for p in text.split("."))


def lint(data):
    """Return a list of (level, code, message) tuples for a parsed manifest."""
    issues = []
    keys = {k.lower(): k for k in data}

    def get(name):
        return data.get(keys.get(name.lower(), "\0"))

    for key in data:
        if key.lower() not in KNOWN_KEYS:
            issues.append(("warning", "PSD012",
                           "unknown key %r - typo? (PowerShell ignores it)" % key))

    ver = get("ModuleVersion")
    if ver is None:
        issues.append(("error", "PSD001", "ModuleVersion is missing"))
    elif _version_tuple(ver) is None:
        issues.append(("error", "PSD002",
                       "ModuleVersion %r is not N[.N[.N[.N]]]" % (ver,)))

    guid = get("GUID")
    if not guid or str(guid).strip("0-") == "":
        issues.append(("warning", "PSD003", "GUID is missing or all zeros"))

    author = get("Author")
    if not isinstance(author, str) or not author.strip():
        issues.append(("warning", "PSD004", "Author is missing or empty"))

    desc = get("Description")
    if not isinstance(desc, str) or not desc.strip():
        issues.append(("warning", "PSD005",
                       "Description is missing (the PowerShell Gallery requires it)"))

    if "moduletoprocess" in keys and "rootmodule" not in keys:
        issues.append(("warning", "PSD006",
                       "ModuleToProcess is deprecated; use RootModule"))

    for name in ("FunctionsToExport", "CmdletsToExport",
                 "AliasesToExport", "VariablesToExport"):
        val = get(name)
        if name.lower() not in keys:
            issues.append(("warning", "PSD007",
                           "%s is missing - everything is exported and discovery is slow" % name))
        elif val == "*" or (isinstance(val, list) and "*" in val):
            issues.append(("warning", "PSD007",
                           "%s uses '*' - list names explicitly for fast discovery" % name))

    raw_ps_ver = get("PowerShellVersion")
    ps_ver = _version_tuple(raw_ps_ver) if raw_ps_ver is not None else None
    editions = get("CompatiblePSEditions")
    if editions is None:
        issues.append(("info", "PSD010",
                       "no CompatiblePSEditions - the module is treated as Desktop only"))
    else:
        if isinstance(editions, str):
            editions = [editions]
        bad = [e for e in editions if str(e).lower() not in ("desktop", "core")]
        if bad:
            issues.append(("error", "PSD008",
                           "CompatiblePSEditions has invalid value(s): %s"
                           % ", ".join(map(str, bad))))
        if ps_ver is None or ps_ver < (5, 1):
            issues.append(("error", "PSD009",
                           "CompatiblePSEditions requires PowerShellVersion '5.1' or higher"))

    required = get("RequiredModules")
    if isinstance(required, dict):
        required = [required]
    for entry in required or []:
        if isinstance(entry, dict):
            low = {k.lower() for k in entry}
            if not low & {"moduleversion", "requiredversion", "maximumversion"}:
                issues.append(("warning", "PSD011",
                               "RequiredModules entry %r pins no version"
                               % entry.get("ModuleName", entry)))
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser(prog="psd1peek",
                                 description="Read/lint a PowerShell .psd1 manifest.")
    ap.add_argument("path")
    ap.add_argument("--lint", action="store_true", help="report manifest problems")
    ap.add_argument("--strict", action="store_true", help="warnings are failures")
    ap.add_argument("--key", help="print one top-level key instead of the whole file")
    args = ap.parse_args(argv)

    try:
        with open(args.path, encoding="utf-8-sig") as fh:
            text = fh.read()
        data = loads(text)
    except Psd1Error as exc:
        print("%s: parse error: %s" % (args.path, exc), file=sys.stderr)
        return 2
    except OSError as exc:
        print("%s: %s" % (args.path, exc), file=sys.stderr)
        return 2

    if args.lint:
        issues = lint(data)
        for level, code, msg in issues:
            print("%s: %s %s: %s" % (args.path, level, code, msg))
        errors = sum(1 for i in issues if i[0] == "error")
        warns = sum(1 for i in issues if i[0] == "warning")
        if not issues:
            print("%s: clean" % args.path)
        return 1 if errors or (args.strict and warns) else 0

    if args.key:
        match = {k.lower(): k for k in data}.get(args.key.lower())
        if match is None:
            print("%s: no such key: %s" % (args.path, args.key), file=sys.stderr)
            return 1
        value = data[match]
        print(value if isinstance(value, str) else json.dumps(value))
        return 0

    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
