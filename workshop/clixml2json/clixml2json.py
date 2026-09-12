"""clixml2json - read PowerShell Export-Clixml files without PowerShell.

Pure stdlib. See README.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET

__all__ = ["loads", "load", "main", "SAMPLE_CLIXML"]

_NS = re.compile(r"^\{[^}]*\}")
_ESC = re.compile(r"_x([0-9A-Fa-f]{4})_")

_STRINGY = {"S", "DT", "TS", "G", "URI", "VERSION", "XD", "SBK"}
_INTY = {"BY", "SB", "U16", "I16", "U32", "I32", "U64", "I64"}
_FLOATY = {"SG", "DB", "D"}
_LISTY = {"LST", "IE", "STACK", "QUE"}

#: A small but complete CLIXML document, also shipped as sample.clixml.
#: `python clixml2json.py --demo > sample.clixml` regenerates the file.
SAMPLE_CLIXML = """<?xml version="1.0" encoding="utf-8"?>
<Objs Version="1.1.0.1" xmlns="http://schemas.microsoft.com/powershell/2004/04">
  <Obj RefId="0">
    <TN RefId="0">
      <T>Example.Broker.Application</T>
      <T>System.Object</T>
    </TN>
    <ToString>Banana Browser</ToString>
    <Props>
      <S N="Name">Banana Browser</S>
      <B N="Enabled">true</B>
      <I32 N="Priority">3</I32>
      <Db N="CpuWeight">1.5</Db>
      <Nil N="Description" />
      <S N="CommandLine">ripe.exe_x0020_--sniff</S>
      <BA N="IconData">3q2+7w==</BA>
      <Obj N="Tags" RefId="1">
        <TN RefId="1">
          <T>System.String[]</T>
          <T>System.Array</T>
        </TN>
        <LST>
          <S>fruit</S>
          <S>kitchen</S>
        </LST>
      </Obj>
      <Obj N="Limits" RefId="2">
        <TN RefId="2">
          <T>System.Collections.Hashtable</T>
        </TN>
        <DCT>
          <En>
            <S N="Key">MaxUsers</S>
            <I32 N="Value">50</I32>
          </En>
        </DCT>
      </Obj>
    </Props>
  </Obj>
  <Obj RefId="3">
    <TNRef RefId="0" />
    <ToString>Grape Grabber</ToString>
    <Props>
      <S N="Name">Grape Grabber</S>
      <B N="Enabled">false</B>
      <Ref N="SharesTagsWith" RefId="1" />
    </Props>
  </Obj>
</Objs>
"""


def _tag(el) -> str:
    return _NS.sub("", el.tag).upper()


def _unescape(s: str) -> str:
    return _ESC.sub(lambda m: chr(int(m.group(1), 16)), s or "")


class _Reader:
    def __init__(self, types: bool = False):
        self.types = types
        self.tns: dict[str, list[str]] = {}
        self.refs: dict[str, object] = {}

    def value(self, el):
        t = _tag(el)
        if t == "NIL":
            return None
        if t in _STRINGY:
            return _unescape(el.text or "")
        if t in _INTY:
            return int((el.text or "0").strip())
        if t in _FLOATY:
            return float((el.text or "0").strip())
        if t == "B":
            return (el.text or "").strip().lower() == "true"
        if t == "C":
            return chr(int((el.text or "0").strip()))
        if t == "BA":
            return (el.text or "").strip()
        if t in _LISTY:
            return [self.value(c) for c in el]
        if t == "DCT":
            return self._dct(el)
        if t == "OBJ":
            return self._obj(el)
        if t == "REF":
            rid = el.get("RefId")
            return self.refs.get(rid, {"$ref": rid})
        # Unknown element: best effort.
        if len(el):
            return [self.value(c) for c in el]
        return _unescape(el.text or "")

    def _dct(self, el):
        out = {}
        for en in el:
            key, val = None, None
            for c in en:
                if (c.get("N") or "").lower() == "key":
                    key = self.value(c)
                elif (c.get("N") or "").lower() == "value":
                    val = self.value(c)
            if key is not None:
                out[str(key)] = val
        return out

    def _obj(self, el):
        names = None
        members = {}
        items = None
        tostr = None
        for c in el:
            t = _tag(c)
            if t == "TN":
                names = [_unescape(x.text or "") for x in c]
                rid = c.get("RefId")
                if rid is not None:
                    self.tns[rid] = names
            elif t == "TNREF":
                names = self.tns.get(c.get("RefId"))
            elif t in ("MS", "PROPS"):
                for i, m in enumerate(c):
                    name = _unescape(m.get("N") or "") or "item%d" % i
                    members[name] = self.value(m)
            elif t == "TOSTRING":
                tostr = _unescape(c.text or "")
            elif t in _LISTY or t == "DCT":
                items = self.value(c)

        if members:
            out = dict(members)
            if items is not None:
                out["$items"] = items
            if self.types:
                if names:
                    out["$type"] = names[0]
                if tostr is not None:
                    out["$tostring"] = tostr
            result = out
        elif items is not None:
            result = items
        elif tostr is not None:
            result = tostr
        elif self.types and names:
            result = {"$type": names[0]}
        else:
            result = {}

        rid = el.get("RefId")
        if rid is not None:
            self.refs[rid] = result
        return result


def _strip_header(text: str) -> str:
    text = text.lstrip("﻿")
    if text.lstrip().startswith("#<"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
    return text


def loads(text: str, types: bool = False) -> list:
    """Deserialize CLIXML text into a list of plain Python values."""
    root = ET.fromstring(_strip_header(text))
    reader = _Reader(types=types)
    if _tag(root) == "OBJS":
        return [reader.value(c) for c in root]
    return [reader.value(root)]


def load(path, types: bool = False) -> list:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return loads(fh.read(), types=types)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Convert PowerShell CLIXML to JSON.")
    p.add_argument("path", nargs="?", default="-", help="file, or - for stdin")
    p.add_argument("--types", action="store_true", help="keep $type/$tostring")
    p.add_argument("--compact", action="store_true", help="single-line JSON")
    p.add_argument("--unwrap", action="store_true",
                   help="if there is exactly one root object, emit it bare")
    p.add_argument("--indent", type=int, default=2)
    p.add_argument("-o", "--output", help="write to file instead of stdout")
    p.add_argument("--demo", action="store_true",
                   help="print a sample CLIXML document and exit")
    a = p.parse_args(argv)

    if a.demo:
        sys.stdout.write(SAMPLE_CLIXML)
        return 0

    if a.path == "-":
        text = sys.stdin.read()
    else:
        try:
            with open(a.path, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
        except OSError as exc:
            print("clixml2json: cannot read %s: %s" % (a.path, exc.strerror),
                  file=sys.stderr)
            return 2

    try:
        data = loads(text, types=a.types)
    except ET.ParseError as exc:
        print("clixml2json: not valid CLIXML/XML: %s" % exc, file=sys.stderr)
        return 2
    if a.unwrap and len(data) == 1:
        data = data[0]
    out = json.dumps(data, ensure_ascii=False,
                     indent=None if a.compact else a.indent,
                     separators=(",", ":") if a.compact else None)
    if a.output:
        try:
            with open(a.output, "w", encoding="utf-8") as fh:
                fh.write(out + "\n")
        except OSError as exc:
            print("clixml2json: cannot write %s: %s" % (a.output, exc.strerror),
                  file=sys.stderr)
            return 2
    else:
        print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
