"""The one comparison of a v8 receipt with the ledger, shared by both seals and verify-receipt (ADR 0020).

Pure: it compares values and never reads the ledger or a file. Each block is
compared in full, rows index by index with exact key sets, so a changed,
added or removed field is a mismatch, not only a changed status.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Receipt blocks copied from the ledger snapshot, and the snapshot key each comes from.
ROW_BLOCKS = {"actions": "actions", "manager_calls": "manager_calls", "replans": "replans",
              "checkpoints": "magentic_checkpoints", "verifier_inputs": "verifier_inputs",
              "verifier_evaluations": "verifier_evaluations", "verifier_usage": "verifier_usage"}
# Receipt blocks the seal derives from the ledger; absent means the ledger has none.
DERIVED_BLOCKS = ("lineage_usage", "expansion", "manager_progress", "token_usage")
_LONG = 200


def expected_blocks(snapshot: dict[str, Any], blocks: dict[str, Any]) -> dict[str, Any]:
    """What a receipt built from ``snapshot`` and the seal ``blocks`` must carry, by receipt key."""
    expected = {key: snapshot.get(source, [] if key != "verifier_usage" else None) for key, source in ROW_BLOCKS.items()}
    expected.update({key: blocks.get(key) for key in DERIVED_BLOCKS})
    return expected


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row_id(item: Any) -> str | None:
    if isinstance(item, dict):
        for key in ("action_id", "call_id", "replan_id", "pending_id", "request_id"):
            if isinstance(item.get(key), str):
                return item[key]
    return None


def _mismatch(block: str, row_id: str | None, path: str, expected: Any, found: Any) -> dict[str, Any]:
    item = {"block": block, "row_id": row_id, "path": path}
    if len(_canonical(expected)) > _LONG or len(_canonical(found)) > _LONG:
        item.update(expected_sha256=hashlib.sha256(_canonical(expected).encode()).hexdigest(),
                    found_sha256=hashlib.sha256(_canonical(found).encode()).hexdigest())
    else:
        item.update(expected=expected, found=found)
    return item


def _diff(block: str, row_id: str | None, path: str, expected: Any, found: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(expected, dict) and isinstance(found, dict):
        if set(expected) != set(found):
            missing, extra = sorted(set(expected) - set(found)), sorted(set(found) - set(expected))
            out.append(_mismatch(block, row_id, path + ".<keys>", {"missing": missing, "extra": extra},
                                 sorted(found)))
            return
        before = len(out)
        for key in sorted(expected):
            _diff(block, row_id, f"{path}.{key}", expected[key], found[key], out)
            if len(out) > before:
                return  # the first differing key path per row is enough to diagnose it
        return
    if isinstance(expected, list) and isinstance(found, list):
        if len(expected) != len(found):
            out.append(_mismatch(block, row_id, path + "[len]", len(expected), len(found)))
        for index, (left, right) in enumerate(zip(expected, found)):
            before = len(out)
            _diff(block, _row_id(left) or row_id, f"{path}[{index}]", left, right, out)
            if len(out) > before:
                return
        return
    if type(expected) is not type(found) or expected != found:
        out.append(_mismatch(block, row_id, path, expected, found))


def compare_receipt_rows(receipt: dict[str, Any], expected: dict[str, Any], *, blocks: Any) -> list[dict[str, Any]]:
    """Every mismatch between ``receipt`` and ``expected`` over ``blocks``: row id, key path, both values."""
    mismatches: list[dict[str, Any]] = []
    for block in blocks:
        want = expected.get(block)
        have = receipt.get(block) if isinstance(receipt, dict) else None
        if block in DERIVED_BLOCKS and want is None:
            if have is not None:
                mismatches.append(_mismatch(block, None, block, None, have))
            continue
        if have is None and want is not None:
            mismatches.append(_mismatch(block, None, block, want, None))
            continue
        _diff(block, None, block, want, have, mismatches)
    return mismatches


def describe(mismatch: dict[str, Any]) -> str:
    """One line naming the block, the row, the key path and both values (or digests)."""
    where = f"{mismatch['block']} {mismatch['row_id'] or '-'} {mismatch['path']}"
    if "expected_sha256" in mismatch:
        return f"{where}: expected sha256 {mismatch['expected_sha256'][:16]}, found {mismatch['found_sha256'][:16]}"
    return f"{where}: expected {_canonical(mismatch['expected'])[:120]}, found {_canonical(mismatch['found'])[:120]}"
