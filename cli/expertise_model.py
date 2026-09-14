"""Pure contracts for local agent-expertise retrieval and admission.

This module has no filesystem, SQLite, provider, or runtime dependencies.  It
defines the vocabulary that every later adapter must preserve and validates the
bounded value passed from semantic ranking into candidate admission.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from datetime import datetime
from typing import Any


SCHEMA_VERSION = 1
OUTER_STATES = frozenset({
    "admitted", "no_match", "unavailable", "invalid_corpus", "stale",
    "rebuilding",
})
ELIGIBILITY_STATES = frozenset({"eligible", "empty", "invalid"})
RANKING_STATES = frozenset({
    "not_run", "ranked", "unavailable", "invalid_result", "stale",
    "rebuilding",
})
ADMISSION_STATES = frozenset({
    "not_run", "admitted", "no_candidate_admitted", "gate_unavailable",
    "invalid_gate_output",
})
DELIVERY_STATES = frozenset({
    "not_run", "delivered", "capped_failure", "invalid_envelope",
})
DISPOSITION_STATES = frozenset({"observed", "not_observed"})
ENTRY_DISPOSITIONS = frozenset({"applied", "ignored", "insufficient_context"})
ROLLOUT_STATES = frozenset({
    "composed", "shadow", "qualified_disabled", "retrieval_enabled",
})
CAMPAIGN_DECISIONS = frozenset({
    "enable_support_lead", "retain_shadow", "stop",
})
FACT_VALUES = frozenset({"present", "absent", "unknown"})
PRIMARY_CLASSES = frozenset({
    "applicable", "plausible-inapplicable", "true-no-match",
    "integrity",
})
PLAUSIBLE_PATHS = frozenset({"admission-rejected", "controlled-delivery"})
SPLITS = ("calibration-v1", "evaluation-v2")
DEFAULT_LIMITS = {
    "ranked_candidate_window": 3,
    "maximum_admitted_ids": 3,
    "delivery_entry_cap": 3,
    "delivery_byte_cap": 16384,
}
OUTER_CAUSES = frozenset({
    "candidates_delivered", "no_eligible_entries", "no_candidate_admitted",
    "invalid_canonical_corpus", "projection_missing", "projection_stale",
    "projection_rebuilding", "provider_unavailable", "invalid_provider_result",
    "gate_unavailable", "invalid_gate_output", "no_complete_entry_fits",
    "invalid_delivery_envelope",
})
EXCLUSION_REASONS = frozenset({
    "wrong_role", "unknown_lifecycle", "withdrawn_lifecycle",
    "superseded_lifecycle", "unauthorized_source_layer",
    "unauthorized_method_layer", "unauthorized_owner", "malformed_entry",
    "invalid_graph",
})
RANKING_REASONS = frozenset({
    "ranked", "not_run_empty_eligibility", "not_run_invalid_corpus", "provider_missing",
    "provider_unapproved", "provider_hash_mismatch", "unsupported_runtime",
    "provider_load_failed", "provider_output_invalid", "projection_missing", "projection_stale",
    "projection_rebuilding",
})
ADMISSION_REASONS = frozenset({
    "similarity_threshold_met", "similarity_below_threshold",
    "structured_exact_match", "trigger_satisfied", "trigger_contradicted",
    "trigger_absent", "trigger_unknown_admitted", "trigger_unknown_rejected",
    "candidate_rejected", "admitted_within_limit", "admitted_limit_reached",
    "rule_coverage_missing", "gate_failed", "gate_output_invalid",
    "not_run_empty_eligibility",
})
DELIVERY_REASONS = frozenset({
    "delivered", "entry_cap_reached", "byte_cap_reached",
    "no_complete_entry_fits", "canonical_entry_changed", "entry_missing",
    "invalid_envelope", "not_run",
})
DISPOSITION_REASONS = frozenset({
    "trigger_satisfied", "trigger_absent", "trigger_contradicted",
    "constraint_displaced", "required_fact_missing", "materiality_absent",
})
IDENTITY_COMPONENTS = {
    "projection": frozenset({
        "corpus_digest", "lifecycle_revision", "entry_serializer_revision",
        "provider_revision", "model_artifact_digest", "embedding_runtime_revision",
        "index_schema_revision",
    }),
    "admission": frozenset({
        "projection_identity", "admission_input_revision", "fact_derivation_revision",
        "strategy_revision", "strategy_config_digest", "ranked_candidate_window",
    }),
    "delivery": frozenset({
        "admission_identity", "packing_revision", "envelope_revision",
        "disposition_contract_revision", "delivery_entry_cap", "delivery_byte_cap",
    }),
}
TRIGGER_OPERATORS = frozenset({"is"})
UNKNOWN_POLICIES = frozenset({"admit_for_context", "reject"})
FACT_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

IDENTIFIER_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*[-_:][A-Za-z0-9_.:-]+")


class ExpertiseContractError(ValueError):
    """A versioned expertise contract is malformed or crosses a boundary."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    payload = value if isinstance(value, bytes) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def identity(kind: str, components: Any) -> dict:
    if kind not in IDENTITY_COMPONENTS:
        raise ExpertiseContractError(f"unknown identity kind: {kind}")
    data = _mapping(components, f"{kind} identity components")
    _closed(data, set(IDENTITY_COMPONENTS[kind]), f"{kind} identity components")
    missing = IDENTITY_COMPONENTS[kind] - set(data)
    if missing:
        raise ExpertiseContractError(
            f"{kind} identity is missing: {', '.join(sorted(missing))}"
        )
    for field, value in data.items():
        if field.endswith("_cap") or field == "ranked_candidate_window":
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ExpertiseContractError(f"{kind} identity {field} must be a non-negative integer")
        else:
            _nonempty(value, f"{kind} identity {field}")
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "components": dict(data),
        "digest": digest({"schema_version": SCHEMA_VERSION, "kind": kind, "components": data}),
    }


def validate_identity(value: Any, expected_kind: str | None = None) -> dict:
    data = _mapping(value, "identity")
    _closed(data, {"schema_version", "kind", "components", "digest"}, "identity")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ExpertiseContractError("unsupported identity schema_version")
    kind = data.get("kind")
    if expected_kind is not None and kind != expected_kind:
        raise ExpertiseContractError(f"expected {expected_kind} identity")
    expected = identity(kind, data.get("components"))
    if data.get("digest") != expected["digest"]:
        raise ExpertiseContractError(f"{kind} identity digest mismatch")
    return data


def validate_trigger_rule(value: Any, *, entry_id: str | None = None) -> dict:
    rule = _mapping(value, "trigger rule")
    _closed(rule, {
        "schema_version", "entry_id", "entry_digest", "trigger_digest",
        "failure_mode_digest", "revision", "unknown_policy", "clauses", "digest",
    }, "trigger rule")
    if rule.get("schema_version") != SCHEMA_VERSION:
        raise ExpertiseContractError("unsupported trigger rule schema_version")
    actual_entry = _nonempty(rule.get("entry_id"), "trigger rule entry_id")
    if entry_id is not None and actual_entry != entry_id:
        raise ExpertiseContractError("trigger rule entry_id mismatch")
    _nonempty(rule.get("revision"), "trigger rule revision")
    entry_digest = _nonempty(rule.get("entry_digest"), "trigger rule entry_digest")
    if not re.fullmatch(r"[0-9a-f]{64}", entry_digest):
        raise ExpertiseContractError("trigger rule entry_digest must be lowercase SHA-256")
    for field in ("trigger_digest", "failure_mode_digest"):
        value_digest = _nonempty(rule.get(field), f"trigger rule {field}")
        if not re.fullmatch(r"[0-9a-f]{64}", value_digest):
            raise ExpertiseContractError(f"trigger rule {field} must be lowercase SHA-256")
    if rule.get("unknown_policy") not in UNKNOWN_POLICIES:
        raise ExpertiseContractError("invalid trigger rule unknown_policy")
    clauses = rule.get("clauses")
    if not isinstance(clauses, list) or not 1 <= len(clauses) <= 32:
        raise ExpertiseContractError("trigger rule requires one to 32 clauses")
    codes: set[str] = set()
    for index, raw in enumerate(clauses):
        clause = _mapping(raw, f"trigger rule clause {index}")
        _closed(clause, {"fact", "operator", "value"}, f"trigger rule clause {index}")
        fact = clause.get("fact")
        if not isinstance(fact, str) or not FACT_CODE_RE.fullmatch(fact):
            raise ExpertiseContractError(f"invalid trigger fact code at clause {index}")
        if fact in codes:
            raise ExpertiseContractError(f"duplicate trigger fact code: {fact}")
        codes.add(fact)
        if clause.get("operator") not in TRIGGER_OPERATORS or clause.get("value") not in {"present", "absent"}:
            raise ExpertiseContractError(f"invalid trigger clause at index {index}")
    payload = {key: value for key, value in rule.items() if key != "digest"}
    if rule.get("digest") != digest(payload):
        raise ExpertiseContractError("trigger rule digest mismatch")
    return rule


def normalized_task(text: str) -> str:
    if not isinstance(text, str):
        raise ExpertiseContractError("task text must be a string")
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def task_identifiers(text: str) -> tuple[str, ...]:
    return tuple(sorted({match.group(0).casefold() for match in IDENTIFIER_RE.finditer(text)}))


def _mapping(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ExpertiseContractError(f"{label} must be an object")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExpertiseContractError(f"{label} must be a non-empty string")
    return value


def validate_admission_input(value: Any) -> dict:
    """Validate the pre-adapter, provider-neutral admission value.

    The validator deliberately knows nothing about a provider or Strategy.  It
    enforces only the boundary: one role, one ordered eligible candidate window,
    finite provider-scoped scores, bounded task facts, and digest-bound trigger
    views.  A Strategy can decide those IDs; it cannot manufacture others.
    """
    data = _mapping(value, "AdmissionInput")
    _closed(data, {
        "schema_version", "role", "admission_contract_revision", "query_view",
        "task_facts", "eligibility", "ranking", "limits",
    }, "AdmissionInput")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ExpertiseContractError("unsupported AdmissionInput schema_version")
    _nonempty(data.get("role"), "role")
    _nonempty(data.get("admission_contract_revision"), "admission_contract_revision")

    query = _mapping(data.get("query_view"), "query_view")
    _closed(query, {"normalizer_revision", "normalized_text", "tokens", "identifiers"}, "query_view")
    _nonempty(query.get("normalizer_revision"), "query_view.normalizer_revision")
    text = query.get("normalized_text")
    if not isinstance(text, str) or len(text.encode("utf-8")) > 32768:
        raise ExpertiseContractError("query_view.normalized_text exceeds 32768 UTF-8 bytes or is not text")
    tokens = query.get("tokens")
    if not isinstance(tokens, list) or len(tokens) > 4096 or any(not isinstance(x, str) for x in tokens):
        raise ExpertiseContractError("query_view.tokens must be a bounded string list")
    identifiers = query.get("identifiers")
    if not isinstance(identifiers, list) or len(identifiers) > 256 or any(not isinstance(x, str) for x in identifiers):
        raise ExpertiseContractError("query_view.identifiers must be a bounded string list")

    task_facts = _mapping(data.get("task_facts"), "task_facts")
    _closed(task_facts, {"derivation_revision", "facts"}, "task_facts")
    _nonempty(task_facts.get("derivation_revision"), "task_facts.derivation_revision")
    facts = task_facts.get("facts")
    if not isinstance(facts, list) or len(facts) > 256:
        raise ExpertiseContractError("task_facts.facts must be a bounded list")
    fact_codes: set[str] = set()
    for index, raw in enumerate(facts):
        fact = _mapping(raw, f"task_facts.facts[{index}]")
        _closed(fact, {"code", "value", "evidence_span"}, f"task_facts.facts[{index}]")
        code = _nonempty(fact.get("code"), f"task_facts.facts[{index}].code")
        if code in fact_codes:
            raise ExpertiseContractError(f"duplicate task fact code: {code}")
        fact_codes.add(code)
        if fact.get("value") not in FACT_VALUES:
            raise ExpertiseContractError(f"invalid task fact value for {code}")
        span = fact.get("evidence_span")
        if not (
            isinstance(span, list) and len(span) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in span)
            and 0 <= span[0] <= span[1] <= len(text)
        ):
            raise ExpertiseContractError(f"invalid evidence span for {code}")

    eligibility = _mapping(data.get("eligibility"), "eligibility")
    _closed(eligibility, {"corpus_digest", "eligibility_revision"}, "eligibility")
    _nonempty(eligibility.get("corpus_digest"), "eligibility.corpus_digest")
    _nonempty(eligibility.get("eligibility_revision"), "eligibility.eligibility_revision")
    ranking = _mapping(data.get("ranking"), "ranking")
    _closed(ranking, {"ranker_revision", "provider_model_revision", "candidates"}, "ranking")
    for field in ("ranker_revision", "provider_model_revision"):
        _nonempty(ranking.get(field), f"ranking.{field}")
    limits = _mapping(data.get("limits"), "limits")
    _closed(limits, {
        "ranked_candidate_window", "maximum_admitted_ids", "delivery_entry_cap",
        "delivery_byte_cap",
    }, "limits")
    window = limits.get("ranked_candidate_window")
    maximum = limits.get("maximum_admitted_ids")
    delivery_entries = limits.get("delivery_entry_cap")
    delivery_bytes = limits.get("delivery_byte_cap")
    if not isinstance(window, int) or isinstance(window, bool) or not 0 <= window <= 32:
        raise ExpertiseContractError("ranked_candidate_window must be an integer from 0 to 32")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 0 <= maximum <= window:
        raise ExpertiseContractError("maximum_admitted_ids must be between 0 and ranked_candidate_window")
    if not isinstance(delivery_entries, int) or isinstance(delivery_entries, bool) or not 0 <= delivery_entries <= maximum:
        raise ExpertiseContractError("delivery_entry_cap must be between 0 and maximum_admitted_ids")
    if not isinstance(delivery_bytes, int) or isinstance(delivery_bytes, bool) or not 256 <= delivery_bytes <= 1048576:
        raise ExpertiseContractError("delivery_byte_cap must be between 256 and 1048576")

    candidates = ranking.get("candidates")
    if not isinstance(candidates, list) or len(candidates) > window:
        raise ExpertiseContractError("ranking.candidates exceeds the ranked window or is not a list")
    seen: set[str] = set()
    for index, raw in enumerate(candidates, start=1):
        candidate = _mapping(raw, f"ranking.candidates[{index - 1}]")
        _closed(candidate, {
            "entry_id", "ordinal", "provider_score", "entry_digest",
            "score_semantics", "structured_exact_match", "trigger_view",
            "failure_mode_view",
        }, f"ranking.candidates[{index - 1}]")
        entry_id = _nonempty(candidate.get("entry_id"), "candidate.entry_id")
        if entry_id in seen:
            raise ExpertiseContractError(f"duplicate ranked candidate: {entry_id}")
        seen.add(entry_id)
        if candidate.get("ordinal") != index:
            raise ExpertiseContractError("candidate ordinals must be contiguous and rank ordered")
        score = candidate.get("provider_score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(float(score)):
            raise ExpertiseContractError(f"provider score for {entry_id} must be finite")
        _nonempty(candidate.get("entry_digest"), "candidate.entry_digest")
        _nonempty(candidate.get("score_semantics"), "candidate.score_semantics")
        if not isinstance(candidate.get("structured_exact_match"), bool):
            raise ExpertiseContractError("candidate.structured_exact_match must be boolean")
        _nonempty(candidate.get("trigger_view"), "candidate.trigger_view")
        _nonempty(candidate.get("failure_mode_view"), "candidate.failure_mode_view")
    return data


def validate_eligibility_result(value: Any) -> dict:
    data = _mapping(value, "EligibilityResult")
    _closed(data, {"schema_version", "state", "role", "eligible_ids", "excluded", "identity"}, "EligibilityResult")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in ELIGIBILITY_STATES:
        raise ExpertiseContractError("invalid EligibilityResult schema or state")
    _nonempty(data.get("role"), "EligibilityResult role")
    eligible = data.get("eligible_ids")
    excluded = data.get("excluded")
    if not isinstance(eligible, list) or len(eligible) != len(set(eligible)) or any(not isinstance(x, str) or not x for x in eligible):
        raise ExpertiseContractError("EligibilityResult eligible_ids must be distinct strings")
    if not isinstance(excluded, list):
        raise ExpertiseContractError("EligibilityResult excluded must be a list")
    excluded_ids: set[str] = set()
    for row in excluded:
        item = _mapping(row, "eligibility exclusion")
        _closed(item, {"entry_id", "reason"}, "eligibility exclusion")
        entry = _nonempty(item.get("entry_id"), "eligibility exclusion entry_id")
        if entry in excluded_ids or entry in eligible:
            raise ExpertiseContractError("eligibility IDs overlap or repeat")
        excluded_ids.add(entry)
        if item.get("reason") not in EXCLUSION_REASONS:
            raise ExpertiseContractError("invalid eligibility exclusion reason")
    _nonempty(data.get("identity"), "EligibilityResult identity")
    if data["state"] == "empty" and eligible or data["state"] == "eligible" and not eligible:
        raise ExpertiseContractError("eligibility state does not match eligible_ids")
    return data


def validate_ranking_result(value: Any) -> dict:
    data = _mapping(value, "RankingResult")
    _closed(data, {"schema_version", "state", "reason", "provider_calls", "candidates", "identity"}, "RankingResult")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in RANKING_STATES:
        raise ExpertiseContractError("invalid RankingResult schema or state")
    if data.get("reason") not in RANKING_REASONS:
        raise ExpertiseContractError("invalid RankingResult reason")
    if not isinstance(data.get("provider_calls"), int) or isinstance(data["provider_calls"], bool) or data["provider_calls"] < 0:
        raise ExpertiseContractError("RankingResult provider_calls must be non-negative")
    candidates = data.get("candidates")
    if not isinstance(candidates, list):
        raise ExpertiseContractError("RankingResult candidates must be a list")
    seen: set[str] = set()
    for ordinal, row in enumerate(candidates, 1):
        item = _mapping(row, "ranked candidate")
        _closed(item, {"entry_id", "ordinal", "provider_score", "entry_digest", "score_semantics", "structured_exact_match"}, "ranked candidate")
        entry = _nonempty(item.get("entry_id"), "ranked candidate entry_id")
        if entry in seen or item.get("ordinal") != ordinal:
            raise ExpertiseContractError("ranked candidates must be unique and contiguous")
        seen.add(entry)
        score = item.get("provider_score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(float(score)):
            raise ExpertiseContractError("ranked candidate score must be finite")
        _nonempty(item.get("entry_digest"), "ranked candidate entry_digest")
        _nonempty(item.get("score_semantics"), "ranked candidate score_semantics")
        if not isinstance(item.get("structured_exact_match"), bool):
            raise ExpertiseContractError("structured_exact_match must be boolean")
    if data["state"] == "ranked" and not candidates:
        raise ExpertiseContractError("ranked state requires candidates")
    if data["state"] != "ranked" and candidates:
        raise ExpertiseContractError("non-ranked state cannot contain candidates")
    allowed_state_reasons = {
        "not_run": {"not_run_empty_eligibility", "not_run_invalid_corpus"},
        "ranked": {"ranked"},
        "stale": {"projection_stale"},
        "rebuilding": {"projection_rebuilding"},
        "invalid_result": {"provider_output_invalid"},
        "unavailable": {
            "projection_missing", "provider_missing", "provider_unapproved",
            "provider_hash_mismatch", "unsupported_runtime", "provider_load_failed",
        },
    }
    if data["reason"] not in allowed_state_reasons[data["state"]]:
        raise ExpertiseContractError("ranking state and reason disagree")
    if data["state"] in {"not_run", "stale", "rebuilding"} and data["provider_calls"] != 0:
        raise ExpertiseContractError("ranking provider_calls disagree with stage state")
    _nonempty(data.get("identity"), "RankingResult identity")
    return data


def validate_admission_decision(value: Any, ranked_ids: list[str]) -> dict:
    data = _mapping(value, "AdmissionDecision")
    _closed(data, {"schema_version", "state", "strategy", "admitted_ids", "candidate_decisions", "identity"}, "AdmissionDecision")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in ADMISSION_STATES:
        raise ExpertiseContractError("invalid AdmissionDecision schema or state")
    _nonempty(data.get("strategy"), "AdmissionDecision strategy")
    admitted = data.get("admitted_ids")
    decisions = data.get("candidate_decisions")
    if not isinstance(admitted, list) or len(admitted) != len(set(admitted)):
        raise ExpertiseContractError("AdmissionDecision admitted_ids must be distinct")
    if any(entry not in ranked_ids for entry in admitted):
        raise ExpertiseContractError("admission restored an unranked entry")
    if admitted != [entry for entry in ranked_ids if entry in set(admitted)]:
        raise ExpertiseContractError("admission changed rank order")
    if not isinstance(decisions, list):
        raise ExpertiseContractError("candidate_decisions must be a list")
    for row in decisions:
        item = _mapping(row, "candidate decision")
        _closed(item, {"entry_id", "admitted", "reason", "evidence_codes"}, "candidate decision")
        if item.get("entry_id") not in ranked_ids or not isinstance(item.get("admitted"), bool):
            raise ExpertiseContractError("invalid candidate decision")
        if item.get("reason") not in ADMISSION_REASONS:
            raise ExpertiseContractError("invalid admission reason")
        codes = item.get("evidence_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) or not FACT_CODE_RE.fullmatch(code) for code in codes):
            raise ExpertiseContractError("candidate decision evidence_codes are invalid")
    decision_ids = [row.get("entry_id") for row in decisions if isinstance(row, dict)]
    if data["state"] in {"admitted", "no_candidate_admitted"} and decision_ids != ranked_ids:
        raise ExpertiseContractError("candidate_decisions must account for every ranked ID in order")
    if data["state"] in {"not_run", "gate_unavailable", "invalid_gate_output"} and decisions:
        raise ExpertiseContractError("an incomplete admission stage cannot contain candidate decisions")
    admitted_set = set(admitted)
    if any(row["admitted"] != (row["entry_id"] in admitted_set) for row in decisions):
        raise ExpertiseContractError("candidate decision admitted flags disagree with admitted_ids")
    if data["state"] == "admitted" and not admitted:
        raise ExpertiseContractError("admitted state requires admitted_ids")
    if data["state"] != "admitted" and admitted:
        raise ExpertiseContractError("non-admitted state cannot contain admitted_ids")
    _nonempty(data.get("identity"), "AdmissionDecision identity")
    return data


def validate_delivery_result(value: Any, admitted_ids: list[str]) -> dict:
    data = _mapping(value, "DeliveryResult")
    _closed(data, {"schema_version", "state", "reason", "delivered_ids", "withheld_ids", "actual_bytes", "limits", "identity", "entries"}, "DeliveryResult")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in DELIVERY_STATES:
        raise ExpertiseContractError("invalid DeliveryResult schema or state")
    if data.get("reason") not in DELIVERY_REASONS:
        raise ExpertiseContractError("invalid DeliveryResult reason")
    delivered, withheld = data.get("delivered_ids"), data.get("withheld_ids")
    if not isinstance(delivered, list) or not isinstance(withheld, list) or delivered + withheld != admitted_ids:
        raise ExpertiseContractError("delivery must partition admitted IDs without reordering")
    if not isinstance(data.get("actual_bytes"), int) or isinstance(data["actual_bytes"], bool) or data["actual_bytes"] < 0:
        raise ExpertiseContractError("DeliveryResult actual_bytes must be non-negative")
    limits = _mapping(data.get("limits"), "DeliveryResult limits")
    _closed(limits, {"delivery_entry_cap", "delivery_byte_cap"}, "DeliveryResult limits")
    if len(delivered) > limits.get("delivery_entry_cap", -1) or data["actual_bytes"] > limits.get("delivery_byte_cap", -1):
        raise ExpertiseContractError("DeliveryResult exceeds its limits")
    entries = data.get("entries")
    if not isinstance(entries, list) or [item.get("@id") for item in entries if isinstance(item, dict)] != delivered:
        raise ExpertiseContractError("delivery entries must be complete ordered delivered IDs")
    _nonempty(data.get("identity"), "DeliveryResult identity")
    return data


def validate_disposition_record(value: Any, delivered_ids: list[str]) -> dict:
    data = _mapping(value, "DispositionRecord")
    _closed(data, {"schema_version", "state", "created_at", "request_id", "pre_receipt_digest", "entries", "identity"}, "DispositionRecord")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in DISPOSITION_STATES:
        raise ExpertiseContractError("invalid DispositionRecord schema or state")
    _nonempty(data.get("request_id"), "DispositionRecord request_id")
    _nonempty(data.get("pre_receipt_digest"), "DispositionRecord pre_receipt_digest")
    created_at = _nonempty(data.get("created_at"), "DispositionRecord created_at")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as error:
        raise ExpertiseContractError("DispositionRecord created_at must be ISO-8601") from error
    if parsed_created_at.tzinfo is None:
        raise ExpertiseContractError("DispositionRecord created_at must include a timezone")
    rows = data.get("entries")
    if not isinstance(rows, list) or [row.get("entry_id") for row in rows if isinstance(row, dict)] != delivered_ids:
        raise ExpertiseContractError("DispositionRecord must account for every delivered ID in order")
    for row in rows:
        _closed(row, {"entry_id", "disposition", "reason", "evidence_codes"}, "disposition entry")
        if row.get("disposition") not in ENTRY_DISPOSITIONS or row.get("reason") not in DISPOSITION_REASONS:
            raise ExpertiseContractError("invalid disposition or reason")
        codes = row.get("evidence_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) or not FACT_CODE_RE.fullmatch(code) for code in codes):
            raise ExpertiseContractError("invalid disposition evidence_codes")
    if data["state"] == "observed" and len(rows) != len(delivered_ids):
        raise ExpertiseContractError("observed disposition is incomplete")
    _nonempty(data.get("identity"), "DispositionRecord identity")
    return data


def validate_outcome(value: Any) -> dict:
    data = _mapping(value, "ExpertiseOutcome")
    _closed(data, {"schema_version", "request_id", "role", "state", "cause", "eligibility", "ranking", "admission", "delivery"}, "ExpertiseOutcome")
    if data.get("schema_version") != SCHEMA_VERSION or data.get("state") not in OUTER_STATES or data.get("cause") not in OUTER_CAUSES:
        raise ExpertiseContractError("invalid ExpertiseOutcome schema, state, or cause")
    _nonempty(data.get("request_id"), "ExpertiseOutcome request_id")
    _nonempty(data.get("role"), "ExpertiseOutcome role")
    eligibility = validate_eligibility_result(data.get("eligibility"))
    ranking = validate_ranking_result(data.get("ranking"))
    ranked_ids = [row["entry_id"] for row in ranking["candidates"]]
    admission = validate_admission_decision(data.get("admission"), ranked_ids)
    delivery = validate_delivery_result(data.get("delivery"), admission["admitted_ids"])
    if data["state"] == "no_match":
        valid = (
            data["cause"] == "no_eligible_entries"
            and eligibility["state"] == "empty"
            and ranking["state"] == "not_run" and ranking["provider_calls"] == 0
            and admission["state"] == "not_run"
        ) or (
            data["cause"] == "no_candidate_admitted"
            and eligibility["state"] == "eligible" and ranking["state"] == "ranked"
            and admission["state"] == "no_candidate_admitted"
        )
        if not valid:
            raise ExpertiseContractError("no_match is not supported by completed stage evidence")
    if data["state"] == "admitted" and not (
        data["cause"] == "candidates_delivered" and delivery["state"] == "delivered" and delivery["delivered_ids"]
    ):
        raise ExpertiseContractError("admitted outer state requires delivered entries")
    if data["state"] == "invalid_corpus" and not (
        data["cause"] == "invalid_canonical_corpus"
        and eligibility["state"] == "invalid"
        and ranking["state"] == "not_run" and ranking["provider_calls"] == 0
        and admission["state"] == "not_run" and delivery["state"] == "not_run"
    ):
        raise ExpertiseContractError("invalid_corpus is not supported by stage evidence")
    if data["state"] == "stale" and not (
        data["cause"] == "projection_stale" and ranking["state"] == "stale"
        and admission["state"] == "not_run" and delivery["state"] == "not_run"
    ):
        raise ExpertiseContractError("stale is not supported by stage evidence")
    if data["state"] == "rebuilding" and not (
        data["cause"] == "projection_rebuilding" and ranking["state"] == "rebuilding"
        and admission["state"] == "not_run" and delivery["state"] == "not_run"
    ):
        raise ExpertiseContractError("rebuilding is not supported by stage evidence")
    if data["state"] == "unavailable":
        exact_failure = {
            "projection_missing": ranking["state"] == "unavailable" and ranking["reason"] == "projection_missing" and admission["state"] == "not_run" and delivery["state"] == "not_run",
            "provider_unavailable": ranking["state"] == "unavailable" and ranking["reason"] in {"provider_missing", "provider_unapproved", "provider_hash_mismatch", "unsupported_runtime", "provider_load_failed"} and admission["state"] == "not_run" and delivery["state"] == "not_run",
            "invalid_provider_result": ranking["state"] == "invalid_result" and ranking["reason"] == "provider_output_invalid" and admission["state"] == "not_run" and delivery["state"] == "not_run",
            "gate_unavailable": ranking["state"] == "ranked" and admission["state"] == "gate_unavailable" and delivery["state"] == "not_run",
            "invalid_gate_output": ranking["state"] == "ranked" and admission["state"] == "invalid_gate_output" and delivery["state"] == "not_run",
            "no_complete_entry_fits": ranking["state"] == "ranked" and admission["state"] == "admitted" and delivery["state"] == "capped_failure" and delivery["reason"] == "no_complete_entry_fits",
            "invalid_delivery_envelope": ranking["state"] == "ranked" and admission["state"] == "admitted" and delivery["state"] == "invalid_envelope" and delivery["reason"] == "invalid_envelope",
        }
        if not exact_failure.get(data["cause"], False):
            raise ExpertiseContractError("unavailable is not supported by stage evidence")
    return data


def _closed(value: dict, fields: set[str], label: str) -> None:
    extras = set(value) - fields
    if extras:
        raise ExpertiseContractError(
            f"{label} contains unsupported fields: {', '.join(sorted(extras))}"
        )
