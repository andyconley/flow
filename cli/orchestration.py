"""Structural validation for Flow orchestration contracts.

The validator deliberately proves declarations, not hidden runtime state or
semantic truth.  It never reads referenced artifact contents; existence and
declared relationships are the enforceable boundary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple

from fsutil import repo_root


SCHEMA_VERSION = 1
MANIFEST_FILE = "orchestration.json"
STAGES = ("dispatch", "handback", "acceptance")
MODES = {"single", "delegated", "shared-mutation"}
CAPABILITY_STATES = {"confirmed", "missing", "unknown"}
CLAIM_STATUSES = {"observed", "inferred", "recommended", "unverified"}
CLAIM_DISPOSITIONS = {"accepted", "rejected", "deferred"}
IDENTITY_KINDS = {"human", "agent", "external_provider"}
MUTATION_TYPES = {"additive", "structural", "destructive", "read-only"}
RECOVERY_STATES = {
    "exercised",
    "available_unexercised",
    "irreversible_acknowledged",
}
UNEXPECTED_DELTA_STATES = {"none", "resolved", "accepted", "unresolved"}
HARD_TRIGGERS = {
    "destructive_or_irreversible",
    "production_or_shared_external_mutation",
    "security_or_privacy_boundary",
    "loss_bearing_data_migration",
    "regulated_personnel_safety_or_customer_access",
}
AGGRAVATING_FACTORS = {
    "large_blast_radius",
    "weak_rollback",
    "weak_or_delayed_observability",
    "concurrency_or_cross_system_coordination",
    "material_unresolved_ambiguity",
    "author_only_validation",
    "unverified_claim_for_durable_truth",
}


def valid_work_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
        and "\x00" not in value
    )


def _enum(value: Any, allowed: set[str]) -> bool:
    return isinstance(value, str) and value in allowed


class Finding(NamedTuple):
    field: str
    subject: str
    rule: str
    message: str
    action: str


def manifest_path(work_id: str, root: Path | None = None) -> Path:
    if not valid_work_id(work_id):
        raise ValueError("work id must be a non-empty run-directory name and may not contain path separators")
    return (root or repo_root()) / ".flow" / "runs" / work_id / MANIFEST_FILE


def calculated_risk(hard_triggers: list[str], aggravating_factors: list[str]) -> str:
    return "high" if hard_triggers or len(aggravating_factors) >= 2 else "standard"


def _finding(
    findings: list[Finding],
    field: str,
    subject: str,
    rule: str,
    message: str,
    action: str,
) -> None:
    findings.append(Finding(field, subject, rule, message, action))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _safe_repo_path(raw: Any, root: Path) -> Path | None:
    if not _nonempty(raw):
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _path_exists(
    findings: list[Finding], root: Path, raw: Any, field: str, subject: str
) -> Path | None:
    path = _safe_repo_path(raw, root)
    if path is None:
        _finding(
            findings,
            field,
            subject,
            "safe-repository-path",
            "the declared path is empty, absolute, or escapes the repository",
            "use a repository-relative path without parent traversal",
        )
    elif not path.is_file():
        _finding(
            findings,
            field,
            subject,
            "referenced-artifact-exists",
            "the referenced artifact is missing or is not a regular file",
            "create the file at the declared path before this stage",
        )
    return path


def _path_within(path: Path, scope: Path) -> bool:
    return path == scope or scope in path.parents


def _paths_overlap(left: Path, right: Path) -> bool:
    return _path_within(left, right) or _path_within(right, left)


def _identity_key(value: Any) -> tuple[str, str] | None:
    identity = _dict(value)
    kind = identity.get("kind")
    identifier = identity.get("id")
    if not _enum(kind, IDENTITY_KINDS) or not _nonempty(identifier):
        return None
    return kind, identifier.strip()


def _validate_identity(
    findings: list[Finding], value: Any, field: str, subject: str
) -> tuple[str, str] | None:
    key = _identity_key(value)
    if key is None:
        _finding(
            findings,
            field,
            subject,
            "identity-provenance",
            "identity must declare a supported kind and a non-empty id",
            "set kind to human, agent, or external_provider and record the stable id",
        )
    return key


def _validate_common(
    data: Any, work_id: str, root: Path, findings: list[Finding]
) -> tuple[dict[str, Any], str]:
    if not isinstance(data, dict):
        _finding(
            findings,
            "$",
            work_id,
            "manifest-object",
            "the orchestration manifest must be a JSON object",
            "replace it with an object using the orchestration template",
        )
        return {}, "standard"
    if data.get("schema_version") != SCHEMA_VERSION:
        _finding(
            findings,
            "schema_version",
            work_id,
            "supported-schema",
            f"schema_version must be {SCHEMA_VERSION}",
            f"set schema_version to {SCHEMA_VERSION}",
        )
    if data.get("work_id") != work_id:
        _finding(
            findings,
            "work_id",
            work_id,
            "containing-run-identity",
            "work_id does not match the containing run",
            f"set work_id to {work_id}",
        )
    if not _enum(data.get("mode"), MODES):
        _finding(
            findings,
            "mode",
            work_id,
            "controlled-mode",
            "mode is not a supported value",
            "use single, delegated, or shared-mutation",
        )

    if not isinstance(data.get("risk"), dict):
        _finding(findings, "risk", work_id, "risk-object", "risk must be an object", "declare controlled triggers, calculated classification, and rationale")
    risk = _dict(data.get("risk"))
    if not isinstance(risk.get("hard_triggers"), list):
        _finding(findings, "risk.hard_triggers", work_id, "risk-trigger-list", "hard_triggers must be a list", "declare zero or more controlled hard triggers")
    if not isinstance(risk.get("aggravating_factors"), list):
        _finding(findings, "risk.aggravating_factors", work_id, "risk-factor-list", "aggravating_factors must be a list", "declare zero or more controlled aggravating factors")
    hard = _list(risk.get("hard_triggers"))
    factors = _list(risk.get("aggravating_factors"))
    for index, value in enumerate(hard):
        if not _enum(value, HARD_TRIGGERS):
            _finding(
                findings,
                f"risk.hard_triggers[{index}]",
                work_id,
                "controlled-risk-trigger",
                "hard trigger is not recognized",
                "use a hard trigger defined by the orchestration standard",
            )
    for index, value in enumerate(factors):
        if not _enum(value, AGGRAVATING_FACTORS):
            _finding(
                findings,
                f"risk.aggravating_factors[{index}]",
                work_id,
                "controlled-risk-factor",
                "aggravating factor is not recognized",
                "use an aggravating factor defined by the orchestration standard",
            )
    expected = calculated_risk(hard, factors)
    if risk.get("classification") != expected:
        _finding(
            findings,
            "risk.classification",
            work_id,
            "calculated-risk",
            f"stored classification conflicts with calculated classification {expected}",
            f"set classification to {expected} or correct the controlled triggers",
        )
    if not _nonempty(risk.get("rationale")):
        _finding(
            findings,
            "risk.rationale",
            work_id,
            "risk-rationale",
            "risk rationale is missing",
            "record why the selected triggers apply",
        )
    return data, expected


def _validate_dispatch(
    data: dict[str, Any], root: Path, findings: list[Finding]
) -> None:
    assignments = data.get("assignments")
    if not isinstance(assignments, list) or not assignments:
        _finding(
            findings,
            "assignments",
            "manifest",
            "assignment-required",
            "at least one assignment is required",
            "add a complete provider assignment",
        )
        return
    if data.get("mode") == "delegated" and len(assignments) < 2:
        _finding(findings, "assignments", "manifest", "delegated-provider-count", "delegated mode has fewer than two assignments", "declare the delegated provider assignment or use single mode")

    seen: set[str] = set()
    writable: list[tuple[str, Path, str, bool]] = []
    assignment_ids: set[str] = set()
    for index, raw in enumerate(assignments):
        field = f"assignments[{index}]"
        item = _dict(raw)
        assignment_id = item.get("id")
        subject = assignment_id if _nonempty(assignment_id) else field
        if not _nonempty(assignment_id) or assignment_id in seen:
            _finding(
                findings,
                f"{field}.id",
                subject,
                "unique-assignment-id",
                "assignment id is missing or duplicated",
                "provide a stable id unique within the manifest",
            )
        else:
            seen.add(assignment_id)
            assignment_ids.add(assignment_id)
        if not _nonempty(item.get("lane")) or not _nonempty(item.get("role")):
            _finding(
                findings,
                field,
                subject,
                "provider-role",
                "lane and role are required",
                "declare the Flow lane and provider role",
            )
        _validate_identity(findings, item.get("provider"), f"{field}.provider", subject)
        _path_exists(findings, root, item.get("brief_path"), f"{field}.brief_path", subject)
        if not isinstance(item.get("input_evidence"), list):
            _finding(findings, f"{field}.input_evidence", subject, "input-evidence-list", "input evidence must be a list", "declare the evidence inventory paths")
        for evidence_index, evidence in enumerate(_list(item.get("input_evidence"))):
            _path_exists(
                findings,
                root,
                evidence,
                f"{field}.input_evidence[{evidence_index}]",
                subject,
            )
        read_scopes = item.get("read_scopes")
        if not isinstance(read_scopes, list) or not read_scopes:
            _finding(findings, f"{field}.read_scopes", subject, "read-scope-inventory", "read scopes are missing", "declare the repository areas the provider may inspect")
        for scope_index, scope in enumerate(_list(read_scopes)):
            if _safe_repo_path(scope, root) is None:
                _finding(findings, f"{field}.read_scopes[{scope_index}]", subject, "safe-read-scope", "read scope is empty, absolute, or escapes the repository", "use a repository-relative read scope")
        read_only = item.get("read_only") is True
        write_scopes = _list(item.get("write_scopes"))
        if read_only and write_scopes:
            _finding(
                findings,
                f"{field}.write_scopes",
                subject,
                "read-only-write-scope",
                "a read-only assignment declares write scopes",
                "remove product write scopes or set read_only to false",
            )
        if not read_only and not write_scopes:
            _finding(
                findings,
                f"{field}.write_scopes",
                subject,
                "writable-scope-required",
                "a writable assignment has no write scope",
                "declare the exact repository write scope",
            )
        scope_paths: list[Path] = []
        for scope_index, scope in enumerate(write_scopes):
            path = _safe_repo_path(scope, root)
            if path is None:
                _finding(
                    findings,
                    f"{field}.write_scopes[{scope_index}]",
                    subject,
                    "safe-write-scope",
                    "write scope is empty, absolute, or escapes the repository",
                    "use a repository-relative scope without parent traversal",
                )
            else:
                scope_paths.append(path)
        coordination = _dict(item.get("coordination"))
        group = coordination.get("group")
        serialized = coordination.get("mode") == "serialized"
        if not _enum(coordination.get("mode"), {"concurrent", "serialized"}) or not _nonempty(group):
            _finding(
                findings,
                f"{field}.coordination",
                subject,
                "coordination-contract",
                "coordination must declare concurrent or serialized mode and a group",
                "declare the execution mode and stable coordination group",
            )
        for scope_path in scope_paths:
            writable.append((subject, scope_path, str(group), serialized))

        capabilities = item.get("required_capabilities")
        if not isinstance(capabilities, list):
            _finding(
                findings,
                f"{field}.required_capabilities",
                subject,
                "capability-inventory",
                "required capabilities must be a list",
                "declare each required capability and its observed status",
            )
        for capability_index, capability_raw in enumerate(_list(capabilities)):
            capability = _dict(capability_raw)
            cap_field = f"{field}.required_capabilities[{capability_index}]"
            if not _nonempty(capability.get("name")):
                _finding(findings, f"{cap_field}.name", subject, "capability-name", "capability name is missing", "name the required capability")
            status = capability.get("status")
            if not _enum(status, CAPABILITY_STATES):
                _finding(findings, f"{cap_field}.status", subject, "capability-status", "capability status is not recognized", "use confirmed, missing, or unknown")
            elif status != "confirmed":
                _finding(findings, f"{cap_field}.status", subject, "required-capability-confirmed", f"required capability is {status}", "confirm the capability before dispatch or change the assignment")

        output = _dict(item.get("output"))
        output_path = _safe_repo_path(output.get("path"), root)
        if output_path is None or not _nonempty(output.get("format")):
            _finding(findings, f"{field}.output", subject, "declared-output", "output requires a safe path and format", "declare the output path and format")
        elif read_only:
            run_output_root = root / ".flow" / "runs" / str(data.get("work_id"))
            if not _path_within(output_path, run_output_root):
                _finding(findings, f"{field}.output.path", subject, "read-only-run-output", "read-only assignment output is outside its run artifact directory", "write the report under the containing run")
        elif not any(_path_within(output_path, scope) for scope in scope_paths):
            _finding(findings, f"{field}.output.path", subject, "output-within-write-scope", "output is not inside a declared write scope", "expand the write scope explicitly or move the output")
        if not _list(item.get("success_criteria")):
            _finding(findings, f"{field}.success_criteria", subject, "success-criteria", "success criteria are missing", "add one or more observable success criteria")
        statuses = _list(item.get("claim_statuses"))
        if not statuses or any(not _enum(value, CLAIM_STATUSES) for value in statuses):
            _finding(findings, f"{field}.claim_statuses", subject, "claim-status-expectation", "claim status expectations are missing or invalid", "declare one or more supported claim statuses")

    for left_index, left in enumerate(writable):
        for right in writable[left_index + 1 :]:
            if left[0] == right[0] or not _paths_overlap(left[1], right[1]):
                continue
            if left[2] == right[2] and left[3] and right[3]:
                continue
            _finding(
                findings,
                "assignments.write_scopes",
                f"{left[0]} / {right[0]}",
                "concurrent-write-overlap",
                "assignment write scopes overlap without shared serialization",
                "make the scopes disjoint or serialize both assignments in one group",
            )

    _validate_shared_dispatch(data, assignment_ids, findings)
    if any(
        _dict(target).get("mutation_type") != "read-only"
        for target in _list(data.get("shared_state"))
    ) and "production_or_shared_external_mutation" not in _list(
        _dict(data.get("risk")).get("hard_triggers")
    ):
        _finding(
            findings,
            "risk.hard_triggers",
            "manifest",
            "shared-mutation-risk-trigger",
            "a shared mutation is declared without its required hard trigger",
            "add production_or_shared_external_mutation and store the calculated high classification",
        )


def _validate_shared_dispatch(
    data: dict[str, Any], assignment_ids: set[str], findings: list[Finding]
) -> None:
    targets = data.get("shared_state", [])
    if not isinstance(targets, list):
        _finding(findings, "shared_state", "manifest", "shared-state-list", "shared_state must be a list", "declare zero or more shared targets")
        return
    if data.get("mode") == "shared-mutation" and not targets:
        _finding(findings, "shared_state", "manifest", "shared-target-required", "shared-mutation mode has no shared target", "declare each shared target or use another mode")
    seen: set[str] = set()
    parsed: list[tuple[str, str, str, str, bool, str]] = []
    for index, raw in enumerate(targets):
        field = f"shared_state[{index}]"
        item = _dict(raw)
        target_id = item.get("id")
        subject = target_id if _nonempty(target_id) else field
        if not _nonempty(target_id) or target_id in seen:
            _finding(findings, f"{field}.id", subject, "unique-target-id", "shared target id is missing or duplicated", "provide a stable unique target id")
        else:
            seen.add(target_id)
        if not _nonempty(item.get("kind")) or not _nonempty(item.get("identity")):
            _finding(findings, field, subject, "exact-target-identity", "target kind and exact identity are required", "record the target kind and stable exact identity")
        mutation = item.get("mutation_type")
        if not _enum(mutation, MUTATION_TYPES):
            _finding(findings, f"{field}.mutation_type", subject, "controlled-mutation-type", "mutation type is not recognized", "use additive, structural, destructive, or read-only")
        if not _nonempty(item.get("owner_assignment")) or item.get("owner_assignment") not in assignment_ids:
            _finding(findings, f"{field}.owner_assignment", subject, "known-assignment-owner", "target owner does not name a declared assignment", "set the owner to a declared assignment id")
        if not _nonempty(item.get("write_region")):
            _finding(findings, f"{field}.write_region", subject, "declared-write-region", "write region is missing", "declare the exact external region or read-only extent")
        coordination = _dict(item.get("coordination"))
        if not _enum(coordination.get("mode"), {"concurrent", "serialized"}) or not _nonempty(coordination.get("group")):
            _finding(findings, f"{field}.coordination", subject, "shared-coordination", "coordination must declare mode and group", "declare concurrent or serialized coordination")
        parsed.append((subject, str(item.get("identity")), str(item.get("write_region")), str(coordination.get("group")), coordination.get("mode") == "serialized", str(mutation)))
    for left_index, left in enumerate(parsed):
        for right in parsed[left_index + 1 :]:
            if left[1] != right[1]:
                continue
            if left[3] == right[3] and left[4] and right[4]:
                continue
            both_additive = left[5] == right[5] == "additive"
            if both_additive and left[2] != right[2]:
                continue
            if "read-only" in {left[5], right[5]}:
                continue
            _finding(findings, "shared_state", f"{left[0]} / {right[0]}", "shared-region-conflict", "shared-target mutations conflict without serialization", "serialize structural or destructive operations; additive operations may instead declare non-overlapping regions")


def _validate_handback(
    data: dict[str, Any], root: Path, findings: list[Finding]
) -> None:
    for index, raw in enumerate(_list(data.get("assignments"))):
        item = _dict(raw)
        subject = item.get("id", f"assignments[{index}]")
        output = _dict(item.get("output"))
        _path_exists(findings, root, output.get("path"), f"assignments[{index}].output.path", subject)

    reconciliation = _dict(data.get("reconciliation"))
    _path_exists(findings, root, reconciliation.get("artifact_path"), "reconciliation.artifact_path", "reconciliation")
    if reconciliation.get("status") != "resolved":
        _finding(findings, "reconciliation.status", "reconciliation", "resolved-reconciliation", "reconciliation is not resolved", "resolve or explicitly disposition every material conflict")
    claims = _list(reconciliation.get("claims"))
    claim_by_id = {
        claim.get("id"): claim
        for claim in (_dict(raw) for raw in claims)
        if _nonempty(claim.get("id"))
    }
    if len(claim_by_id) != len([claim for claim in claims if _nonempty(_dict(claim).get("id"))]):
        _finding(findings, "reconciliation.claims", "reconciliation", "unique-claim-id", "material claim ids are duplicated", "give every material claim a stable unique id")
    for index, raw in enumerate(claims):
        claim = _dict(raw)
        subject = claim.get("id", f"claim[{index}]")
        status = claim.get("status")
        if not _enum(status, CLAIM_STATUSES):
            _finding(findings, f"reconciliation.claims[{index}].status", subject, "claim-status", "claim status is not recognized", "use observed, inferred, recommended, or unverified")
        if status == "observed":
            evidence = _list(claim.get("evidence"))
            if not evidence:
                _finding(findings, f"reconciliation.claims[{index}].evidence", subject, "observed-evidence", "observed claim has no evidence reference", "cite the observation evidence")
            for evidence_index, evidence_path in enumerate(evidence):
                _path_exists(findings, root, evidence_path, f"reconciliation.claims[{index}].evidence[{evidence_index}]", subject)
        if status == "inferred":
            supports = _list(claim.get("supports"))
            if not supports or any(not _nonempty(support) or _dict(claim_by_id.get(support)).get("status") != "observed" for support in supports):
                _finding(findings, f"reconciliation.claims[{index}].supports", subject, "inference-support", "inferred claim does not link declared observed claims", "link one or more observed claim ids")
        if status == "recommended" and _identity_key(claim.get("decision_owner")) is None:
            _finding(findings, f"reconciliation.claims[{index}].decision_owner", subject, "recommendation-owner", "recommended claim lacks decision ownership", "record the accountable identity")
        disposition = claim.get("disposition")
        if not _enum(disposition, CLAIM_DISPOSITIONS):
            _finding(findings, f"reconciliation.claims[{index}].disposition", subject, "claim-disposition", "material claim has no supported disposition", "set accepted, rejected, or deferred")
        if status == "unverified" and disposition == "accepted":
            _finding(findings, f"reconciliation.claims[{index}].disposition", subject, "unverified-not-fact", "an unverified claim cannot be accepted as durable fact", "verify it, reject it, or defer it")

    for index, raw in enumerate(_list(data.get("shared_state"))):
        item = _dict(raw)
        if item.get("mutation_type") == "read-only":
            continue
        subject = item.get("id", f"shared_state[{index}]")
        for key in ("baseline_artifact", "execution_result_artifact", "readback_artifact", "comparison_artifact"):
            _path_exists(findings, root, item.get(key), f"shared_state[{index}].{key}", subject)
        if not _nonempty(item.get("baseline_captured_at")) or not _nonempty(item.get("baseline_source_identity")):
            _finding(findings, f"shared_state[{index}].baseline", subject, "fresh-baseline-provenance", "baseline capture time or source identity is missing", "record the immediately pre-write capture time and source identity")
        if not _nonempty(item.get("expected_delta")):
            _finding(findings, f"shared_state[{index}].expected_delta", subject, "expected-delta", "expected delta is missing", "state the exact intended change")
        recovery = item.get("recovery_state")
        if not _enum(recovery, RECOVERY_STATES):
            _finding(findings, f"shared_state[{index}].recovery_state", subject, "recovery-posture", "recovery state is not recognized", "record exercised, available_unexercised, or irreversible_acknowledged")
        if item.get("mutation_type") == "destructive" and not _enum(recovery, {"exercised", "irreversible_acknowledged"}):
            _finding(findings, f"shared_state[{index}].recovery_state", subject, "destructive-recovery", "destructive mutation lacks exercised recovery or irreversible acknowledgment", "exercise recovery or record the acknowledgment and safeguards")
        if recovery == "irreversible_acknowledged" and not _nonempty(item.get("recovery_safeguards")):
            _finding(findings, f"shared_state[{index}].recovery_safeguards", subject, "irreversible-safeguards", "irreversible acknowledgment has no recorded safeguards", "record the safeguards and accountable acknowledgment")
        delta = item.get("unexpected_delta_status")
        if not _enum(delta, UNEXPECTED_DELTA_STATES):
            _finding(findings, f"shared_state[{index}].unexpected_delta_status", subject, "unexpected-delta-status", "unexpected delta status is not recognized", "use none, resolved, accepted, or unresolved")
        elif delta == "unresolved" or (_enum(delta, {"resolved", "accepted"}) and not _nonempty(item.get("unexpected_delta_disposition"))):
            _finding(findings, f"shared_state[{index}].unexpected_delta_disposition", subject, "unexpected-delta-disposition", "unexpected delta is unresolved or lacks a disposition", "resolve and record the disposition before handback")


def _validate_acceptance(
    data: dict[str, Any], root: Path, risk: str, findings: list[Finding]
) -> None:
    verification = _dict(data.get("verification"))
    assignments_by_id = {
        assignment.get("id"): assignment
        for assignment in (_dict(raw) for raw in _list(data.get("assignments")))
        if _nonempty(assignment.get("id"))
    }
    assignment_providers = {
        assignment_id: _identity_key(assignment.get("provider"))
        for assignment_id, assignment in assignments_by_id.items()
    }
    producers = verification.get("producer_assignments")
    if not isinstance(producers, list) or not producers:
        _finding(findings, "verification.producer_assignments", "verification", "producer-assignment-inventory", "producer assignments are missing", "list every assignment that produced the accepted work")
        producer_ids: list[str] = []
    else:
        producer_ids = [value for value in producers if _nonempty(value)]
        if len(producer_ids) != len(producers) or len(set(producer_ids)) != len(producer_ids):
            _finding(findings, "verification.producer_assignments", "verification", "producer-assignment-inventory", "producer assignments contain invalid or duplicate ids", "list each producer assignment id exactly once")
    collector_id = verification.get("evidence_collector_assignment")
    verifier_id = verification.get("verifier_assignment")
    collector_key = collector_id if _nonempty(collector_id) else None
    verifier_key = verifier_id if _nonempty(verifier_id) else None
    for field, assignment_ids in (
        ("verification.producer_assignments", producer_ids),
        ("verification.evidence_collector_assignment", [collector_key]),
        ("verification.verifier_assignment", [verifier_key]),
    ):
        for assignment_id in assignment_ids:
            if not _nonempty(assignment_id) or assignment_id not in assignment_providers:
                _finding(findings, field, "verification", "declared-verification-assignment", "verification role does not reference a declared assignment", "reference the stable id of the assignment that performed this role")
    producer_identities = {assignment_providers.get(value) for value in producer_ids} - {None}
    collector = assignment_providers.get(collector_key)
    verifier = assignment_providers.get(verifier_key)
    mutable_owners = {
        target.get("owner_assignment")
        for target in (_dict(raw) for raw in _list(data.get("shared_state")))
        if target.get("mutation_type") != "read-only" and _nonempty(target.get("owner_assignment"))
    }
    if not mutable_owners.issubset(set(producer_ids)):
        _finding(findings, "verification.producer_assignments", "verification", "shared-mutation-producer-binding", "a shared-mutation owner is not recorded as a producer", "include every mutable target owner assignment in producer_assignments")
    writable_assignments = {
        assignment_id
        for assignment_id, assignment in assignments_by_id.items()
        if assignment.get("read_only") is not True
    }
    if not writable_assignments.issubset(set(producer_ids)):
        _finding(findings, "verification.producer_assignments", "verification", "writable-producer-binding", "a writable assignment is not recorded as a producer", "include every writable assignment that produced run output")
    artifact = verification.get("artifact_path")
    if risk == "high":
        _path_exists(findings, root, artifact, "verification.artifact_path", "verification")
        if verifier_key in producer_ids or (verifier is not None and verifier in producer_identities):
            _finding(findings, "verification.verifier_assignment", "verification", "independent-high-risk-verifier", "high-risk verifier assignment or provider also produced the work", "assign a verifier with a distinct assignment and stable provider identity")
        if verifier_key == collector_key or (collector is not None and verifier == collector):
            _finding(findings, "verification.verifier_assignment", "verification", "independent-high-risk-verifier", "high-risk verifier assignment or provider also collected the certified evidence", "assign a verifier who did not collect the certified evidence")
        if _dict(assignments_by_id.get(verifier_key)).get("read_only") is not True:
            _finding(findings, "verification.verifier_assignment", "verification", "read-only-high-risk-verifier", "high-risk verifier assignment is writable", "use a read-only review assignment for independent verification")
        if verification.get("independent") is not True:
            _finding(findings, "verification.independent", "verification", "recorded-verifier-independence", "high-risk verification is not marked independent", "record true after checking identity separation")
    elif artifact:
        _path_exists(findings, root, artifact, "verification.artifact_path", "verification")


def validate_manifest(
    data: Any, work_id: str, stage: str, *, root: Path | None = None
) -> list[Finding]:
    if stage not in STAGES:
        raise ValueError(f"unsupported orchestration stage: {stage}")
    project_root = (root or repo_root()).resolve()
    findings: list[Finding] = []
    manifest, risk = _validate_common(data, work_id, project_root, findings)
    _validate_dispatch(manifest, project_root, findings)
    if stage in {"handback", "acceptance"}:
        _validate_handback(manifest, project_root, findings)
    if stage == "acceptance":
        _validate_acceptance(manifest, project_root, risk, findings)
    return findings


def validate_orchestration(
    work_id: str, stage: str, *, root: Path | None = None
) -> tuple[bool, Path, list[Finding]]:
    if not valid_work_id(work_id):
        project_root = (root or repo_root()).resolve()
        path = project_root / ".flow" / "runs" / "__invalid_work_id__" / MANIFEST_FILE
        finding = Finding(
            "work_id",
            "invalid",
            "safe-work-id",
            "the work id is not a safe run-directory name",
            "use a non-empty single directory name without path separators",
        )
        return False, path, [finding]
    path = manifest_path(work_id, root)
    run_dir = path.parent
    if not run_dir.exists():
        finding = Finding(
            "run",
            work_id,
            "orchestration-run-exists",
            "the workflow run does not exist",
            f"create or transition run {work_id} before validating its contract",
        )
        return False, path, [finding]
    if not path.exists():
        finding = Finding(
            "manifest",
            work_id,
            "orchestration-manifest-exists",
            "the run has no orchestration manifest",
            f"create {path.relative_to((root or repo_root()).resolve())} from the template",
        )
        return False, path, [finding]
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        finding = Finding(
            "manifest",
            work_id,
            "valid-json",
            f"the orchestration manifest is invalid JSON at line {exc.lineno}, column {exc.colno}",
            "repair the JSON syntax without adding comments",
        )
        return False, path, [finding]
    findings = validate_manifest(data, work_id, stage, root=root)
    return not findings, path, findings


def result_payload(ok: bool, stage: str, path: Path, findings: list[Finding]) -> dict[str, Any]:
    return {
        "ok": ok,
        "stage": stage,
        "manifest": str(path),
        "findings": [finding._asdict() for finding in findings],
        "limitations": [
            "external region overlap is declaration-level only",
            "runtime capability grants and semantic truth are not inspected",
        ],
    }


def cmd_validate(args) -> int:
    try:
        ok, path, findings = validate_orchestration(args.work_id, args.stage)
    except ValueError as exc:
        print(str(exc))
        return 1
    payload = result_payload(ok, args.stage, path, findings)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif ok:
        print(f"orchestration valid: {args.work_id} ({args.stage})")
        print(f"manifest: {path}")
    else:
        print(f"orchestration invalid: {args.work_id} ({args.stage})")
        print(f"manifest: {path}")
        for finding in findings:
            print(f"- {finding.field} [{finding.rule}]: {finding.message}; {finding.action}")
    if not args.json:
        print("limit: external region overlap is declaration-level only; runtime grants and semantic truth are not inspected")
    return 0 if ok else 1
