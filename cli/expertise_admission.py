"""Candidate-admission strategies over one validated ordered rank window."""
from __future__ import annotations

from typing import Any

from expertise_model import (
    SCHEMA_VERSION,
    ExpertiseContractError,
    digest,
    validate_admission_decision,
    validate_admission_input,
    validate_trigger_rule,
)


class ExpertiseAdmissionError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class SimilarityStrategy:
    revision = "similarity-admission-v1"

    def __init__(self, threshold: float) -> None:
        if not isinstance(threshold, (int, float)) or not -1.0 <= float(threshold) <= 1.0:
            raise ExpertiseAdmissionError("invalid_gate_output")
        self.threshold = float(threshold)

    def decide(self, admission_input: dict, identity_digest: str) -> dict:
        value = validate_admission_input(admission_input)
        maximum = value["limits"]["maximum_admitted_ids"]
        admitted: list[str] = []
        decisions: list[dict] = []
        for candidate in value["ranking"]["candidates"]:
            exact = candidate["structured_exact_match"]
            passes = exact or candidate["provider_score"] >= self.threshold
            if passes and len(admitted) < maximum:
                admitted.append(candidate["entry_id"])
                reason = "structured_exact_match" if exact else "similarity_threshold_met"
            elif passes:
                reason = "admitted_limit_reached"
            else:
                reason = "similarity_below_threshold"
            decisions.append({
                "entry_id": candidate["entry_id"], "admitted": candidate["entry_id"] in admitted,
                "reason": reason, "evidence_codes": [],
            })
        return validate_admission_decision({
            "schema_version": SCHEMA_VERSION,
            "state": "admitted" if admitted else "no_candidate_admitted",
            "strategy": self.revision,
            "admitted_ids": admitted,
            "candidate_decisions": decisions,
            "identity": identity_digest,
        }, [row["entry_id"] for row in value["ranking"]["candidates"]])


class TriggerRuleStrategy:
    revision = "trigger-rule-admission-v1"

    def __init__(self, rules: dict[str, dict]) -> None:
        self.rules = {entry_id: validate_trigger_rule(rule, entry_id=entry_id) for entry_id, rule in rules.items()}

    def decide(self, admission_input: dict, identity_digest: str) -> dict:
        value = validate_admission_input(admission_input)
        facts = {row["code"]: row["value"] for row in value["task_facts"]["facts"]}
        maximum = value["limits"]["maximum_admitted_ids"]
        admitted: list[str] = []
        decisions: list[dict] = []
        for candidate in value["ranking"]["candidates"]:
            entry_id = candidate["entry_id"]
            rule = self.rules.get(entry_id)
            if rule is None:
                raise ExpertiseAdmissionError("rule_coverage_missing")
            if rule["entry_digest"] != candidate["entry_digest"]:
                raise ExpertiseAdmissionError("rule_coverage_missing")
            if rule["trigger_digest"] != digest(candidate["trigger_view"]):
                raise ExpertiseAdmissionError("rule_coverage_missing")
            if rule["failure_mode_digest"] != digest(candidate["failure_mode_view"]):
                raise ExpertiseAdmissionError("rule_coverage_missing")
            mismatched: list[str] = []
            unknown: list[str] = []
            for clause in rule["clauses"]:
                observed = facts.get(clause["fact"], "unknown")
                if observed == "unknown":
                    unknown.append(clause["fact"])
                elif observed != clause["value"]:
                    mismatched.append(clause["fact"])
            if mismatched:
                passes, reason, evidence = False, "trigger_contradicted", mismatched
            elif unknown:
                passes = rule["unknown_policy"] == "admit_for_context"
                reason = "trigger_unknown_admitted" if passes else "trigger_unknown_rejected"
                evidence = unknown
            else:
                passes, reason, evidence = True, "trigger_satisfied", [row["fact"] for row in rule["clauses"]]
            if passes and len(admitted) < maximum:
                admitted.append(entry_id)
            elif passes:
                reason = "admitted_limit_reached"
            decisions.append({"entry_id": entry_id, "admitted": entry_id in admitted, "reason": reason, "evidence_codes": evidence})
        return validate_admission_decision({
            "schema_version": SCHEMA_VERSION,
            "state": "admitted" if admitted else "no_candidate_admitted",
            "strategy": self.revision,
            "admitted_ids": admitted,
            "candidate_decisions": decisions,
            "identity": identity_digest,
        }, [row["entry_id"] for row in value["ranking"]["candidates"]])
