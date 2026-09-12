"""Self-preservation: check-ups, circuit breakers, heartbeat and self-update.

A brain has to keep itself running. Before every action the fly checks the
world it depends on (network, git, its memory file, disk) and repairs what it
can; actions that keep failing are suspended for a while instead of taking
the loop down; a heartbeat lets a watchdog restart a stuck process; and
every few hours the fly pulls its own updates from the repository.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

Logger = Callable[[str], None]


@dataclass
class Breaker:
    failures: int = 0
    open_until: float = 0.0
    last_error: str = ""


@dataclass
class HealthState:
    breakers: dict[str, Breaker] = field(default_factory=dict)
    last_checkup: float = 0.0
    last_update_check: float = 0.0
    last_proposal: float = 0.0
    proposals_today: int = 0
    proposal_day: str = ""
    incidents: list[dict[str, Any]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    restarts: int = 0

    def to_json(self) -> dict[str, Any]:
        return {
            "breakers": {k: vars(v) for k, v in self.breakers.items()},
            "last_checkup": self.last_checkup, "last_update_check": self.last_update_check,
            "last_proposal": self.last_proposal, "proposals_today": self.proposals_today,
            "proposal_day": self.proposal_day, "incidents": self.incidents[-50:],
            "started_at": self.started_at, "restarts": self.restarts,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> "HealthState":
        h = cls()
        for k, v in (d.get("breakers") or {}).items():
            h.breakers[k] = Breaker(failures=int(v.get("failures", 0)), open_until=float(v.get("open_until", 0)),
                                    last_error=str(v.get("last_error", "")))
        for k in ("last_checkup", "last_update_check", "last_proposal", "proposals_today", "proposal_day",
                  "started_at", "restarts"):
            if k in d:
                setattr(h, k, d[k])
        h.incidents = list(d.get("incidents") or [])
        return h


class Health:
    BREAK_AFTER = 3            # consecutive failures before an action is suspended
    BREAK_FOR_SEC = 2 * 3600
    CHECKUP_EVERY_SEC = 600
    UPDATE_EVERY_SEC = 6 * 3600
    HEARTBEAT_STALE_SEC = 45 * 60

    def __init__(self, root: Path, log: Logger = print):
        self.root = root
        self.log = log
        self.path = root / "data" / "fly_health.json"
        self.heartbeat_path = root / "data" / "fly_heartbeat"
        self.state = self._load()
        self.state.restarts += 1
        self.save()

    # -- persistence -----------------------------------------------------------
    def _load(self) -> HealthState:
        try:
            if self.path.is_file():
                return HealthState.from_json(json.loads(self.path.read_text(encoding="utf-8")))
        except Exception:
            pass
        return HealthState()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.state.to_json(), indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass

    def incident(self, kind: str, detail: str, fixed: str = "") -> None:
        self.state.incidents.append({
            "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "ts": time.time(),
            "kind": kind, "detail": detail[:600], "fixed": fixed[:300],
        })
        self.state.incidents = self.state.incidents[-50:]
        self.save()

    # -- heartbeat / watchdog ----------------------------------------------------
    def beat(self, phase: str = "") -> None:
        try:
            self.heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            self.heartbeat_path.write_text(f"{time.time()} {phase}\n", encoding="utf-8")
        except OSError:
            pass

    def start_watchdog(self) -> None:
        """If the loop stops beating for too long, exit so the supervisor restarts us."""
        def run():
            while True:
                time.sleep(60)
                try:
                    stamp = float(self.heartbeat_path.read_text().split()[0])
                except Exception:
                    continue
                if time.time() - stamp > self.HEARTBEAT_STALE_SEC:
                    self.incident("stuck", f"no heartbeat for {int(time.time() - stamp)}s", fixed="restarted by the watchdog")
                    self.log("watchdog: the fly is stuck; restarting")
                    os._exit(3)
        threading.Thread(target=run, daemon=True).start()

    # -- circuit breakers ----------------------------------------------------------
    def allowed(self, action: str) -> bool:
        b = self.state.breakers.get(action)
        return not b or b.open_until <= time.time()

    def suspended(self) -> list[str]:
        now = time.time()
        return [k for k, b in self.state.breakers.items() if b.open_until > now]

    def succeeded(self, action: str) -> None:
        b = self.state.breakers.get(action)
        if b and (b.failures or b.open_until):
            self.state.breakers[action] = Breaker()
            self.save()

    def failed(self, action: str, error: str) -> bool:
        """Record a failure; returns True if the action just got suspended."""
        b = self.state.breakers.setdefault(action, Breaker())
        b.failures += 1
        b.last_error = error[:300]
        tripped = False
        if b.failures >= self.BREAK_AFTER:
            b.open_until = time.time() + self.BREAK_FOR_SEC
            b.failures = 0
            tripped = True
            self.incident("breaker", f"{action} failed {self.BREAK_AFTER} times: {error[:200]}",
                          fixed=f"suspended {action} for {self.BREAK_FOR_SEC // 3600}h")
        self.save()
        return tripped

    # -- check-ups -------------------------------------------------------------------
    def checkup(self, force: bool = False) -> list[str]:
        """Run the cheap checks; fix what can be fixed; return notes."""
        if not force and time.time() - self.state.last_checkup < self.CHECKUP_EVERY_SEC:
            return []
        self.state.last_checkup = time.time()
        notes: list[str] = []
        notes += self.check_memory()
        notes += self.check_git()
        notes += self.check_disk()
        self.save()
        return notes

    def network_up(self, url: str = "https://api.anthropic.com/") -> bool:
        try:
            import requests

            requests.head(url, timeout=8)
            return True
        except Exception:
            return False

    def wait_for_network(self, max_wait_sec: int = 3600) -> bool:
        """Back off while the network is down; returns True once it is back."""
        delay, waited = 30, 0
        while not self.network_up():
            if waited == 0:
                self.log("network is down; waiting for it")
                self.incident("network", "no route to the internet")
            self.beat("waiting for network")
            time.sleep(delay)
            waited += delay
            delay = min(600, delay * 2)
            if waited >= max_wait_sec:
                return False
        if waited:
            self.incident("network", f"back after {waited}s", fixed="resumed")
        return True

    def check_memory(self) -> list[str]:
        mem = self.root / "data" / "fly_memory.json"
        bak = self.root / "data" / "fly_memory.bak.json"
        notes: list[str] = []
        if mem.is_file():
            try:
                json.loads(mem.read_text(encoding="utf-8"))
                shutil.copy2(mem, bak)                    # good copy: refresh the backup
            except ValueError:
                if bak.is_file():
                    shutil.copy2(bak, mem)
                    notes.append("memory file was corrupt; restored from backup")
                    self.incident("memory", "corrupt fly_memory.json", fixed="restored backup")
                else:
                    mem.rename(mem.with_suffix(".corrupt.json"))
                    notes.append("memory file was corrupt; starting a fresh one")
                    self.incident("memory", "corrupt fly_memory.json, no backup", fixed="fresh memory")
        return notes

    def _git(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True, text=True, timeout=timeout)

    def check_git(self) -> list[str]:
        notes: list[str] = []
        try:
            git_dir = self.root / ".git"
            if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
                self._git("rebase", "--abort")
                notes.append("found a half-finished rebase; aborted it")
                self.incident("git", "rebase in progress", fixed="aborted")
            if (git_dir / "MERGE_HEAD").exists():
                self._git("merge", "--abort")
                notes.append("found a half-finished merge; aborted it")
            st = self._git("status", "--porcelain", "--", "site/data/state.json")
            if st.stdout.startswith("UU"):
                self._git("checkout", "--theirs", "--", "site/data/state.json")
                self._git("add", "site/data/state.json")
                notes.append("state.json was conflicted; kept the remote copy (it is regenerated anyway)")
        except Exception as exc:
            notes.append(f"git check failed: {exc}")
        return notes

    def check_disk(self) -> list[str]:
        notes: list[str] = []
        try:
            usage = shutil.disk_usage(str(self.root))
            if usage.free < 500 * 1024 * 1024:
                shots = self.root / "site" / "browsing" / "shots"
                removed = 0
                if shots.is_dir():
                    for f in sorted(shots.glob("*.jpg"))[:-40]:
                        f.unlink(missing_ok=True)
                        removed += 1
                notes.append(f"disk nearly full; removed {removed} old screenshots")
                self.incident("disk", f"{usage.free // 1024 // 1024} MB free", fixed=f"pruned {removed} shots")
        except Exception:
            pass
        return notes

    # -- self-update (pulls reviewed changes from the repository) ------------------
    def maybe_update(self) -> bool:
        """Pull the fly's own updates every few hours; True if the code changed
        (the caller should restart on it)."""
        if time.time() - self.state.last_update_check < self.UPDATE_EVERY_SEC:
            return False
        self.state.last_update_check = time.time()
        self.save()
        try:
            self._git("fetch", "-q", "origin")
            branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
            behind = self._git("rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip()
            if not behind.isdigit() or int(behind) == 0:
                return False
            self._git("checkout", "--", "site/data/state.json")
            r = self._git("pull", "--rebase", "--autostash", "-X", "theirs", "-q")
            if r.returncode != 0:
                self._git("rebase", "--abort")
                self.incident("update", f"pull failed: {(r.stderr or r.stdout)[-200:]}")
                return False
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(self.root / "requirements-fly.txt")],
                           capture_output=True, timeout=600)
            self.incident("update", f"pulled {behind} new commit(s)", fixed="restarting on new code")
            self.log(f"pulled {behind} update(s); restarting on the new code")
            return True
        except Exception as exc:
            self.incident("update", f"self-update failed: {exc}")
            return False

    def summary(self) -> dict[str, Any]:
        return {
            "uptime_sec": int(time.time() - self.state.started_at), "restarts": self.state.restarts,
            "suspended": self.suspended(), "incidents": self.state.incidents[-10:],
            "proposals_today": self.state.proposals_today,
        }
