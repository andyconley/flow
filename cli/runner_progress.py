"""Load the manager progress parser from ``runtime/maf_runner/progress_parse.py``.

Flow classifies observed progress replies with the runner's own parser, so
its ledger events and receipt block agree with what the runner handed MAF
(ADR 0018). Loaded by location, as ``runner_limits`` is.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

PARSER_PATH = Path(__file__).resolve().parents[1] / "runtime" / "maf_runner" / "progress_parse.py"

_spec = importlib.util.spec_from_file_location("flow_runner_progress", PARSER_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"runner progress parser not found: {PARSER_PATH}")
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

classify = _module.classify
parse_progress = _module.parse_progress
UNPARSABLE_SENTINEL: str = _module.UNPARSABLE_SENTINEL

if not callable(classify) or not callable(parse_progress) or not isinstance(UNPARSABLE_SENTINEL, str):
    raise ImportError("runner progress parser has an unexpected shape")
