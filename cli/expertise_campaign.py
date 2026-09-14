"""Frozen-campaign scoring and lexicographic expertise-gate selection."""
from __future__ import annotations

from collections import Counter
from typing import Callable

from expertise_model import canonical_json, digest


class ExpertiseCampaignError(ValueError):
    pass


def safe_stage_result(outcome: dict) -> dict:
    """Retain decision evidence without query or delivered entry prose."""
    return {
        "request_id": outcome["request_id"],
        "role": outcome["role"],
        "state": outcome["state"],
        "cause": outcome["cause"],
        "eligibility": outcome["eligibility"],
        "ranking": outcome["ranking"],
        "admission": outcome["admission"],
        "delivery": {key: value for key, value in outcome["delivery"].items() if key != "entries"},
    }


def _ids(rows: list[dict], key: str = "entry_id") -> list[str]:
    return [row[key] for row in rows if isinstance(row, dict) and isinstance(row.get(key), str)]


def _disposition_evidence(value: dict, delivered: list[str], expected: object) -> bool:
    """Read either a campaign verdict or a durable disposition plus behavior verdict."""
    if "disposition_record" not in value:
        return (
            value.get("disposition") == expected
            and value.get("behavior_pass") is True
            and value.get("entry_id") in delivered
        )
    record = value.get("disposition_record")
    behavior = value.get("behavior_evaluation")
    if not isinstance(record, dict) or not isinstance(behavior, dict) or record.get("state") != "observed":
        return False
    rows = record.get("entries")
    if not isinstance(rows, list) or [row.get("entry_id") for row in rows if isinstance(row, dict)] != delivered:
        return False
    target = behavior.get("entry_id")
    observed = next((row for row in rows if row.get("entry_id") == target), None)
    return (
        isinstance(observed, dict)
        and observed.get("disposition") == expected
        and target in delivered
        and behavior.get("behavior_pass") is True
        and isinstance(behavior.get("oracle_digest"), str)
        and len(behavior["oracle_digest"]) == 64
    )


def score_fixture(fixture: dict, outcome: dict, disposition: dict | None = None) -> dict:
    primary = fixture["primary_class"]
    plausible_path = fixture.get("plausible_path")
    acceptable = set(fixture.get("acceptable_entry_ids", []))
    prohibited = set(fixture.get("prohibited_entry_ids", []))
    delivered = outcome["delivery"]["delivered_ids"]
    ranked = _ids(outcome["ranking"]["candidates"])
    eligible = set(outcome["eligibility"]["eligible_ids"])
    decisions = outcome["admission"]["candidate_decisions"]
    admitted = {
        row["entry_id"] for row in decisions
        if isinstance(row, dict) and row.get("admitted") is True
    }
    rejected = {
        row["entry_id"] for row in decisions
        if isinstance(row, dict) and row.get("admitted") is False
    }
    untraceable = sorted(
        row.get("entry_id", "unknown") if isinstance(row, dict) else "unknown"
        for row in decisions
        if not isinstance(row, dict) or not isinstance(row.get("reason"), str) or not row["reason"]
    )
    admitted_acceptable = bool(acceptable.intersection(delivered))
    leakage_scope = eligible.union(ranked).union(delivered) if primary == "integrity" else set(delivered)
    leakage = sorted(prohibited.intersection(leakage_scope))
    retrieval_pass = False
    disposition_required = False
    disposition_pass: bool | None = None

    if primary == "applicable":
        retrieval_pass = (
            outcome["state"] == "admitted"
            and outcome["cause"] == "candidates_delivered"
            and admitted_acceptable
            and bool(acceptable.intersection(admitted))
        )
    elif primary == "true-no-match":
        retrieval_pass = (
            outcome["state"] == "no_match"
            and outcome["cause"] == "no_candidate_admitted"
            and outcome["admission"]["state"] == "no_candidate_admitted"
            and not delivered
        )
    elif primary == "integrity":
        expected = fixture.get("expected", {})
        if expected.get("outer_state") == "invalid_corpus":
            retrieval_pass = (
                outcome["state"] == "invalid_corpus"
                and outcome["cause"] == "invalid_canonical_corpus"
                and outcome["ranking"]["state"] == "not_run"
                and outcome["admission"]["state"] == "not_run"
            )
        else:
            retrieval_pass = (
                outcome["state"] == expected.get("outer_state")
                and outcome["cause"] == expected.get("cause")
                and outcome["admission"]["state"] == expected.get("admission_state")
                and not leakage
                and not prohibited.intersection(ranked)
                and admitted_acceptable
            )
    elif primary == "plausible-inapplicable" and plausible_path == "admission-rejected":
        retrieval_pass = (
            outcome["state"] == "no_match"
            and outcome["cause"] == "no_candidate_admitted"
            and outcome["admission"]["state"] == "no_candidate_admitted"
            and bool(prohibited.intersection(rejected))
        )
    elif primary == "plausible-inapplicable" and plausible_path == "controlled-delivery":
        retrieval_pass = outcome["state"] == "admitted" and admitted_acceptable
        disposition_required = bool(delivered)
        if disposition is not None:
            expected = fixture.get("expected", {}).get("disposition")
            disposition_pass = _disposition_evidence(disposition, delivered, expected)
    passed = retrieval_pass and not leakage and not untraceable and (disposition_pass is not False)
    complete = not disposition_required or disposition_pass is not None
    if disposition_required:
        passed = passed and disposition_pass is True
    return {
        "fixture_id": fixture["id"],
        "primary_class": primary,
        "plausible_path": plausible_path,
        "retrieval_pass": retrieval_pass,
        "disposition_required": disposition_required,
        "disposition_pass": disposition_pass,
        "complete": complete,
        "passed": passed,
        "leaked_prohibited_ids": leakage,
        "untraceable_candidate_ids": untraceable,
        "delivered_count": len(delivered),
        "safe_result": safe_stage_result(outcome),
    }


def score_candidate(
    manifest: dict,
    candidate_id: str,
    execute_fixture: Callable[[dict], dict],
    dispositions: dict[str, dict] | None = None,
) -> dict:
    dispositions = dispositions or {}
    rows = [score_fixture(fixture, execute_fixture(fixture), dispositions.get(fixture["id"])) for fixture in manifest["fixtures"]]
    classes = Counter()
    for row in rows:
        if row["passed"]:
            classes[row["primary_class"]] += 1
    hard_failures = []
    for row in rows:
        result = row["safe_result"]
        expected_integrity_failure = (
            row["primary_class"] == "integrity"
            and result["state"] == "invalid_corpus"
            and row["retrieval_pass"] is True
        )
        if result["state"] in {"unavailable", "invalid_corpus", "stale", "rebuilding"} and not expected_integrity_failure:
            hard_failures.append(f"{row['fixture_id']}:degraded:{result['state']}")
        if row["primary_class"] == "true-no-match" and result["state"] == "admitted":
            hard_failures.append(f"{row['fixture_id']}:admitted_true_no_match")
        if row["leaked_prohibited_ids"]:
            hard_failures.append(f"{row['fixture_id']}:integrity_leak")
        if row["untraceable_candidate_ids"]:
            hard_failures.append(f"{row['fixture_id']}:untraceable_decision")
    complete = all(row["complete"] for row in rows)
    applicable_total = sum(row["primary_class"] == "applicable" for row in rows)
    plausible_total = sum(row["primary_class"] == "plausible-inapplicable" for row in rows)
    displacement = sum(row["delivered_count"] for row in rows if row["primary_class"] == "plausible-inapplicable")
    return {
        "schema_version": 1,
        "split": manifest["split"],
        "manifest_digest": digest(manifest),
        "candidate_id": candidate_id,
        "complete": complete,
        "survives_hard_rules": not hard_failures and complete,
        "hard_failures": hard_failures,
        "score": {
            "applicable_admission_recall": classes["applicable"] / applicable_total if applicable_total else 0.0,
            "applicable_passed": classes["applicable"],
            "applicable_total": applicable_total,
            "plausible_path_passed": classes["plausible-inapplicable"],
            "plausible_total": plausible_total,
            "plausible_admission_rejected_passed": sum(
                row["passed"] and row["plausible_path"] == "admission-rejected" for row in rows
            ),
            "plausible_controlled_delivery_passed": sum(
                row["passed"] and row["plausible_path"] == "controlled-delivery" for row in rows
            ),
            "delivery_displacement": displacement,
        },
        "rows": rows,
        "result_digest": digest(rows),
    }


def select_candidate(scorecards: list[dict]) -> dict:
    survivors = [item for item in scorecards if item.get("survives_hard_rules") is True]
    if not survivors:
        return {"schema_version": 1, "state": "stop", "reason": "no_candidate_survived", "candidates": [item["candidate_id"] for item in scorecards]}

    def selection_key(item: dict) -> tuple:
        score = item["score"]
        similarity_tie = 1 if item["candidate_id"].startswith("similarity:") else 0
        return (
            score["applicable_admission_recall"],
            score["plausible_path_passed"],
            -score["delivery_displacement"],
            similarity_tie,
        )

    ordered = sorted(survivors, key=selection_key, reverse=True)
    winner = ordered[0]
    runner = ordered[1] if len(ordered) > 1 else None
    thin = False
    if runner is not None:
        winning = winner["score"]
        second = runner["score"]
        thin = (
            abs(winning["applicable_passed"] - second["applicable_passed"]) <= 1
            and abs(winning["plausible_path_passed"] - second["plausible_path_passed"]) <= 1
        )
    return {
        "schema_version": 1,
        "state": "selected",
        "winner": winner["candidate_id"],
        "winner_result_digest": winner["result_digest"],
        "thin_margin": thin,
        "selector_revision": "hard-rules-applicable-plausible-displacement-similarity-tie-v1",
        "ordered_survivors": [item["candidate_id"] for item in ordered],
        "selection_digest": digest([item["candidate_id"] for item in ordered]),
    }


def repeatable(left: dict, right: dict) -> dict:
    """Compare normalized score evidence, excluding request IDs only."""
    def normalized(value: dict) -> dict:
        copy = {key: item for key, item in value.items() if key not in {"result_digest"}}
        for row in copy.get("rows", []):
            row.get("safe_result", {}).pop("request_id", None)
        return copy

    a, b = normalized(json_clone(left)), normalized(json_clone(right))
    return {"state": "identical" if a == b else "different", "left_digest": digest(a), "right_digest": digest(b)}


def json_clone(value: dict) -> dict:
    import json
    return json.loads(canonical_json(value))
