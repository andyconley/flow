"""Managed, credential-free readiness checks for Flow's optional MAF runtime.

This module is deliberately below the delivery gateway: checking an optional
runtime must never import MAF into the normal Flow interpreter or mutate a
project.  A managed selection is a small immutable JSON pointer under
``~/.flow/runtimes/maf``; the environment it names is addressed by the digest
recorded in that pointer.
"""

from __future__ import annotations

import hashlib
import json
import os
import fcntl
import platform
import sysconfig
import subprocess
import sys
import tempfile
import time
import uuid
import venv
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from paths import FLOW_HOME

PINNED_PACKAGES = {
    "agent-framework-core": "1.19.0",
    "agent-framework-orchestrations": "1.2.0",
}
RESOLVED_PACKAGES = {
    "agent-framework-core": "1.19.0", "agent-framework-orchestrations": "1.2.0",
    "annotated-types": "0.8.0", "msgspec": "0.21.1", "opentelemetry-api": "1.45.0",
    "pydantic": "2.13.5", "pydantic-core": "2.46.5", "python-dotenv": "1.2.3",
    "pyyaml": "6.0.3", "typing-inspection": "0.4.4", "typing-extensions": "4.16.0",
}
# These are the protocols whose readiness depends on the pinned MAF package
# surface. Protocol v9 uses the same managed interpreter, but its
# credentialless selection path returns before importing MAF orchestration.
# Keep this package-compatibility identity stable across that additive
# transport change so the preceding release can transactionally activate the
# new source with its already-loaded readiness probe.
SUPPORTED_PROTOCOLS = [5, 6, 7, 8]
READY = "ready"
UNREADY_STATES = {
    "not_installed", "interpreter_missing", "identity_mismatch", "lock_mismatch",
    "package_missing", "version_mismatch", "runner_import_failed",
    "protocol_incompatible", "probe_timeout", "unsupported_runtime",
}


class MafRuntimeUnready(RuntimeError):
    """A delivery-safe error carrying a stable, public diagnostic."""

    reason = "maf_runtime_unready"

    def __init__(self, diagnostic: dict[str, Any]):
        self.diagnostic = diagnostic
        super().__init__(f"{diagnostic['state']}: {diagnostic['remedy']}")


def _source_root() -> Path:
    return Path(__file__).resolve().parents[1]


def lock_digest(source_root: Path | None = None) -> str:
    path = (source_root or _source_root()) / "runtime" / "maf_runner" / "requirements.lock"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def runner_digest(source_root: Path | None = None) -> str:
    root = source_root or _source_root()
    return hashlib.sha256((root / "runtime" / "maf_runner" / "delivery_lead.py").read_bytes()).hexdigest()


def runtime_root(home: Path | None = None) -> Path:
    return (home or FLOW_HOME) / "runtimes" / "maf"


def pointer_path(home: Path | None = None) -> Path:
    return runtime_root(home) / "current.json"


@contextmanager
def _provision_lock(home: Path):
    """Serialize pointer and digest-directory changes across Flow processes."""
    root = runtime_root(home)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".provision.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        stat = os.fstat(fd)
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise MafRuntimeUnready(_result("identity_mismatch", source="installer",
                                            remedy="repair the managed MAF runtime lock"))
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _write_pointer(home: Path, interpreter: str, identity: dict[str, Any]) -> None:
    path = pointer_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump({"schema_version": 1, "interpreter": interpreter, "identity": identity,
                       "installed_at": int(time.time())}, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _result(state: str, *, source: str, remedy: str, detail: str = "", identity: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"state": state, "source": source, "remedy": remedy, "detail": detail}
    if identity is not None:
        result["identity"] = identity
    return result


def _load_pointer(home: Path | None = None) -> dict[str, Any] | None:
    path = pointer_path(home)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _probe_command() -> str:
    # Kept as a single, data-only probe: no MAF workflow, adapter or network
    # import is permitted before the gateway creates an attempt.
    integrity = (
        "import base64,csv,hashlib,importlib.metadata as md,json\n"
        "records={}\n"
        "for name in " + repr(sorted(RESOLVED_PACKAGES)) + ":\n"
        " d=md.distribution(name); record=d.locate_file(d._path.name + '/RECORD'); bad=[]\n"
        " with open(record,newline='') as f:\n"
        "  for path,hashed,size in csv.reader(f):\n"
        "   if hashed:\n"
        "    algorithm,encoded=hashed.split('=',1); actual=hashlib.new(algorithm,d.locate_file(path).read_bytes()).digest(); expected=base64.urlsafe_b64decode(encoded + '='*(-len(encoded)%4))\n"
        "    if actual != expected: bad.append(path)\n"
        " records[name]={'record':hashlib.sha256(record.read_bytes()).hexdigest(),'bad':bad}\n"
    )
    return (
        "import json,sys,platform,sysconfig; from agent_framework import AgentResponse,Executor,FileCheckpointStorage,Message,WorkflowContext,handler,response_handler; "
        "from agent_framework_orchestrations import GroupChatParticipantMessage,GroupChatRequestMessage,GroupChatResponseMessage,MagenticBuilder,StandardMagenticManager; "
        "from importlib.metadata import version; "
        "from runtime.maf_runner import delivery_lead; exec(" + repr(integrity) + "); "
        "print(json.dumps({'executable':sys.executable,'python':list(sys.version_info[:3]),"
        "'packages':{n:version(n) for n in " + repr(sorted(RESOLVED_PACKAGES)) + "},"
        "'protocols':delivery_lead.SUPPORTED_PROTOCOLS,'machine':platform.machine(),'implementation':platform.python_implementation(),'soabi':sysconfig.get_config_var('SOABI'),'records':records}))"
    )


def probe(*, python_path: str | None = None, home: Path | None = None,
          source_root: Path | None = None, timeout_s: float = 10) -> dict[str, Any]:
    """Return a stable, side-effect-free runtime readiness record.

    An override is authoritative.  In particular, a bad ``FLOW_MAF_PYTHON``
    is not allowed to fall back to the managed selection or ``sys.executable``.
    """
    override = python_path or os.environ.get("FLOW_MAF_PYTHON")
    source = "override" if override else "managed"
    pointer = None if override else _load_pointer(home)
    executable = override or (pointer or {}).get("interpreter")
    if not isinstance(executable, str) or not executable:
        return _result("not_installed", source=source,
                       remedy="run `flow runtime install-maf` or set FLOW_MAF_PYTHON to a verified interpreter")
    binary = Path(executable)
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return _result("interpreter_missing", source=source,
                       remedy="repair the managed MAF runtime or set FLOW_MAF_PYTHON to an executable", detail=executable)
    root = source_root or _source_root()
    try:
        completed = subprocess.run([str(binary), "-c", _probe_command()], cwd=root,
                                   env={"PYTHONPATH": str(root), "PYTHONDONTWRITEBYTECODE": "1"},
                                   capture_output=True, text=True, timeout=timeout_s, check=False)
    except subprocess.TimeoutExpired:
        return _result("probe_timeout", source=source, remedy="rerun `flow runtime install-maf` and inspect the interpreter")
    except OSError as exc:
        return _result("interpreter_missing", source=source, remedy="repair the managed MAF runtime", detail=str(exc))
    if completed.returncode:
        text = (completed.stderr or completed.stdout or "").lower()
        state = "package_missing" if "no module named" in text or "not found" in text else "runner_import_failed"
        return _result(state, source=source, remedy="run `flow runtime install-maf`", detail=(completed.stderr or completed.stdout)[-512:])
    try:
        observed = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return _result("runner_import_failed", source=source, remedy="run `flow runtime install-maf`", detail="probe returned invalid JSON")
    packages = observed.get("packages") if isinstance(observed, dict) else None
    if not isinstance(packages, dict):
        return _result("runner_import_failed", source=source, remedy="run `flow runtime install-maf`")
    if any(packages.get(name) != wanted for name, wanted in RESOLVED_PACKAGES.items()):
        return _result("version_mismatch", source=source, remedy="run `flow runtime install-maf`", detail=json.dumps(packages, sort_keys=True))
    if observed.get("protocols") != SUPPORTED_PROTOCOLS:
        return _result("protocol_incompatible", source=source, remedy="install a Flow-compatible MAF runtime")
    records = observed.get("records")
    if not isinstance(records, dict) or any(not isinstance(item, dict) or item.get("bad") or not item.get("record")
                                            for item in records.values()):
        return _result("identity_mismatch", source=source, remedy="run `flow runtime install-maf`", detail="installed package RECORD integrity failed")
    identity = {"schema_version": 2, "interpreter": str(binary.resolve()), "python": observed["python"],
                "platform": sys.platform, "packages": packages, "lock_digest": lock_digest(root),
                "runner_digest": runner_digest(root), "protocols": observed["protocols"],
                "protocol_digest": hashlib.sha256(json.dumps(observed["protocols"], separators=(",", ":")).encode()).hexdigest(),
                "machine": observed.get("machine"), "implementation": observed.get("implementation"),
                "soabi": observed.get("soabi"), "record_digest": hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    identity["runtime_digest"] = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if pointer and isinstance(pointer.get("identity"), dict) and pointer["identity"].get("lock_digest") != identity["lock_digest"]:
        return _result("lock_mismatch", source=source, remedy="run `flow runtime install-maf`", identity=identity)
    if pointer and pointer.get("identity") != identity:
        return _result("identity_mismatch", source=source, remedy="run `flow runtime install-maf`", identity=identity)
    return _result(READY, source=source, remedy="none", identity=identity)


def require_ready(**kwargs: Any) -> dict[str, Any]:
    result = probe(**kwargs)
    if result["state"] != READY:
        raise MafRuntimeUnready(result)
    return result["identity"]


def provision(*, home: Path | None = None, source_root: Path | None = None,
              base_python: str | None = None) -> dict[str, Any]:
    """Stage, prove, then atomically select a digest-addressed venv.

    The old pointer is deliberately untouched until the new environment passes
    the same probe that dispatch uses.  Existing exact identities are reused.
    """
    root = source_root or _source_root()
    home = home or FLOW_HOME
    # FLOW_MAF_PYTHON is an execution/readiness override only.  It must never
    # become the managed pointer: provisioning always produces a digest-
    # addressed environment beneath FLOW_HOME.
    base = base_python or os.environ.get("FLOW_MAF_BASE_PYTHON") or sys.executable
    try:
        version_out = subprocess.run([base, "-c", "import sys; print('.'.join(map(str,sys.version_info[:3])))"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise MafRuntimeUnready(_result("interpreter_missing", source="installer", remedy="select a usable Python interpreter", detail=str(exc))) from exc
    host = subprocess.run([base, "-c", "import platform,sys; print('|'.join((sys.platform,platform.machine(),str(sys.version_info.major),str(sys.version_info.minor))))"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    if host != "darwin|arm64|3|12":
        raise MafRuntimeUnready(_result("unsupported_runtime", source="installer",
                                        remedy="managed MAF wheels currently require macOS arm64 with CPython 3.12", detail=host))
    # The address includes every compatibility input that may change runner
    # behavior; a code/protocol/ABI change always receives a fresh target.
    base_tags = subprocess.run([base, "-c", "import platform,sysconfig; print('|'.join((platform.machine(),platform.python_implementation(),str(sysconfig.get_config_var('SOABI') or ''))))"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    protocol_digest = hashlib.sha256(json.dumps(SUPPORTED_PROTOCOLS, separators=(",", ":")).encode()).hexdigest()
    key = hashlib.sha256(f"{lock_digest(root)}:{runner_digest(root)}:{protocol_digest}:{Path(base).resolve()}:{version_out}:{sys.platform}:{base_tags}".encode()).hexdigest()
    target = runtime_root(home) / key
    # All target validation, staging and pointer changes occur while holding a
    # user-owned advisory lock. A second installer therefore observes either a
    # complete verified target or waits; it never races a shared current.tmp.
    with _provision_lock(home):
      if target.is_dir() and not target.is_symlink():
        candidate = str(target / "bin" / "python")
        identity_probe = probe(python_path=candidate, source_root=root)
        if identity_probe["state"] == READY:
            _write_pointer(home, candidate, identity_probe["identity"])
            return identity_probe
        # A digest directory that does not prove is not reusable. Preserve it
        # for operator inspection, then build a fresh immutable replacement.
        quarantine = target.with_name(f"{target.name}.invalid-{uuid.uuid4().hex}")
        os.replace(target, quarantine)
      elif target.exists() or target.is_symlink():
        quarantine = target.with_name(f"{target.name}.invalid-{uuid.uuid4().hex}")
        os.replace(target, quarantine)
      stage: Path | None = Path(tempfile.mkdtemp(prefix="maf-stage-", dir=runtime_root(home)))
      try:
        venv.EnvBuilder(with_pip=True, clear=True).create(stage)
        interpreter = stage / "bin" / "python"
        command = [str(interpreter), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "--require-hashes"]
        wheelhouse = os.environ.get("FLOW_MAF_WHEELHOUSE")
        if wheelhouse:
            command.extend(["--no-index", "--find-links", wheelhouse])
        command.extend(["-r", str(root / "runtime" / "maf_runner" / "requirements.lock")])
        install = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        if install.returncode:
            raise MafRuntimeUnready(_result("package_missing", source="installer", remedy="check package installation", detail=install.stderr[-512:]))
        checked = probe(python_path=str(interpreter), source_root=root)
        if checked["state"] != READY:
            raise MafRuntimeUnready(checked)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, target)
        stage = None  # ownership moved
        # The interpreter's absolute path participates in its identity, so
        # prove it again after the staged directory receives its immutable
        # address.  Staging-path identity must never become the pointer.
        checked = probe(python_path=str(target / "bin" / "python"), source_root=root)
        if checked["state"] != READY:
            raise MafRuntimeUnready(checked)
        _write_pointer(home, str(target / "bin" / "python"), checked["identity"])
        return checked
      finally:
          if stage is not None and stage.exists():
              import shutil
              shutil.rmtree(stage, ignore_errors=True)
