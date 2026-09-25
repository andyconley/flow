"""The optional MAF interpreter for MAF-gated tests, taken only from FLOW_MAF_PYTHON.

There is no fallback path: an absent interpreter skips visibly, naming the
variable, so the local merge gate cannot pass on a stale temporary location.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

MAF_PYTHON = os.environ.get("FLOW_MAF_PYTHON", "")
MAF_AVAILABLE = bool(MAF_PYTHON) and Path(MAF_PYTHON).is_file()
SKIP_REASON = "set FLOW_MAF_PYTHON to an interpreter built from runtime/maf_runner/requirements.txt"


def requires_maf(target):
    """Skip a MAF-gated test class or method unless FLOW_MAF_PYTHON is usable."""
    return unittest.skipUnless(MAF_AVAILABLE, SKIP_REASON)(target)
