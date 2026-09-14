"""Provider-neutral expertise retrieval and admission application service."""
from __future__ import annotations

import json
from pathlib import Path
import re
import time
import unicodedata
import uuid

from expertise import ExpertiseError, canonical_snapshot
from expertise_admission import ExpertiseAdmissionError
from expertise_model import (
    DEFAULT_LIMITS,
    SCHEMA_VERSION,
    ExpertiseContractError,
    canonical_json,
    digest,
    identity,
    normalized_task,
    task_identifiers,
    validate_admission_input,
    validate_admission_decision,
    validate_delivery_result,
    validate_eligibility_result,
    validate_outcome,
)
from expertise_projection import ExpertiseProjectionError, projection_identity
from expertise_ranker import ExpertiseProviderError, rank


ROLES = ("architect", "business-analyst", "lead-developer", "sre", "support-lead", "test-engineer")
FACT_DERIVATION_REVISION = "expertise-task-facts-v1"
ADMISSION_INPUT_REVISION = "expertise-admission-input-v1"
PACKING_REVISION = "complete-entry-utf8-prefix-v1"
ENVELOPE_REVISION = "expertise-envelope-v1"
DISPOSITION_CONTRACT_REVISION = "expertise-disposition-v1"


class ExpertiseServiceError(ValueError):
    pass


def load_fact_definitions(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    if set(data) != {"schema_version", "revision", "normalizer_revision", "facts"} or data.get("schema_version") != 1:
        raise ExpertiseServiceError("invalid fact definitions")
    facts = data.get("facts")
    if not isinstance(facts, list) or len(facts) > 256:
        raise ExpertiseServiceError("invalid fact definitions")
    seen: set[str] = set()
    for item in facts:
        if not isinstance(item, dict) or set(item) != {"code", "present_any", "absent_any"}:
            raise ExpertiseServiceError("invalid fact definition")
        code = item.get("code")
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code) or code in seen:
            raise ExpertiseServiceError("invalid or duplicate fact code")
        seen.add(code)
        for field in ("present_any", "absent_any"):
            patterns = item.get(field)
            if not isinstance(patterns, list) or any(not isinstance(pattern, str) or not pattern.strip() for pattern in patterns):
                raise ExpertiseServiceError("fact patterns must be non-empty strings")
    return data


def _normalized_with_map(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def derive_task_facts(task: str, definitions: dict) -> dict:
    if not isinstance(task, str) or len(task.encode("utf-8")) > 32768:
        raise ExpertiseServiceError("invalid task input")
    normalized = _normalized_with_map(task)
    facts = []
    for definition in definitions["facts"]:
        present = next((pattern for pattern in definition["present_any"] if _normalized_with_map(pattern) in normalized), None)
        absent = next((pattern for pattern in definition["absent_any"] if _normalized_with_map(pattern) in normalized), None)
        if present and not absent:
            value, pattern = "present", present
        elif absent and not present:
            value, pattern = "absent", absent
        else:
            value, pattern = "unknown", None
        start = normalized.find(_normalized_with_map(pattern)) if pattern else 0
        facts.append({"code": definition["code"], "value": value, "evidence_span": [start, start + len(_normalized_with_map(pattern))] if pattern else [0, 0]})
    return {"derivation_revision": definitions["revision"], "facts": facts}


def admission_identity_for(projection: dict, strategy: object, strategy_config: dict, limits: dict) -> dict:
    return identity("admission", {
        "projection_identity": projection["digest"],
        "admission_input_revision": ADMISSION_INPUT_REVISION,
        "fact_derivation_revision": FACT_DERIVATION_REVISION,
        "strategy_revision": str(strategy.revision),
        "strategy_config_digest": digest(strategy_config),
        "ranked_candidate_window": limits["ranked_candidate_window"],
    })


def delivery_identity_for(admission: dict, limits: dict) -> dict:
    return identity("delivery", {
        "admission_identity": admission["digest"],
        "packing_revision": PACKING_REVISION,
        "envelope_revision": ENVELOPE_REVISION,
        "disposition_contract_revision": DISPOSITION_CONTRACT_REVISION,
        "delivery_entry_cap": limits["delivery_entry_cap"],
        "delivery_byte_cap": limits["delivery_byte_cap"],
    })


def complete_entry(entry: dict) -> dict:
    fields = (
        "@id", "name", "abstract", "flow:trigger", "flow:requiredBehavior",
        "flow:failureMode", "flow:source", "teaches",
    )
    value = {field: entry[field] for field in fields if field in entry}
    value["role"] = entry["audience"]["audienceType"]
    value["source_layer"] = entry["_source_layer"]
    value["method_layer"] = entry["_layer"]
    value["lifecycle_state"] = entry["_lifecycle"]["state"]
    value["owner"] = entry["_lifecycle"]["owner"]
    value["entry_digest"] = entry["_entry_digest"]
    return value


def _with_exact_size(value: dict) -> dict:
    """Set actual_bytes to the exact UTF-8 size of its canonical envelope."""
    sized = dict(value)
    size = 0
    for _ in range(8):
        sized["actual_bytes"] = size
        next_size = len(canonical_json(sized).encode("utf-8"))
        if next_size == size:
            return sized
        size = next_size
    raise ExpertiseServiceError("delivery envelope size did not converge")


def _delivery(admitted_ids: list[str], entries: dict[str, dict], delivery_identity: dict, limits: dict) -> dict:
    entry_cap = limits["delivery_entry_cap"]
    byte_cap = limits["delivery_byte_cap"]
    delivered: list[str] = []
    bodies: list[dict] = []
    for entry_id in admitted_ids[:entry_cap]:
        body = complete_entry(entries[entry_id])
        candidate_bodies = bodies + [body]
        trial = {
            "schema_version": SCHEMA_VERSION, "state": "delivered", "reason": "delivered",
            "delivered_ids": delivered + [entry_id], "withheld_ids": admitted_ids[len(delivered) + 1:],
            "actual_bytes": 0,
            "limits": {"delivery_entry_cap": entry_cap, "delivery_byte_cap": byte_cap},
            "identity": delivery_identity["digest"], "entries": candidate_bodies,
        }
        trial = _with_exact_size(trial)
        if trial["actual_bytes"] > byte_cap:
            break
        delivered.append(entry_id)
        bodies = candidate_bodies
    withheld = admitted_ids[len(delivered):]
    state = "delivered" if delivered else ("capped_failure" if admitted_ids else "not_run")
    reason = "not_run" if not admitted_ids else (
        "no_complete_entry_fits" if not delivered else
        "entry_cap_reached" if len(delivered) == entry_cap and withheld else
        "byte_cap_reached" if withheld else "delivered"
    )
    result = {
        "schema_version": SCHEMA_VERSION, "state": state, "reason": reason,
        "delivered_ids": delivered, "withheld_ids": withheld, "actual_bytes": 0,
        "limits": {"delivery_entry_cap": entry_cap, "delivery_byte_cap": byte_cap},
        "identity": delivery_identity["digest"], "entries": bodies,
    }
    return validate_delivery_result(_with_exact_size(result), admitted_ids)


def _not_run_ranking(identity_digest: str, reason: str = "not_run_empty_eligibility") -> dict:
    return {"schema_version": 1, "state": "not_run", "reason": reason, "provider_calls": 0, "candidates": [], "identity": identity_digest}


def _not_run_admission(identity_digest: str) -> dict:
    return {"schema_version": 1, "state": "not_run", "strategy": "not-run", "admitted_ids": [], "candidate_decisions": [], "identity": identity_digest}


def _not_run_delivery(identity_digest: str, limits: dict) -> dict:
    result = {"schema_version": 1, "state": "not_run", "reason": "not_run", "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0, "limits": {"delivery_entry_cap": limits["delivery_entry_cap"], "delivery_byte_cap": limits["delivery_byte_cap"]}, "identity": identity_digest, "entries": []}
    return _with_exact_size(result)


def _finish(outcome: dict, started: float) -> dict:
    validate_outcome(outcome)
    return dict(outcome, elapsed_ms=round((time.perf_counter() - started) * 1000, 3))


def execute(
    role: str,
    task: str,
    *,
    framework_dir: Path,
    user_dir: Path | None,
    flow_home: Path,
    provider: object,
    strategy: object,
    strategy_config: dict,
    fact_definitions: dict,
    limits: dict | None = None,
    request_id: str | None = None,
) -> dict:
    started = time.perf_counter()
    limits = dict(DEFAULT_LIMITS if limits is None else limits)
    request_id = request_id or str(uuid.uuid4())
    if role not in ROLES:
        raise ExpertiseServiceError("unsupported role")
    try:
        snapshot = canonical_snapshot(ROLES, framework_dir, user_dir)
    except ExpertiseError:
        eligibility = {"schema_version": 1, "state": "invalid", "role": role, "eligible_ids": [], "excluded": [], "identity": "invalid-corpus"}
        ranking = _not_run_ranking("not-run", "not_run_invalid_corpus")
        admission = _not_run_admission("not-run")
        delivery = _not_run_delivery("not-run", limits)
        return _finish({"schema_version": 1, "request_id": request_id, "role": role, "state": "invalid_corpus", "cause": "invalid_canonical_corpus", "eligibility": eligibility, "ranking": ranking, "admission": admission, "delivery": delivery}, started)

    projection = projection_identity(snapshot, provider)
    admission_identity = admission_identity_for(projection, strategy, strategy_config, limits)
    delivery_identity = delivery_identity_for(admission_identity, limits)
    role_entries = [entry for entry in snapshot["entries"] if entry["audience"]["audienceType"] == role]
    eligible_entries = [entry for entry in role_entries if entry["_effective_current"]]
    eligible_ids = [entry["@id"] for entry in eligible_entries]
    exclusions = []
    for entry in role_entries:
        if entry["_effective_current"]:
            continue
        state = entry["_lifecycle"]["state"]
        reason = {"unknown": "unknown_lifecycle", "withdrawn": "withdrawn_lifecycle", "superseded": "superseded_lifecycle", "current": "superseded_lifecycle"}[state]
        exclusions.append({"entry_id": entry["@id"], "reason": reason})
    eligibility = validate_eligibility_result({"schema_version": 1, "state": "eligible" if eligible_ids else "empty", "role": role, "eligible_ids": eligible_ids, "excluded": exclusions, "identity": digest({"corpus": snapshot["corpus_digest"], "role": role, "revision": snapshot["lifecycle_revision"]})})
    if not eligible_ids:
        outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": "no_match", "cause": "no_eligible_entries", "eligibility": eligibility, "ranking": _not_run_ranking(projection["digest"]), "admission": _not_run_admission(admission_identity["digest"]), "delivery": _not_run_delivery(delivery_identity["digest"], limits)}
        return _finish(outcome, started)

    try:
        ranking = rank(flow_home, role, task, provider, projection["digest"], window=limits["ranked_candidate_window"])
    except ExpertiseProjectionError as error:
        reason = str(error) if str(error) in {"projection_missing", "projection_stale"} else "projection_missing"
        state = "stale" if reason == "projection_stale" else "unavailable"
        ranking = {"schema_version": 1, "state": "stale" if state == "stale" else "unavailable", "reason": reason, "provider_calls": 0, "candidates": [], "identity": projection["digest"]}
        outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": state, "cause": reason, "eligibility": eligibility, "ranking": ranking, "admission": _not_run_admission(admission_identity["digest"]), "delivery": _not_run_delivery(delivery_identity["digest"], limits)}
        return _finish(outcome, started)
    except ExpertiseProviderError as error:
        reason = error.reason if error.reason in {"provider_missing", "provider_unapproved", "provider_hash_mismatch", "unsupported_runtime", "provider_load_failed", "provider_output_invalid"} else "provider_load_failed"
        ranking = {"schema_version": 1, "state": "invalid_result" if reason == "provider_output_invalid" else "unavailable", "reason": reason, "provider_calls": 1, "candidates": [], "identity": projection["digest"]}
        outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": "unavailable", "cause": "invalid_provider_result" if reason == "provider_output_invalid" else "provider_unavailable", "eligibility": eligibility, "ranking": ranking, "admission": _not_run_admission(admission_identity["digest"]), "delivery": _not_run_delivery(delivery_identity["digest"], limits)}
        return _finish(outcome, started)

    by_id = {entry["@id"]: entry for entry in eligible_entries}
    admission_input = validate_admission_input({
        "schema_version": 1, "role": role, "admission_contract_revision": ADMISSION_INPUT_REVISION,
        "query_view": {"normalizer_revision": "nfkc-casefold-whitespace-v1", "normalized_text": normalized_task(task), "tokens": normalized_task(task).split(), "identifiers": list(task_identifiers(task))},
        "task_facts": derive_task_facts(task, fact_definitions),
        "eligibility": {"corpus_digest": snapshot["corpus_digest"], "eligibility_revision": snapshot["lifecycle_revision"]},
        "ranking": {"ranker_revision": "exact-cosine-v1", "provider_model_revision": str(provider.provider_revision), "candidates": [dict(row, trigger_view=by_id[row["entry_id"]]["flow:trigger"], failure_mode_view=by_id[row["entry_id"]]["flow:failureMode"]) for row in ranking["candidates"]]},
        "limits": limits,
    })
    try:
        admission = validate_admission_decision(
            strategy.decide(admission_input, admission_identity["digest"]),
            [row["entry_id"] for row in ranking["candidates"]],
        )
    except (ExpertiseAdmissionError, ExpertiseContractError, AttributeError, TypeError, ValueError) as error:
        unavailable = isinstance(error, ExpertiseAdmissionError) and error.reason not in {"invalid_gate_output"}
        failure_state = "gate_unavailable" if unavailable else "invalid_gate_output"
        admission = {"schema_version": 1, "state": failure_state, "strategy": str(getattr(strategy, "revision", "invalid-gate")), "admitted_ids": [], "candidate_decisions": [], "identity": admission_identity["digest"]}
        outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": "unavailable", "cause": failure_state, "eligibility": eligibility, "ranking": ranking, "admission": admission, "delivery": _not_run_delivery(delivery_identity["digest"], limits)}
        return _finish(outcome, started)
    if not admission["admitted_ids"]:
        outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": "no_match", "cause": "no_candidate_admitted", "eligibility": eligibility, "ranking": ranking, "admission": admission, "delivery": _not_run_delivery(delivery_identity["digest"], limits)}
        return _finish(outcome, started)
    try:
        for candidate in ranking["candidates"]:
            if candidate["entry_id"] in admission["admitted_ids"] and by_id[candidate["entry_id"]]["_entry_digest"] != candidate["entry_digest"]:
                raise ExpertiseServiceError("canonical_entry_changed")
        delivery = _delivery(admission["admitted_ids"], by_id, delivery_identity, limits)
    except (ExpertiseContractError, ExpertiseServiceError, KeyError, TypeError, ValueError):
        delivery = {"schema_version": 1, "state": "invalid_envelope", "reason": "invalid_envelope", "delivered_ids": [], "withheld_ids": admission["admitted_ids"], "actual_bytes": 0, "limits": {"delivery_entry_cap": limits["delivery_entry_cap"], "delivery_byte_cap": limits["delivery_byte_cap"]}, "identity": delivery_identity["digest"], "entries": []}
        return _finish({"schema_version": 1, "request_id": request_id, "role": role, "state": "unavailable", "cause": "invalid_delivery_envelope", "eligibility": eligibility, "ranking": ranking, "admission": admission, "delivery": delivery}, started)
    state, cause = ("admitted", "candidates_delivered") if delivery["delivered_ids"] else ("unavailable", "no_complete_entry_fits")
    outcome = {"schema_version": 1, "request_id": request_id, "role": role, "state": state, "cause": cause, "eligibility": eligibility, "ranking": ranking, "admission": admission, "delivery": delivery}
    return _finish(outcome, started)
