"""Flow-owned structured verifier candidate and evaluation contracts.

Provider output is an untrusted candidate.  This module deliberately has no
provider or ledger dependency: callers persist the raw provider observation,
then use this deterministic evaluator to record Flow's judgment.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


VERIFIER_VERDICT_SCHEMA_VERSION = 1
VERIFIER_EVALUATION_SCHEMA_VERSION = 1
MAX_RAW_OUTPUT_BYTES = 16 * 1024
MAX_SUMMARY_BYTES = 1024
MAX_FINDINGS = 16
MAX_FINDING_SUMMARY_BYTES = 1024
MAX_FINDING_EVIDENCE_BYTES = 2048

VALID_DECISIONS = frozenset({"pass", "fail"})
VALID_SEVERITIES = frozenset({"blocking", "non_blocking"})
VALID_DISPOSITIONS = frozenset({"valid_pass", "valid_fail", "unusable"})
FORCED_UNUSABLE_REASONS = frozenset({"provider_binding_mismatch"})
UNUSABLE_REASON_CODES = frozenset({
    "raw_output_invalid", "candidate_json_invalid", "candidate_root_invalid",
    "candidate_fields_invalid", "candidate_schema_version_unsupported",
    "candidate_decision_invalid", "candidate_summary_invalid",
    "candidate_findings_invalid", "candidate_finding_fields_invalid",
    "candidate_finding_severity_invalid", "candidate_finding_summary_invalid",
    "candidate_finding_evidence_invalid", "pass_contains_blocking_finding",
    "fail_requires_blocking_finding", "provider_binding_mismatch",
})
MAX_RETAINED_OUTPUT_BYTES = 64 * 1024
ACCEPTED_REASONS = {"valid_pass": "accepted_pass", "valid_fail": "accepted_fail"}
PROVIDER_EVIDENCE_LEVELS = {"ollama": "flow_observed_local_http_response",
                            "codex": "flow_observed_codex_cli_completed_turn",
                            "claude": "flow_observed_claude_cli_completed_turn",
                            "local-stub": "local_stub"}

# Flow appends this block to every protocol-v8 verifier input.  It is part of
# the persisted, digested input, so a receipt proves which contract was asked.
VERIFIER_CONTRACT_INSTRUCTION = (
    "\n\nFlow verifier output contract (schema_version 1):\n"
    "Reply with exactly one JSON object and nothing else: no prose, no code fence.\n"
    'Shape: {"schema_version": 1, "decision": "pass" | "fail", "summary": "<text>", '
    '"findings": [{"severity": "blocking" | "non_blocking", "summary": "<text>", "evidence": "<text>"}]}\n'
    "Rules: judge only the diff and test result supplied above; do not claim to have inspected anything else. "
    "A pass may contain only non_blocking findings. A fail must contain at least one blocking finding. "
    f"At most {MAX_FINDINGS} findings. Summary at most {MAX_SUMMARY_BYTES} bytes; each finding summary at most "
    f"{MAX_FINDING_SUMMARY_BYTES} bytes and evidence at most {MAX_FINDING_EVIDENCE_BYTES} bytes. "
    "Every text field must be non-empty. Flow treats any other output as unusable.\n"
)


class VerifierContractError(ValueError):
    """A verifier candidate or Flow evaluation is invalid."""


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise VerifierContractError(f"record is not canonical JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise VerifierContractError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _bounded_text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > maximum:
        raise VerifierContractError(f"{field} is empty or exceeds its size limit")
    return value


def parse_candidate(raw_output: str) -> dict[str, Any]:
    """Parse one bounded JSON candidate without treating it as a verdict yet."""
    _bounded_text(raw_output, "raw output", MAX_RAW_OUTPUT_BYTES)
    try:
        candidate = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise VerifierContractError("candidate is not valid JSON") from exc
    if not isinstance(candidate, dict):
        raise VerifierContractError("candidate root must be an object")
    return candidate


def validate_candidate(candidate: object) -> dict[str, Any]:
    """Validate the closed provider candidate schema and its decision rules."""
    if not isinstance(candidate, dict) or set(candidate) != {"schema_version", "decision", "summary", "findings"}:
        raise VerifierContractError("candidate fields are invalid")
    if type(candidate["schema_version"]) is not int or candidate["schema_version"] != VERIFIER_VERDICT_SCHEMA_VERSION:
        raise VerifierContractError("candidate schema version is unsupported")
    if not isinstance(candidate["decision"], str) or candidate["decision"] not in VALID_DECISIONS:
        raise VerifierContractError("candidate decision is invalid")
    _bounded_text(candidate["summary"], "candidate summary", MAX_SUMMARY_BYTES)
    findings = candidate["findings"]
    if not isinstance(findings, list) or len(findings) > MAX_FINDINGS:
        raise VerifierContractError("candidate findings are invalid")
    blocking = 0
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != {"severity", "summary", "evidence"}:
            raise VerifierContractError("candidate finding fields are invalid")
        if not isinstance(finding["severity"], str) or finding["severity"] not in VALID_SEVERITIES:
            raise VerifierContractError("candidate finding severity is invalid")
        _bounded_text(finding["summary"], "candidate finding summary", MAX_FINDING_SUMMARY_BYTES)
        _bounded_text(finding["evidence"], "candidate finding evidence", MAX_FINDING_EVIDENCE_BYTES)
        blocking += finding["severity"] == "blocking"
    if candidate["decision"] == "pass" and blocking:
        raise VerifierContractError("pass candidate cannot contain blocking findings")
    if candidate["decision"] == "fail" and not blocking:
        raise VerifierContractError("fail candidate requires a blocking finding")
    return candidate


def _unusable_reason(exc: VerifierContractError) -> str:
    """Translate validation failures to durable, provider-neutral reason codes."""
    message = str(exc)
    if message == "candidate is not valid JSON":
        return "candidate_json_invalid"
    if message == "candidate root must be an object":
        return "candidate_root_invalid"
    if message == "candidate fields are invalid":
        return "candidate_fields_invalid"
    if message == "candidate schema version is unsupported":
        return "candidate_schema_version_unsupported"
    if message == "candidate decision is invalid":
        return "candidate_decision_invalid"
    if message == "candidate summary is empty or exceeds its size limit":
        return "candidate_summary_invalid"
    if message == "candidate findings are invalid":
        return "candidate_findings_invalid"
    if message == "candidate finding fields are invalid":
        return "candidate_finding_fields_invalid"
    if message == "candidate finding severity is invalid":
        return "candidate_finding_severity_invalid"
    if message == "candidate finding summary is empty or exceeds its size limit":
        return "candidate_finding_summary_invalid"
    if message == "candidate finding evidence is empty or exceeds its size limit":
        return "candidate_finding_evidence_invalid"
    if message == "pass candidate cannot contain blocking findings":
        return "pass_contains_blocking_finding"
    if message == "fail candidate requires a blocking finding":
        return "fail_requires_blocking_finding"
    return "raw_output_invalid"


def evaluate_candidate(*, action_id: str, verifier_input_digest: str, raw_output: str,
                       diff_digest: str, test_evidence_digest: str,
                       forced_unusable_reason: str | None = None) -> dict[str, Any]:
    """Return Flow's evidence-bound evaluation for a completed provider result.

    Invalid provider content becomes a durable ``unusable`` evaluation.  It is
    intentionally not a transport-unknown state.
    """
    if not isinstance(action_id, str) or not action_id.strip():
        raise VerifierContractError("action_id must be a non-empty string")
    if not isinstance(raw_output, str):
        raise VerifierContractError("raw output must be a string")
    bindings = {
        "action_id": action_id,
        "verifier_input_digest": _digest(verifier_input_digest, "verifier_input_digest"),
        "raw_output_digest": hashlib.sha256(raw_output.encode("utf-8")).hexdigest(),
        "diff_digest": _digest(diff_digest, "diff_digest"),
        "test_evidence_digest": _digest(test_evidence_digest, "test_evidence_digest"),
    }
    verdict: dict[str, Any] | None = None
    if forced_unusable_reason is not None:
        if forced_unusable_reason not in FORCED_UNUSABLE_REASONS:
            raise VerifierContractError("forced unusable reason is invalid")
        disposition, reason = "unusable", forced_unusable_reason
    else:
        try:
            verdict = validate_candidate(parse_candidate(raw_output))
        except VerifierContractError as exc:
            disposition, reason = "unusable", _unusable_reason(exc)
        else:
            disposition = "valid_pass" if verdict["decision"] == "pass" else "valid_fail"
            reason = "accepted_pass" if disposition == "valid_pass" else "accepted_fail"
    evaluation = {
        "schema_version": VERIFIER_EVALUATION_SCHEMA_VERSION,
        "kind": "flow_verifier_evaluation",
        **bindings,
        "disposition": disposition,
        "reason": reason,
        "candidate": verdict,
    }
    evaluation["evaluation_digest"] = digest(evaluation)
    return evaluation


def validate_evaluation(evaluation: object) -> dict[str, Any]:
    """Validate a persisted Flow evaluation, including its immutable digest."""
    required = {"schema_version", "kind", "action_id", "verifier_input_digest", "raw_output_digest",
                "diff_digest", "test_evidence_digest", "disposition", "reason", "candidate", "evaluation_digest"}
    if not isinstance(evaluation, dict) or set(evaluation) != required:
        raise VerifierContractError("evaluation fields are invalid")
    if evaluation["schema_version"] != VERIFIER_EVALUATION_SCHEMA_VERSION or evaluation["kind"] != "flow_verifier_evaluation":
        raise VerifierContractError("evaluation schema version is unsupported")
    if not isinstance(evaluation["action_id"], str) or not evaluation["action_id"].strip():
        raise VerifierContractError("evaluation action_id is invalid")
    for field in ("verifier_input_digest", "raw_output_digest", "diff_digest", "test_evidence_digest", "evaluation_digest"):
        _digest(evaluation[field], field)
    if evaluation["disposition"] not in VALID_DISPOSITIONS or not isinstance(evaluation["reason"], str) or not evaluation["reason"]:
        raise VerifierContractError("evaluation disposition or reason is invalid")
    allowed_reasons = ({ACCEPTED_REASONS[evaluation["disposition"]]} if evaluation["disposition"] != "unusable"
                       else UNUSABLE_REASON_CODES)
    if evaluation["reason"] not in allowed_reasons:
        raise VerifierContractError("evaluation reason is invalid")
    if evaluation["disposition"] == "unusable":
        if evaluation["candidate"] is not None:
            raise VerifierContractError("unusable evaluation cannot contain a candidate")
    else:
        candidate = validate_candidate(evaluation["candidate"])
        expected = "valid_pass" if candidate["decision"] == "pass" else "valid_fail"
        if evaluation["disposition"] != expected:
            raise VerifierContractError("evaluation disposition contradicts candidate")
    sealed = dict(evaluation)
    actual = sealed.pop("evaluation_digest")
    if actual != digest(sealed):
        raise VerifierContractError("evaluation digest mismatch")
    return evaluation


def provider_binding_mismatch(action: dict[str, Any], result: dict[str, Any]) -> bool:
    """Whether a received result contradicts the approved verifier binding."""
    return (result.get("provider") != action.get("provider")
            or result.get("model") != action.get("model")
            or result.get("physical_call") != (action.get("provider") != "local-stub")
            or result.get("evidence_level") != PROVIDER_EVIDENCE_LEVELS.get(action.get("provider")))


def validate_structured_verifier_result(result: object) -> dict[str, Any]:
    """Validate the observed shape of a v8 verifier result, not its binding.

    Unlike ordinary specialist results, empty output and mismatched provider
    facts are retained so Flow can record them as a completed, unusable call.
    """
    if (not isinstance(result, dict) or result.get("schema_version") != 1 or result.get("status") != "completed"
            or not isinstance(result.get("provider"), str) or not result["provider"]
            or not isinstance(result.get("model"), str) or not result["model"]
            or type(result.get("physical_call")) is not bool
            or not isinstance(result.get("evidence_level"), str) or not result["evidence_level"]):
        raise VerifierContractError("structured verifier response is invalid")
    output = result.get("output")
    if (not isinstance(output, str) or len(output.encode("utf-8")) > MAX_RETAINED_OUTPUT_BYTES
            or result.get("output_sha256") != hashlib.sha256(output.encode("utf-8")).hexdigest()):
        raise VerifierContractError("structured verifier response is invalid")
    usage = result.get("usage")
    if usage is not None and (not isinstance(usage, dict) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in usage.values())):
        raise VerifierContractError("structured verifier response usage is invalid")
    return result
