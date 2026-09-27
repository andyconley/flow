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
import subprocess
import sys
import tempfile
import time
import venv
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
SUPPORTED_PROTOCOLS = [5, 6, 7, 8]
READY = "ready"
UNREADY_STATES = {
    "not_installed", "interpreter_missing", "identity_mismatch", "lock_mismatch",
    "package_missing", "version_mismatch", "runner_import_failed",
    "protocol_incompatible", "probe_timeout",
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


def runtime_root(home: Path | None = None) -> Path:
    return (home or FLOW_HOME) / "runtimes" / "maf"


def pointer_path(home: Path | None = None) -> Path:
    return runtime_root(home) / "current.json"


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
    return (
        "import json,sys; import agent_framework,agent_framework_orchestrations; from importlib.metadata import version; "
        "from runtime.maf_runner import delivery_lead; "
        "print(json.dumps({'executable':sys.executable,'python':list(sys.version_info[:3]),"
        "'packages':{n:version(n) for n in " + repr(sorted(RESOLVED_PACKAGES)) + "},"
        "'protocols':[5,6,7,8]}))"
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
    identity = {"schema_version": 1, "interpreter": str(binary.resolve()), "python": observed["python"],
                "packages": packages, "lock_digest": lock_digest(root), "protocols": SUPPORTED_PROTOCOLS}
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
    # An explicitly selected interpreter is a verified reusable runtime, not
    # an ambient fallback.  This supports offline installs where an operator
    # has already built the locked environment, while the default path below
    # remains the staged managed-environment provisioning transaction.
    supplied = os.environ.get("FLOW_MAF_PYTHON")
    if supplied:
        checked = probe(python_path=supplied, source_root=root)
        if checked["state"] != READY:
            raise MafRuntimeUnready(checked)
        pointer_path(home).parent.mkdir(parents=True, exist_ok=True)
        temp = pointer_path(home).with_suffix(".tmp")
        temp.write_text(json.dumps({"schema_version": 1, "interpreter": checked["identity"]["interpreter"],
                                    "identity": checked["identity"], "installed_at": int(time.time())},
                                   sort_keys=True) + "\n")
        os.replace(temp, pointer_path(home))
        return checked
    base = base_python or os.environ.get("FLOW_MAF_BASE_PYTHON") or sys.executable
    try:
        version_out = subprocess.run([base, "-c", "import sys; print('.'.join(map(str,sys.version_info[:3])))"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise MafRuntimeUnready(_result("interpreter_missing", source="installer", remedy="select a usable Python interpreter", detail=str(exc))) from exc
    key = hashlib.sha256(f"{lock_digest(root)}:{Path(base).resolve()}:{version_out}:{sys.platform}".encode()).hexdigest()
    target = runtime_root(home) / key
    current = _load_pointer(home)
    if target.is_dir():
        candidate = str(target / "bin" / "python")
        # A temporary pointer lets probe enforce the exact immutable identity.
        identity_probe = probe(python_path=candidate, source_root=root)
        if identity_probe["state"] == READY:
            pointer_path(home).parent.mkdir(parents=True, exist_ok=True)
            temp = pointer_path(home).with_suffix(".tmp")
            temp.write_text(json.dumps({"schema_version": 1, "interpreter": candidate, "identity": identity_probe["identity"], "installed_at": int(time.time())}, sort_keys=True) + "\n")
            os.replace(temp, pointer_path(home))
            return identity_probe
    runtime_root(home).parent.mkdir(parents=True, exist_ok=True)
    stage: Path | None = Path(tempfile.mkdtemp(prefix="maf-stage-", dir=runtime_root(home).parent))
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(stage)
        interpreter = stage / "bin" / "python"
        install = subprocess.run([str(interpreter), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-r", str(root / "runtime" / "maf_runner" / "requirements.lock")], capture_output=True, text=True, timeout=300, check=False)
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
        pointer_path(home).parent.mkdir(parents=True, exist_ok=True)
        temp = pointer_path(home).with_suffix(".tmp")
        temp.write_text(json.dumps({"schema_version": 1, "interpreter": str(target / "bin" / "python"), "identity": checked["identity"], "installed_at": int(time.time())}, sort_keys=True) + "\n")
        os.replace(temp, pointer_path(home))
        return checked
    finally:
        if stage is not None and stage.exists():
            import shutil
            shutil.rmtree(stage, ignore_errors=True)
