"""Pure Gate 0/1 checks for expertise-admission campaign evidence.

This deliberately lives in ``tests`` until the production CLI owns the command
surface.  It makes the protocol executable without authoring campaign task
text, installing a model, or creating score rows.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


V1_MANIFEST_SHA256 = "d2f42382c7c52bc51227596ceb37e58dc5a5f45e77b1edb026441270afa978b0"
V1_RESULTS_SHA256 = "9101f9c2902ffb34b5077f19c126c736e37e6227896e9438a5b3b9e68d2dee57"
PRIMARY_COUNTS = {"applicable": 10, "plausible-inapplicable": 10, "true-no-match": 6, "integrity": 4}
PROHIBITED_ON_PAUSE = ("fixture_authoring", "embedding", "ranking", "scoring", "selection", "release")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")


class ProtocolError(ValueError):
    """A frozen evidence protocol requirement was not met."""


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_immutable_v1(evidence_root: Path) -> dict[str, str]:
    """Read retained v1 only and reject any digest drift."""
    manifest = evidence_root / "manifest.json"
    results = evidence_root / "results.json"
    actual = {"manifest_sha256": _digest(manifest), "results_sha256": _digest(results)}
    expected = {"manifest_sha256": V1_MANIFEST_SHA256, "results_sha256": V1_RESULTS_SHA256}
    if actual != expected:
        raise ProtocolError(f"immutable evaluation-v1 digest mismatch: expected {expected}, got {actual}")
    return actual


def validate_no_v1_reuse(candidate_manifest: dict[str, Any], v1_manifest: dict[str, Any]) -> None:
    """Reject candidate fixture IDs or normalized task digests reused from v1."""
    candidate = candidate_manifest.get("fixtures", [])
    prior = v1_manifest.get("fixtures", [])
    prior_ids = {row.get("id") for row in prior}
    prior_tasks = {fingerprint_task(str(row.get("task", row.get("query", "")))) for row in prior}
    for row in candidate:
        _require(row.get("id") not in prior_ids, f"candidate reuses v1 fixture id {row.get('id')}")
        task = str(row.get("task", row.get("query", "")))
        _require(fingerprint_task(task) not in prior_tasks, f"candidate reuses a v1 task digest for {row.get('id')}")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


def validate_feasibility(record: dict[str, Any]) -> None:
    """Validate either the complete go record or the durable stop record."""
    state = record.get("state")
    _require(state in {"feasible", "paused_for_engineer_decision"}, "invalid feasibility state")
    _require(isinstance(record.get("corpus_digest"), str) and len(record["corpus_digest"]) == 64,
             "feasibility record needs corpus_digest")
    _require(isinstance(record.get("assignment_digest"), str) and len(record["assignment_digest"]) == 64,
             "feasibility record needs assignment_digest")
    if state == "paused_for_engineer_decision":
        _require(record.get("reason") in {"corpus_gap", "staffing_gap", "environment_gap"},
                 "paused result needs a recognized reason")
        _require(bool(record.get("blocking_checks")), "paused result needs blocking checks")
        _require(record.get("automatic_retrieval") == "disabled", "paused result must disable automatic retrieval")
        actions = record.get("prohibited_next_actions")
        _require(isinstance(actions, list) and set(PROHIBITED_ON_PAUSE).issubset(actions),
                 "paused result must prohibit every downstream campaign action")
        _require(bool(record.get("gap")) and bool(record.get("remedies")),
                 "paused result needs exact gap and remedies")
        return

    _require(record.get("automatic_retrieval") == "disabled", "feasibility never enables retrieval")
    _require(record.get("distinct_task_slots") == 60, "feasibility requires exactly 60 task slots")
    _require(len(record.get("eligible_roles", [])) >= 6, "feasibility requires six eligible roles")
    _require(bool(record.get("assignments")), "feasibility needs independent assignments")
    _require(bool(record.get("environments")), "feasibility needs environment inventory")


def validate_fixture_manifest(manifest: dict[str, Any]) -> None:
    """Check the frozen structural and independence constraints of one split."""
    fixtures = manifest.get("fixtures")
    _require(isinstance(fixtures, list) and len(fixtures) == 30, "manifest needs exactly 30 fixtures")
    ids = [row.get("id") for row in fixtures]
    _require(all(isinstance(value, str) and value for value in ids), "every fixture needs an id")
    _require(len(ids) == len(set(ids)), "fixture IDs must be distinct")
    counts = Counter(row.get("primary_class") for row in fixtures)
    _require(dict(counts) == PRIMARY_COUNTS, f"primary classes must equal {PRIMARY_COUNTS}")
    roles = manifest.get("eligible_roles")
    _require(isinstance(roles, list) and len(set(roles)) >= 6, "manifest needs six eligible roles")
    role_counts = Counter(row.get("role") for row in fixtures)
    _require(all(role_counts[role] >= 2 for role in roles), "each eligible role needs two fixtures")
    positives = [row for row in fixtures if row.get("primary_class") == "applicable" and row.get("semantic_no_overlap")]
    _require(len(positives) >= 3, "manifest needs three semantic no-overlap positives")
    _require(len({row.get("query_author") for row in positives}) >= 3,
             "semantic no-overlap positives must be independently authored")
    plausible = [row for row in fixtures if row.get("primary_class") == "plausible-inapplicable"]
    paths = Counter(row.get("plausible_path") for row in plausible)
    _require(paths == {"admission-rejected": 5, "controlled-delivery": 5},
             "plausible fixtures need five rejected and five controlled-delivery paths")
    pairs = manifest.get("trigger_pairs")
    _require(isinstance(pairs, list) and len(pairs) >= 4, "manifest needs four trigger pairs")
    pair_roles = {role for pair in pairs for role in pair.get("roles", [])}
    _require("support-lead" in pair_roles and len(pair_roles) >= 2,
             "trigger pairs must span support-lead and another role")
    for pair in pairs:
        _require(pair.get("applicable_id") in ids and pair.get("plausible_id") in ids,
                 "trigger pair must cite fixture IDs")
        _require(pair.get("one_fact_difference") is True, "trigger pair must attest one fact difference")


def normalize_task(value: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(value.lower()))


def fingerprint_task(value: str) -> str:
    return hashlib.sha256(normalize_task(value).encode()).hexdigest()


def fingerprint_identifiers(identifiers: Iterable[str]) -> str:
    joined = "\n".join(sorted(set(identifiers)))
    return hashlib.sha256(joined.encode()).hexdigest()


def lexical_similarity(left: str, right: str) -> float:
    left_tokens = set(normalize_task(left).split())
    right_tokens = set(normalize_task(right).split())
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def split_independence(candidate: Iterable[dict[str, Any]], references: Iterable[dict[str, Any]], threshold: float = 0.7) -> dict[str, Any]:
    """Return a blind-review queue without labels, target IDs, or score data."""
    _require(0 < threshold <= 1, "lexical threshold must be within (0, 1]")
    flags: list[dict[str, Any]] = []
    for task in candidate:
        task_text = task["task"]
        task_fp = fingerprint_task(task_text)
        id_fp = fingerprint_identifiers(task.get("identifiers", []))
        for reference in references:
            categories: list[str] = []
            if task_fp == fingerprint_task(reference["task"]):
                categories.append("exact_task")
            if id_fp == fingerprint_identifiers(reference.get("identifiers", [])) and task.get("identifiers"):
                categories.append("identifier_overlap")
            similarity = lexical_similarity(task_text, reference["task"])
            if similarity >= threshold and "exact_task" not in categories:
                categories.append("lexical_similarity")
            if categories:
                flags.append({
                    "candidate_id": task["id"], "reference_id": reference["id"],
                    "categories": categories, "similarity": similarity,
                    "candidate_task_digest": task_fp, "reference_task_digest": fingerprint_task(reference["task"]),
                })
    return {
        "schema_version": 1,
        "normalizer": "ascii-token-lower-v1",
        "task_fields": ["task"],
        "lexical_method": "jaccard-token-set-v1",
        "lexical_threshold": threshold,
        "flags": flags,
    }


def read_json(path: Path) -> dict[str, Any]:
    """Small deterministic helper for future CLI adapters."""
    return json.loads(path.read_text())
