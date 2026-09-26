"""The single parser for a Magentic manager's progress ledger reply (ADR 0018).

The runner and Flow both classify a progress reply with this module, so the
runner's decision (hand MAF a canonical object, or make it retry) and Flow's
ledger and receipt evidence always agree. Standard library only: ``cli``
loads this file by path, and the release install has no MAF.

Candidate extraction copies ``_extract_json`` from
``agent_framework_orchestrations==1.2.0`` (fenced block, else the first
balanced object, plus its ``True``/``False``/``None`` variant). MAF's final
``ast.literal_eval`` fallback is deliberately omitted: a Python-literal reply
is retried instead. The only repair is escaping a backslash that does not
start a valid JSON escape.
"""

from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

LEDGER_ITEMS = ("is_request_satisfied", "is_in_loop", "is_progress_being_made",
                "next_speaker", "instruction_or_question")
# Contains no "{", so MAF's _extract_json always rejects it and retries.
UNPARSABLE_SENTINEL = "flow: progress reply was not valid JSON"
_FENCE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_HEX = frozenset("0123456789abcdefABCDEF")


class ProgressParse(NamedTuple):
    value: dict[str, Any] | None
    repaired: bool
    canonical: str | None


def extract_candidate(text: str) -> str:
    fence = _FENCE.search(text)
    if fence:
        return fence.group(1)
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unbalanced JSON braces")


def repair_escapes(candidate: str) -> str:
    """Escape each backslash that does not begin a valid JSON escape."""
    out = []
    index = 0
    while index < len(candidate):
        char = candidate[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        following = candidate[index + 1:index + 2]
        if following and following in '"\\/bfnrt':
            out.append(candidate[index:index + 2])
            index += 2
        elif following == "u" and len(candidate) >= index + 6 and set(candidate[index + 2:index + 6]) <= _HEX:
            out.append(candidate[index:index + 6])
            index += 6
        else:
            out.append("\\\\")
            index += 1
    return "".join(out)


def _loads(candidate: str) -> dict[str, Any] | None:
    for attempt in (candidate, candidate.replace("True", "true").replace("False", "false").replace("None", "null")):
        try:
            value = json.loads(attempt)
        except (ValueError, RecursionError):
            # A deeply nested reply fits the size cap but not the decoder's stack;
            # it is unparsable, never an exception that could strand a paid call.
            continue
        if isinstance(value, dict):
            return value
    return None


def well_shaped(value: dict[str, Any]) -> bool:
    """MAF's progress model needs every ledger item as an object with an answer."""
    return all(isinstance(value.get(name), dict) and "answer" in value[name] for name in LEDGER_ITEMS)


def parse_progress(text: str) -> ProgressParse:
    try:
        candidate = extract_candidate(text)
    except ValueError:
        return ProgressParse(None, False, None)
    repaired = False
    value = _loads(candidate)
    if value is None:
        fixed = repair_escapes(candidate)
        if fixed != candidate:
            value = _loads(fixed)
            repaired = value is not None
    if value is None or not well_shaped(value):
        return ProgressParse(None, False, None)
    try:
        canonical = json.dumps(value, ensure_ascii=False)
    except (ValueError, RecursionError):
        return ProgressParse(None, False, None)
    # MAF re-extracts the canonical text with the same rules. Re-serializing can
    # turn an escaped fence inside a string into a literal one that MAF would
    # extract instead, so the round trip must give back the same object.
    try:
        if _loads(extract_candidate(canonical)) != value:
            return ProgressParse(None, False, None)
    except ValueError:
        return ProgressParse(None, False, None)
    return ProgressParse(value, repaired, canonical)


def classify(text: str) -> str:
    """``parsed``, ``repaired`` or ``unparsable``, for Flow's ledger and receipt."""
    parsed = parse_progress(text)
    if parsed.value is None:
        return "unparsable"
    return "repaired" if parsed.repaired else "parsed"
