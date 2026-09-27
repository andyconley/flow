"""Identity evidence for the processes a v8 delivery parent starts (ADR 0019).

A control record names the dispatching parent by pid, a timezone-independent
start time, and a machine id, and lists every process group the parent started
with its leader's start time. It is evidence of identity only: it grants no
authority, and every destructive use re-checks the live process first.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import os
import re
import signal
import socket
import struct
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

GROUP_KINDS = frozenset({"maf", "provider", "test"})
_CONTROL_NAME = re.compile(r"^control-g([1-9][0-9]{0,8})\.json$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@lru_cache(maxsize=1)
def _libc() -> Any:
    return ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


def _darwin_start(pid: int) -> str | None:
    """``kinfo_proc.kp_proc.p_starttime`` from sysctl KERN_PROC_PID; None when the pid is gone."""
    ctl_kern, kern_proc, kern_proc_pid = 1, 14, 1
    mib = (ctypes.c_int * 4)(ctl_kern, kern_proc, kern_proc_pid, pid)
    size = ctypes.c_size_t(0)
    libc = _libc()
    if libc.sysctl(mib, 4, None, ctypes.byref(size), None, 0) != 0 or size.value == 0:
        return None
    buffer = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 4, buffer, ctypes.byref(size), None, 0) != 0 or size.value == 0:
        return None
    # extern_proc begins with a union whose timeval member is p_starttime.
    seconds, micros = struct.unpack_from("qi", buffer.raw, 0)
    if seconds <= 0:
        return None
    return f"darwin:{seconds}.{micros:06d}"


def linux_start_from_stat(stat_text: str, boot_id: str) -> str | None:
    """Parse field 22 (start time in clock ticks since boot) of ``/proc/<pid>/stat``.

    The command name (field 2) may contain spaces and parentheses, so fields
    are counted after its last closing parenthesis.
    """
    close = stat_text.rfind(")")
    if close < 0 or not boot_id:
        return None
    fields = stat_text[close + 2:].split()
    # fields[0] is field 3 (state); field 22 is fields[19].
    if len(fields) < 20 or not fields[19].isdigit():
        return None
    return f"linux:{boot_id}:{int(fields[19])}"


def _linux_start(pid: int) -> str | None:
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text()
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        return None
    return linux_start_from_stat(stat_text, boot_id)


def start_time(pid: int) -> str | None:
    """The canonical start time of a live pid, or None when it is gone or unreadable."""
    if type(pid) is not int or pid <= 0:
        return None
    if sys.platform == "darwin":
        return _darwin_start(pid)
    if sys.platform.startswith("linux"):
        return _linux_start(pid)
    return None


def _start_key(value: Any) -> tuple[str, Decimal] | None:
    """A comparable form of one start time; only values of one clock compare."""
    if not isinstance(value, str):
        return None
    try:
        if value.startswith("darwin:"):
            return ("darwin", Decimal(value[len("darwin:"):]))
        if value.startswith("linux:"):
            _, boot_id, ticks = value.split(":")
            return ("linux:" + boot_id, Decimal(int(ticks)))
    except (ValueError, InvalidOperation):
        return None
    return None


def started_at_or_after(value: Any, reference: Any) -> bool:
    current, floor = _start_key(value), _start_key(reference)
    return current is not None and floor is not None and current[0] == floor[0] and current[1] >= floor[1]


@lru_cache(maxsize=1)
def machine_id() -> str:
    """A stable id for this machine; the host name is display only."""
    if sys.platform == "darwin":
        try:
            output = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True,
                                    text=True, timeout=10, check=False).stdout
        except (OSError, subprocess.SubprocessError):
            output = ""
        found = re.search(r'"IOPlatformUUID"\s*=\s*"([0-9A-Fa-f-]{36})"', output)
        if found:
            return "darwin:" + found.group(1).upper()
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(candidate).read_text().strip()
        except OSError:
            continue
        if re.fullmatch(r"[0-9a-f]{32}", value):
            return "linux:" + value
    return "host:" + socket.gethostname()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _write_new(path: Path, data: bytes) -> None:
    """Create a file that must not exist yet, never through a symlink."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _safe_dir(attempt_dir: Path) -> Path:
    attempt_dir = Path(attempt_dir)
    if attempt_dir.is_symlink() or not attempt_dir.is_dir():
        raise OSError(f"attempt directory is absent or unsafe: {attempt_dir}")
    return attempt_dir


class ControlScope:
    """One dispatching parent's control record for one owner generation."""

    def __init__(self, attempt_dir: Path, generation: int, *, attempt_id: str, cancel_supported: bool) -> None:
        self.attempt_dir = _safe_dir(attempt_dir)
        self.generation = generation
        self.attempt_id = attempt_id
        self.cancel_supported = cancel_supported
        self.path = self.attempt_dir / f"control-g{generation}.json"
        self.groups_path = self.attempt_dir / f"control-g{generation}.groups.jsonl"
        self.closed_path = self.attempt_dir / f"control-g{generation}.closed"

    def open(self) -> None:
        pid = os.getpid()
        record = {"schema_version": 1, "attempt_id": self.attempt_id, "owner_generation": self.generation,
                  "pid": pid, "start_time": start_time(pid), "machine_id": machine_id(),
                  "host": socket.gethostname(), "cancel_supported": self.cancel_supported, "created_at": _now()}
        _write_new(self.path, (json.dumps(record, sort_keys=True) + "\n").encode())

    def register(self, pgid: int, kind: str) -> None:
        """Append one started process group with its leader's start time, read now."""
        if kind not in GROUP_KINDS or type(pgid) is not int or pgid <= 1:
            raise ValueError("process group registration is invalid")
        line = {"pgid": pgid, "leader_start": start_time(pgid), "kind": kind, "at": _now()}
        fd = os.open(self.groups_path, os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "ab") as handle:
            handle.write((json.dumps(line, sort_keys=True) + "\n").encode())
            handle.flush()
            os.fsync(handle.fileno())

    def close(self) -> None:
        if not self.closed_path.exists():
            _write_new(self.closed_path, (json.dumps({"closed_at": _now()}) + "\n").encode())


_CURRENT: ControlScope | None = None


def current() -> ControlScope | None:
    """The control scope of the dispatching parent in this process, if any."""
    return _CURRENT


@contextmanager
def control_scope(attempt_dir: Path, generation: int, *, attempt_id: str,
                  cancel_supported: bool = False) -> Iterator[ControlScope]:
    """Write the control record, expose it to the adapters, and mark it closed at exit."""
    global _CURRENT
    if _CURRENT is not None:
        raise RuntimeError("a delivery control scope is already open in this process")
    scope = ControlScope(attempt_dir, generation, attempt_id=attempt_id, cancel_supported=cancel_supported)
    scope.open()
    _CURRENT = scope
    try:
        yield scope
    finally:
        _CURRENT = None
        scope.close()


def register_group(pgid: int, kind: str) -> None:
    """Register a group with the open scope; a no-op outside one (used by test stubs)."""
    scope = current()
    if scope is not None:
        scope.register(pgid, kind)


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def records(attempt_dir: Path) -> list[dict[str, Any]]:
    """Every control record of an attempt, oldest generation first, with its groups."""
    attempt_dir = Path(attempt_dir)
    if attempt_dir.is_symlink() or not attempt_dir.is_dir():
        return []
    found = []
    for path in attempt_dir.iterdir():
        match = _CONTROL_NAME.match(path.name)
        record = _read_json(path) if match else None
        if not isinstance(record, dict) or record.get("owner_generation") != int(match.group(1)):
            continue
        groups: list[dict[str, Any]] = []
        groups_path = attempt_dir / f"control-g{match.group(1)}.groups.jsonl"
        if groups_path.is_file() and not groups_path.is_symlink():
            for line in groups_path.read_text(errors="replace").splitlines():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict) and type(item.get("pgid")) is int and item.get("kind") in GROUP_KINDS:
                    groups.append(item)
        closed_path = attempt_dir / f"control-g{match.group(1)}.closed"
        found.append({**record, "groups": groups, "closed": closed_path.exists()})
    return sorted(found, key=lambda item: item["owner_generation"])


def parent_live(record: dict[str, Any]) -> str:
    """``live``, ``closed``, ``dead``, ``mismatch`` (pid reused), or ``foreign`` (another machine)."""
    if record.get("machine_id") != machine_id():
        return "foreign"
    if record.get("closed"):
        return "closed"
    pid = record.get("pid")
    if type(pid) is not int or pid <= 0 or not pid_alive(pid):
        return "dead"
    current_start = start_time(pid)
    if current_start is None:
        return "dead"
    return "live" if current_start == record.get("start_time") else "mismatch"


def group_alive(group: dict[str, Any]) -> bool:
    """Whether a recorded group still has its original leader or a member that started after it."""
    leader = group.get("pgid")
    if type(leader) is not int or leader <= 1:
        return False
    if start_time(leader) is not None:
        return start_time(leader) == group.get("leader_start")
    return bool(_members(leader, group.get("leader_start")))


def _members(pgid: int, leader_start: Any) -> list[int]:
    """This user's pids still in ``pgid`` that started at or after the recorded leader."""
    try:
        listing = subprocess.run(["ps", "-A", "-o", "pid=,pgid=,uid="], capture_output=True, text=True,
                                 timeout=10, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    uid, members = os.getuid(), []
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            continue
        pid, group, owner = (int(part) for part in parts)
        if group == pgid and owner == uid and pid != os.getpid() and started_at_or_after(start_time(pid), leader_start):
            members.append(pid)
    return members


def reap(attempt_dir: Path) -> list[dict[str, Any]]:
    """Kill every surviving recorded group of every generation; report what was done.

    A leader still alive with its recorded start time: its whole group is
    killed. A leader that is gone: only this user's members of that pgid that
    started at or after the recorded leader are killed, so a reused pgid is
    never hit. Anything else is reported and never signalled.
    """
    report = []
    own_group = os.getpgrp()
    for record in records(attempt_dir):
        for group in record["groups"]:
            pgid, leader_start = group["pgid"], group.get("leader_start")
            entry = {"owner_generation": record["owner_generation"], "pgid": pgid, "kind": group["kind"]}
            if pgid == own_group or pgid <= 1 or _start_key(leader_start) is None:
                report.append({**entry, "action": "skipped_unverifiable"})
                continue
            current_start = start_time(pgid)
            if current_start is not None:
                if current_start != leader_start:
                    report.append({**entry, "action": "skipped_identity_mismatch"})
                    continue
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    report.append({**entry, "action": "killed_group"})
                except ProcessLookupError:
                    report.append({**entry, "action": "gone"})
                continue
            killed = []
            for pid in _members(pgid, leader_start):
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed.append(pid)
                except ProcessLookupError:
                    pass
            report.append({**entry, "action": "killed_members" if killed else "gone", "members": killed})
    return report
