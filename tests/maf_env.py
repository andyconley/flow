"""The optional MAF interpreter for MAF-gated tests, taken only from FLOW_MAF_PYTHON.

There is no fallback path: an absent interpreter skips visibly, naming the
variable, so the local merge gate cannot pass on a stale temporary location.
"""

from __future__ import annotations

import copy
import functools
import os
import sys
import unittest
from pathlib import Path
from typing import Any

MAF_PYTHON = os.environ.get("FLOW_MAF_PYTHON", "")
MAF_AVAILABLE = bool(MAF_PYTHON) and Path(MAF_PYTHON).is_file()
SKIP_REASON = "set FLOW_MAF_PYTHON to an interpreter built from runtime/maf_runner/requirements.txt"


def requires_maf(target):
    """Skip a MAF-gated test class or method unless FLOW_MAF_PYTHON is usable."""
    return unittest.skipUnless(MAF_AVAILABLE, SKIP_REASON)(target)


def managed_wheelhouse() -> Path:
    """Configurable offline wheel source for managed-runtime acceptance tests."""
    override = os.environ.get("FLOW_TEST_MAF_WHEELHOUSE")
    if override:
        return Path(override)
    lock = Path(__file__).resolve().parents[1] / "runtime/maf_runner/requirements.lock"
    pins = [line.split(" --hash", 1)[0] for line in lock.read_text().splitlines()
            if line.strip() and not line.startswith("#")]
    for candidate in (Path("/private") / "tmp" / "flow-maf-wheelhouse", Path("/private") / "tmp" / "flow-maf-poc-wheelhouse"):
        wheels = [wheel.name.lower().replace("-", "_") for wheel in candidate.glob("*.whl")]
        if all(any(name.startswith(pin.replace("==", "_").replace("-", "_").lower() + "_")
                   for name in wheels) for pin in pins):
            return candidate
    return Path("/private") / "tmp" / "flow-maf-wheelhouse-unavailable"


# A stand-in for fixtures whose child never checks the sealed runtime.
FAKE_RUNTIME_IDENTITY: dict[str, Any] = {
    "schema_version": 1, "interpreter": "/test/maf-python", "python": [3, 12, 0],
    "packages": {"agent-framework-core": "1.19.0", "agent-framework-orchestrations": "1.2.0"},
    "lock_digest": "a" * 64, "protocols": [5, 6, 7, 8], "runtime_digest": "b" * 64,
}


@functools.lru_cache(maxsize=None)
def _probed_identity(interpreter: str) -> dict[str, Any] | None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
    try:
        from maf_runtime import probe
    finally:
        sys.path.pop(0)
    result = probe(python_path=interpreter)
    return result["identity"] if result["state"] == "ready" else None


def sealed_runtime_identity() -> dict[str, Any]:
    """The runtime identity a fixture seals into its envelope.

    A real MAF child computes its own identity and must match the sealed one,
    so when FLOW_MAF_PYTHON is a ready runtime the fixture seals its probed
    identity. Otherwise the fake stands in, and MAF-gated tests skip.
    """
    identity = _probed_identity(MAF_PYTHON) if MAF_AVAILABLE else None
    return copy.deepcopy(identity if identity is not None else FAKE_RUNTIME_IDENTITY)
