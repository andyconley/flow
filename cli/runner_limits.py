"""Load the runner ceilings from ``runtime/maf_runner/limits.py``.

``cli`` modules run without the repository root on ``sys.path``, so the file
is loaded by location. Both the source tree and the release install keep
``runtime/`` beside ``cli/``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

LIMITS_PATH = Path(__file__).resolve().parents[1] / "runtime" / "maf_runner" / "limits.py"

_spec = importlib.util.spec_from_file_location("flow_runner_limits", LIMITS_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"runner limits not found: {LIMITS_PATH}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

MAX_MANAGER_CALLS: int = _module.MAX_MANAGER_CALLS
MAX_MANAGER_ROUNDS: int = _module.MAX_MANAGER_ROUNDS
MAX_ACTIONS: int = _module.MAX_ACTIONS
MAX_VERIFIER_CALLS: int = _module.MAX_VERIFIER_CALLS
MAX_CONCURRENT: int = _module.MAX_CONCURRENT
MAX_REPLANS: int = _module.MAX_REPLANS
