"""Persistent memory for the fly: a small JSON journal.

Everything the fly does is appended here so that later ticks (and humans)
can see what it browsed, what it built, which memes it drew and which
coins it launched or merely planned.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_ENTRIES = 500


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Memory:
    path: Path
    data: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    KEYS = ("journal", "pages", "ideas", "builds", "memes", "launches", "drives", "searches", "learnings", "posts", "playbook")

    def __post_init__(self) -> None:
        for key in self.KEYS:
            self.data.setdefault(key, [])

    @classmethod
    def load(cls, path: Path) -> "Memory":
        mem = cls(path=path)
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    for key in cls.KEYS:
                        value = loaded.get(key, [])
                        if isinstance(value, list):
                            mem.data[key] = value
            except (OSError, ValueError):
                pass
        return mem

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for key in self.KEYS:
            self.data[key] = self.data[key][-MAX_ENTRIES:]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self.path)

    # -- writes ------------------------------------------------------------
    def add(self, key: str, entry: dict[str, Any]) -> dict[str, Any]:
        entry = {"at": now_iso(), "ts": time.time(), **entry}
        self.data[key].append(entry)
        return entry

    def note(self, text: str, **extra: Any) -> None:
        self.add("journal", {"text": text, **extra})

    # -- reads -------------------------------------------------------------
    def last(self, key: str) -> dict[str, Any] | None:
        items = self.data.get(key) or []
        return items[-1] if items else None

    def recent(self, key: str, n: int = 10) -> list[dict[str, Any]]:
        return list(self.data.get(key) or [])[-n:]

    def hours_since(self, key: str, default: float = 1e6) -> float:
        item = self.last(key)
        if not item or "ts" not in item:
            return default
        return max(0.0, (time.time() - float(item["ts"])) / 3600.0)

    def hours_since_kind(self, key: str, kind: str, default: float = 1e6) -> float:
        for item in reversed(self.data.get(key) or []):
            if item.get("kind") == kind and "ts" in item:
                return max(0.0, (time.time() - float(item["ts"])) / 3600.0)
        return default

    def count_since(self, key: str, hours: float, **match: Any) -> int:
        cutoff = time.time() - hours * 3600.0
        n = 0
        for item in self.data.get(key) or []:
            if float(item.get("ts", 0)) < cutoff:
                continue
            if all(item.get(k) == v for k, v in match.items()):
                n += 1
        return n

    def visited(self, url: str) -> bool:
        return any(p.get("url") == url for p in self.data.get("pages") or [])

    def forget_launches(self, symbol: str = "", dry_runs: bool = False) -> list[dict[str, Any]]:
        """Drop launch records that never reached the chain: a dry run by
        symbol, or every dry run. Live launches are never forgotten."""
        keep, gone = [], []
        for l in self.data.get("launches") or []:
            dry = not l.get("live") and l.get("status") in (None, "", "planned", "blocked")
            match = dry and (dry_runs or (symbol and str(l.get("symbol", "")).upper() == symbol.upper()))
            (gone if match else keep).append(l)
        self.data["launches"] = keep
        return gone

    def unlaunched_memes(self) -> list[dict[str, Any]]:
        launched = {l.get("meme") for l in self.data.get("launches") or [] if l.get("live")}
        return [m for m in self.data.get("memes") or [] if m.get("path") not in launched]

    def summary(self, n: int = 8) -> str:
        """A compact natural-language digest for the mind's context window."""
        lines = []
        for page in self.recent("pages", n):
            lines.append(f"- read: {page.get('title') or page.get('url')} :: {page.get('gist', '')[:160]}")
        for idea in self.recent("ideas", n):
            lines.append(f"- idea: {idea.get('title')} ({idea.get('slug')}) for {idea.get('for_whom')}")
        for build in self.recent("builds", n):
            lines.append(f"- built: {build.get('slug')} ok={build.get('ok')}")
        for meme in self.recent("memes", n):
            lines.append(f"- meme: {meme.get('top')} / {meme.get('bottom')}")
        for launch in self.recent("launches", n):
            lines.append(
                f"- coin: {launch.get('symbol')} {launch.get('name')} live={launch.get('live')} tx={launch.get('tx', '')}"
            )
        return "\n".join(lines) if lines else "(nothing yet: the fly just hatched)"
