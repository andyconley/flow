"""Flow-owned execution records. This module has no MAF dependency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from runner_limits import (MAX_ACTIONS, MAX_CONCURRENT, MAX_LINEAGE_TOKENS, MAX_MANAGER_CALLS, MAX_MANAGER_ROUNDS, MAX_REPLANS,
                           MAX_TOKEN_TRANCHES, MAX_VERIFIER_CALLS)
from runner_progress import classify as classify_progress

try:
    from verifier_contracts import (VERIFIER_CONTRACT_INSTRUCTION, VERIFIER_EVALUATION_SCHEMA_VERSION, evaluate_candidate,
                                    provider_binding_mismatch, validate_evaluation, validate_structured_verifier_result)
except ModuleNotFoundError:  # Package import used by isolated tests.
    from .verifier_contracts import (VERIFIER_CONTRACT_INSTRUCTION, VERIFIER_EVALUATION_SCHEMA_VERSION, evaluate_candidate,
                                     provider_binding_mismatch, validate_evaluation, validate_structured_verifier_result)

SCHEMA_VERSION = 1
EXECUTION_PROTOCOL_VERSION = 2
MIXED_PROTOCOL_VERSION = 3
CLAUDE_PROTOCOL_VERSION = 4
MAGENTIC_PROTOCOL_VERSION = 5
CHARTERED_PROTOCOL_VERSION = 6
DELIVERY_PROTOCOL_VERSION = 7
STRUCTURED_VERIFIER_PROTOCOL_VERSION = 8
MAX_TASK_BYTES = 4096
MAX_MESSAGE_BYTES = 65536
ALLOWED_PROVIDERS = frozenset({"ollama", "local-stub"})
MIXED_ASSIGNMENTS = (("test-engineer", "ollama"), ("lead-developer", "codex"))
CLAUDE_ASSIGNMENTS = (("test-engineer", "ollama"), ("quality-reviewer", "claude"))


def is_magentic_protocol(protocol_version: int) -> bool:
    """Whether an execution protocol uses the supervised Magentic boundary."""
    return protocol_version in {MAGENTIC_PROTOCOL_VERSION, CHARTERED_PROTOCOL_VERSION,
                                DELIVERY_PROTOCOL_VERSION, STRUCTURED_VERIFIER_PROTOCOL_VERSION}


def is_chartered_protocol(protocol_version: int) -> bool:
    """Whether an execution protocol carries a chartered specialist job."""
    return protocol_version in {CHARTERED_PROTOCOL_VERSION, DELIVERY_PROTOCOL_VERSION,
                                STRUCTURED_VERIFIER_PROTOCOL_VERSION}


def is_delivery_protocol(protocol_version: int) -> bool:
    """Whether an execution protocol projects sealed Delivery authority."""
    return protocol_version in {DELIVERY_PROTOCOL_VERSION, STRUCTURED_VERIFIER_PROTOCOL_VERSION}


def has_structured_verifier_evaluations(protocol_version: int) -> bool:
    """Whether receipts require Flow-owned structured verifier evaluations."""
    return protocol_version == STRUCTURED_VERIFIER_PROTOCOL_VERSION


def structured_verifier_evaluation_schema_version(protocol_version: int) -> int | None:
    """Return the evaluation schema for protocols that persist Flow verdicts."""
    return VERIFIER_EVALUATION_SCHEMA_VERSION if has_structured_verifier_evaluations(protocol_version) else None


def supported_execution_protocol_versions() -> frozenset[int]:
    """Return all known protocol numbers, including dormant v8 capability."""
    return frozenset({1, EXECUTION_PROTOCOL_VERSION, MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION,
                      MAGENTIC_PROTOCOL_VERSION, CHARTERED_PROTOCOL_VERSION, DELIVERY_PROTOCOL_VERSION,
                      STRUCTURED_VERIFIER_PROTOCOL_VERSION})


class ContractError(ValueError):
    """An execution record violates Flow's versioned contract."""


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"record is not canonical JSON: {exc}") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_fields(record: dict[str, Any], fields: tuple[str, ...], *, kind: str,
                   max_bytes: int = MAX_MESSAGE_BYTES) -> None:
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"unsupported {kind} schema version")
    for field in fields:
        if field not in record or record[field] is None:
            raise ContractError(f"{kind} missing {field}")
    if len(canonical(record).encode("utf-8")) > max_bytes:
        raise ContractError(f"{kind} exceeds size limit")


def validate_envelope(envelope: dict[str, Any]) -> None:
    protocol_version = envelope.get("execution_protocol_version", 1)
    if protocol_version not in supported_execution_protocol_versions():
        raise ContractError("execution protocol version is unsupported")
    if is_magentic_protocol(protocol_version):
        _validate_magentic_envelope(envelope)
        if is_chartered_protocol(protocol_version):
            _validate_chartered_job(envelope)
        if is_delivery_protocol(protocol_version):
            _validate_delivery_projection(envelope)
        if protocol_version == STRUCTURED_VERIFIER_PROTOCOL_VERSION and "predecessors" in envelope:
            _validate_predecessors(envelope)
        if "expansion_headroom" in envelope:
            _validate_expansion_headroom(envelope)
        return
    shared = ("work_id", "attempt_id", "charter_digest", "charter_sources", "run_protocol_revision", "manifest_digest", "limits", "checkpoint_dir")
    legacy = ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest", "task")
    paired = protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}
    require_fields(envelope, shared + (("assignments",) if paired else legacy)
                   + (("source_commit", "source_files") if protocol_version == CLAUDE_PROTOCOL_VERSION else ()), kind="envelope")
    if paired:
        assignments = envelope["assignments"]
        if not isinstance(assignments, list) or len(assignments) != 2:
            raise ContractError("mixed job requires exactly two assignments")
        seen_instances: set[str] = set()
        seen_definitions: set[str] = set()
        seen_tasks: set[str] = set()
        for sequence, assignment in enumerate(assignments, 1):
            if not isinstance(assignment, dict) or set(assignment) != {"sequence", "assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "task_digest", "task", "instructions"}:
                raise ContractError("mixed assignment fields are invalid")
            expected_pair = CLAUDE_ASSIGNMENTS if protocol_version == CLAUDE_PROTOCOL_VERSION else MIXED_ASSIGNMENTS
            if assignment["sequence"] != sequence or (assignment["role"], assignment["provider"]) != expected_pair[sequence - 1]:
                raise ContractError("mixed assignment order, role, or provider is invalid")
            for field in ("assignment_id", "instance_id", "model", "instructions"):
                if not isinstance(assignment[field], str) or not assignment[field].strip():
                    raise ContractError(f"mixed assignment {field} is invalid")
            if assignment["instance_id"] in seen_instances:
                raise ContractError("mixed assignment instance is duplicated")
            seen_instances.add(assignment["instance_id"])
            if assignment["definition_digest"] in seen_definitions:
                raise ContractError("mixed assignment definition is duplicated")
            seen_definitions.add(assignment["definition_digest"])
            if not isinstance(assignment["task"], str) or not assignment["task"].strip() or len(assignment["task"].encode()) > MAX_TASK_BYTES:
                raise ContractError("task is empty or exceeds size limit")
            if hashlib.sha256(assignment["task"].encode()).hexdigest() != assignment["task_digest"]:
                raise ContractError("task digest mismatch")
            if assignment["task_digest"] in seen_tasks:
                raise ContractError("mixed assignment task is duplicated")
            seen_tasks.add(assignment["task_digest"])
            if assignment["definition_digest"] != digest({"role": assignment["role"], "instructions": assignment["instructions"]}):
                raise ContractError("definition digest mismatch")
    elif envelope["role"] != "test-engineer" or envelope["provider"] not in ALLOWED_PROVIDERS:
        raise ContractError("role or provider is not allowed")
    sources = envelope["charter_sources"]
    if envelope["run_protocol_revision"] != 2 or not isinstance(sources, dict) or set(sources) != {"requirements", "acceptance"}:
        raise ContractError("charter source snapshot is invalid")
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str) or not source["path"].startswith(".flow/runs/") or any(part in {"", ".", ".."} for part in source["path"].split("/")) or not isinstance(source["sha256"], str) or len(source["sha256"]) != 64 or any(char not in "0123456789abcdef" for char in source["sha256"]):
            raise ContractError("charter source snapshot is invalid")
    if digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}) != envelope["charter_digest"]:
        raise ContractError("charter source digest mismatch")
    if protocol_version == CLAUDE_PROTOCOL_VERSION:
        commit, files = envelope["source_commit"], envelope["source_files"]
        if not isinstance(commit, str) or len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ContractError("Claude review source commit is invalid")
        expected_paths = ["cli/codex_worker.py", "tests/test_codex_worker.py"]
        if not isinstance(files, list) or [item.get("path") if isinstance(item, dict) else None for item in files] != expected_paths:
            raise ContractError("Claude review source paths are invalid")
        for item in files:
            value = item.get("sha256")
            if set(item) != {"path", "sha256"} or not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ContractError("Claude review source digest is invalid")
    if not paired:
        if not isinstance(envelope["task"], str) or not envelope["task"].strip() or len(envelope["task"].encode()) > MAX_TASK_BYTES:
            raise ContractError("task is empty or exceeds size limit")
        if hashlib.sha256(envelope["task"].encode()).hexdigest() != envelope["task_digest"]:
            raise ContractError("task digest mismatch")
    limits = envelope["limits"]
    expected_limits = ({"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_codex_calls": 1}
                       if protocol_version == MIXED_PROTOCOL_VERSION else
                       {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "max_claude_calls": 1}
                       if protocol_version == CLAUDE_PROTOCOL_VERSION else
                       {"max_delegations": 6, "max_concurrent": 3, "max_replans": 2, "paid_budget_usd": 0})
    if not isinstance(limits, dict) or limits != expected_limits:
        raise ContractError("execution limits differ from the approved first slice")


def _hex_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _validate_magentic_envelope(envelope: dict[str, Any]) -> None:
    require_fields(envelope, ("work_id", "attempt_id", "charter_digest", "charter_sources",
                              "run_protocol_revision", "manifest_digest", "limits", "checkpoint_dir",
                              "source_commit", "worktree", "allowed_paths", "manager", "roster"), kind="envelope")
    sources = envelope["charter_sources"]
    if envelope["run_protocol_revision"] != 2 or not isinstance(sources, dict) or set(sources) != {"requirements", "acceptance"}:
        raise ContractError("charter source snapshot is invalid")
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {"path", "sha256"} or not isinstance(source["path"], str) or not source["path"].startswith(".flow/runs/") or any(part in {"", ".", ".."} for part in source["path"].split("/")) or not _hex_digest(source["sha256"]):
            raise ContractError("charter source snapshot is invalid")
    if digest({"requirements": sources["requirements"]["sha256"], "acceptance": sources["acceptance"]["sha256"]}) != envelope["charter_digest"]:
        raise ContractError("charter source digest mismatch")
    if not isinstance(envelope["manifest_digest"], str) or not _hex_digest(envelope["manifest_digest"]):
        raise ContractError("manifest digest is invalid")
    if not isinstance(envelope["source_commit"], str) or len(envelope["source_commit"]) != 40 or any(c not in "0123456789abcdef" for c in envelope["source_commit"]):
        raise ContractError("source commit is invalid")
    worktree = envelope["worktree"]
    if not isinstance(worktree, str) or not Path(worktree).is_absolute() or ".." in Path(worktree).parts:
        raise ContractError("worktree path is invalid")
    paths = envelope["allowed_paths"]
    if not isinstance(paths, list) or not paths or any(not isinstance(path, str) for path in paths) or len(paths) != len(set(paths)):
        raise ContractError("allowed path scope is invalid")
    for path in paths:
        if not isinstance(path, str) or not path or Path(path).is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ContractError("allowed path scope is invalid")
    manager = envelope["manager"]
    if not isinstance(manager, dict) or set(manager) != {"provider", "model"} or manager["provider"] not in {"ollama", "claude", "codex"} or not isinstance(manager["model"], str) or not manager["model"].strip():
        raise ContractError("manager binding is invalid")
    roster = envelope["roster"]
    if not isinstance(roster, list) or not roster or len(roster) > 6:
        raise ContractError("specialist roster is invalid")
    seen_ids: set[str] = set()
    for assignment in roster:
        fields = {"assignment_id", "definition_digest", "instance_id", "role", "provider", "model", "instructions"}
        if is_chartered_protocol(envelope["execution_protocol_version"]):
            fields.add("capabilities")
        if not isinstance(assignment, dict) or set(assignment) != fields:
            raise ContractError("specialist binding is invalid")
        if assignment["provider"] not in {"ollama", "claude", "codex", "local-stub"}:
            raise ContractError("specialist provider is invalid")
        if any(not isinstance(assignment[k], str) or not assignment[k].strip() for k in ("assignment_id", "instance_id", "role", "model", "instructions")):
            raise ContractError("specialist identity is invalid")
        if assignment["assignment_id"] in seen_ids or assignment["instance_id"] in seen_ids:
            raise ContractError("specialist identity is duplicated")
        seen_ids.update((assignment["assignment_id"], assignment["instance_id"]))
        if assignment["definition_digest"] != digest({"role": assignment["role"], "instructions": assignment["instructions"]}):
            raise ContractError("specialist definition digest mismatch")
        if is_chartered_protocol(envelope["execution_protocol_version"]):
            valid_capabilities = (["read"], ["read", "edit"]) if assignment["provider"] == "codex" else (
                (["read", "edit"],) if assignment["provider"] == "claude" else (["read"],))
            if assignment["capabilities"] not in valid_capabilities:
                raise ContractError("specialist capabilities differ from provider")
    limits = envelope["limits"]
    expected = {"max_delegations": MAX_ACTIONS, "max_concurrent": MAX_CONCURRENT, "max_replans": MAX_REPLANS,
                "max_manager_calls": MAX_MANAGER_CALLS, "max_manager_rounds": MAX_MANAGER_ROUNDS}
    paid_calls = limits.get("max_paid_worker_calls") if isinstance(limits, dict) else None
    if envelope["execution_protocol_version"] == DELIVERY_PROTOCOL_VERSION:
        valid_limits = (isinstance(limits, dict) and set(limits) == set(expected) | {"max_paid_worker_calls", "max_runtime_seconds"}
                        and all(type(limits[key]) is int and 0 <= limits[key] <= maximum for key, maximum in expected.items())
                        and limits["max_delegations"] >= 1 and limits["max_concurrent"] >= 1
                        and limits["max_manager_calls"] >= 1 and limits["max_manager_rounds"] >= 1
                        and type(limits["max_runtime_seconds"]) is int and 1 <= limits["max_runtime_seconds"] <= 600
                        and type(paid_calls) is int and 0 <= paid_calls <= limits["max_delegations"])
    elif envelope["execution_protocol_version"] == STRUCTURED_VERIFIER_PROTOCOL_VERSION:
        # Pre-release v8 envelopes stay readable (ADR 0020); only a handback
        # envelope, which seals the lineage token budget, may be advanced.
        valid_limits = (isinstance(limits, dict)
                        and set(limits) in (LEGACY_V8_LIMIT_KEYS, HANDBACK_V8_LIMIT_KEYS)
                        and (set(limits) == LEGACY_V8_LIMIT_KEYS or _token_budget_valid(limits))
                        and all(type(limits[key]) is int and 0 <= limits[key] <= maximum for key, maximum in expected.items())
                        and limits["max_delegations"] >= 1 and limits["max_concurrent"] >= 1
                        and limits["max_manager_calls"] >= 1 and limits["max_manager_rounds"] >= 1
                        and type(limits["max_runtime_seconds"]) is int and 1 <= limits["max_runtime_seconds"] <= 600
                        and type(paid_calls) is int and 0 <= paid_calls <= limits["max_delegations"]
                        and type(limits["max_verifier_calls"]) is int and 1 <= limits["max_verifier_calls"] <= MAX_VERIFIER_CALLS)
    else:
        valid_limits = (isinstance(limits, dict) and set(limits) == set(expected) | {"max_paid_worker_calls"}
                        and all(limits[key] == value for key, value in expected.items())
                        and type(paid_calls) is int and 1 <= paid_calls <= expected["max_delegations"])
    if not valid_limits:
        raise ContractError("Magentic limits differ from approved envelope")


LEGACY_V8_LIMIT_KEYS = frozenset({"max_delegations", "max_concurrent", "max_replans", "max_manager_calls",
                                  "max_manager_rounds", "max_paid_worker_calls", "max_runtime_seconds",
                                  "max_verifier_calls"})
TOKEN_LIMIT_KEYS = ("max_lineage_tokens", "token_tranche", "unobserved_send_tokens")
HANDBACK_V8_LIMIT_KEYS = LEGACY_V8_LIMIT_KEYS | frozenset(TOKEN_LIMIT_KEYS)


def _token_budget_valid(limits: dict[str, Any]) -> bool:
    return (all(type(limits.get(key)) is int and limits[key] >= 1 for key in TOKEN_LIMIT_KEYS)
            and limits["token_tranche"] >= limits["unobserved_send_tokens"]
            and limits["unobserved_send_tokens"] <= limits["max_lineage_tokens"] <= MAX_LINEAGE_TOKENS)


def handback_supported(envelope: Any) -> bool:
    """Whether a v8 envelope seals the lineage token budget (ADR 0020).

    Read from the raw envelope, so it is safe on a pre-release envelope and
    never depends on a receipt's own contents.
    """
    limits = envelope.get("limits") if isinstance(envelope, dict) else None
    return (isinstance(envelope, dict) and envelope.get("execution_protocol_version") == STRUCTURED_VERIFIER_PROTOCOL_VERSION
            and isinstance(limits, dict) and set(limits) == HANDBACK_V8_LIMIT_KEYS)


def _safe_relative_paths(paths: Any) -> bool:
    return (isinstance(paths, list) and bool(paths) and all(isinstance(path, str) for path in paths)
            and len(paths) == len(set(paths))
            and all(isinstance(path, str) and path and not Path(path).is_absolute()
                    and all(part not in {"", ".", ".."} for part in path.split("/"))
                    for path in paths))


def _paths_within_scopes(paths: Any, scopes: Any) -> bool:
    """Whether each safe relative path equals or descends from an approved scope."""
    if not _safe_relative_paths(paths) or not _safe_relative_paths(scopes):
        return False
    approved = tuple(Path(scope) for scope in scopes)
    return all(any(Path(path) == scope or Path(path).is_relative_to(scope) for scope in approved)
               for path in paths)


def chartered_test_argv_supported(argv: Any) -> bool:
    """One canonical command-shape policy shared by sealing and dispatch."""
    full_discovery = isinstance(argv, list) and len(argv) == 6 and argv[1:6] == ["-m", "unittest", "discover", "-s", "tests"]
    focused = (isinstance(argv, list) and len(argv) == 8
               and argv[1:6] == ["-m", "unittest", "discover", "-s", "tests"]
               and argv[6] == "-p" and argv[7].startswith("test_") and argv[7].endswith(".py")
               and argv[7][5:-3].replace("_", "").isalnum())
    probe = (isinstance(argv, list) and len(argv) == 2
             and argv[1].startswith("tests/") and argv[1].endswith("_probe.py")
             and argv[1][len("tests/"):-len("_probe.py")].replace("_", "").isalnum())
    return bool(full_discovery or focused or probe)


def _validate_chartered_job(envelope: dict[str, Any]) -> None:
    job = envelope.get("job_contract")
    required = {"task", "baseline", "read_paths", "write_paths", "test",
                "producer_instance_ids", "verifier_instance_ids"}
    optional = {"evidence_collector_instance_ids"}
    if not isinstance(job, dict) or not required.issubset(job) or set(job) - required - optional:
        raise ContractError("chartered job contract fields are invalid")
    if not isinstance(job["task"], str) or not job["task"].strip() or len(job["task"].encode()) > MAX_TASK_BYTES:
        raise ContractError("chartered job task is invalid")
    baseline = job["baseline"]
    if (not isinstance(baseline, dict) or set(baseline) != {"kind", "diff_sha256"}
            or baseline["kind"] not in {"clean", "declared_regression"}
            or not _hex_digest(baseline["diff_sha256"])):
        raise ContractError("chartered job baseline is invalid")
    if not _safe_relative_paths(job["read_paths"]) or not _safe_relative_paths(job["write_paths"]) or job["write_paths"] != envelope["allowed_paths"]:
        raise ContractError("chartered job path scope is invalid")
    test = job["test"]
    argv = test.get("argv") if isinstance(test, dict) else None
    if (not isinstance(test, dict) or set(test) != {"argv", "timeout_seconds"}
            or not isinstance(test["argv"], list) or not test["argv"]
            or any(not isinstance(arg, str) or not arg or "\x00" in arg or "\n" in arg for arg in test["argv"])
            or test["argv"][0] not in {"python3", "python3.12", "/opt/homebrew/bin/python3.12"}
            or not chartered_test_argv_supported(argv)
            or type(test["timeout_seconds"]) is not int or not 1 <= test["timeout_seconds"] <= 3600):
        raise ContractError("chartered job test command is invalid")
    for kind, providers in (("producer_instance_ids", {"claude", "codex"}),
                            ("verifier_instance_ids", {"ollama", "local-stub", "codex"})):
        ids = job[kind]
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ContractError(f"chartered job {kind} is invalid")
        bindings = {item["instance_id"]: item for item in envelope["roster"]}
        if any(instance not in bindings or bindings[instance]["provider"] not in providers for instance in ids):
            raise ContractError(f"chartered job {kind} differs from roster")
        expected = ["read", "edit"] if kind == "producer_instance_ids" else ["read"]
        if any(bindings[instance]["capabilities"] != expected for instance in ids):
            raise ContractError(f"chartered job {kind} capabilities differ from roster")
    if set(job["producer_instance_ids"]) & set(job["verifier_instance_ids"]):
        raise ContractError("chartered job producer and verifier overlap")
    evidence_collectors = job.get("evidence_collector_instance_ids", [])
    bindings = {item["instance_id"]: item for item in envelope["roster"]}
    if (not isinstance(evidence_collectors, list) or len(evidence_collectors) != len(set(evidence_collectors))
            or any(instance not in bindings or bindings[instance]["provider"] not in {"ollama", "local-stub", "codex"}
                   or bindings[instance]["capabilities"] != ["read"] for instance in evidence_collectors)
            or set(evidence_collectors) & (set(job["producer_instance_ids"]) | set(job["verifier_instance_ids"]))):
        raise ContractError("chartered job evidence collector differs from roster")


def _validate_delivery_projection(envelope: dict[str, Any]) -> None:
    """Validate v7's immutable projection of Flow-owned delivery authority.

    The canonical records remain outside this execution module.  Their digests
    are carried here so a runtime cannot quietly broaden a Shaper-approved job.
    """
    required = ("shaper_contract_digest", "delivery_charter_digest", "handoff_digest",
                "delivery_lead_claim_digest", "delivery_lead_claim")
    if any(not _hex_digest(envelope.get(field)) for field in required[:-1]):
        raise ContractError("delivery projection contract link is invalid")
    claim = envelope.get("delivery_lead_claim")
    if (not isinstance(claim, dict) or set(claim) != {"lead_id", "generation"}
            or not isinstance(claim["lead_id"], str) or not claim["lead_id"].strip()
            or type(claim["generation"]) is not int or claim["generation"] < 1):
        raise ContractError("delivery lead claim is invalid")


# A v8 attempt a person stopped (ADR 0019). Its receipt keeps every uncertain
# row uncertain; no other status may seal one.
TERMINAL_UNCERTAIN_STATUSES = frozenset({"cancelled", "abandoned"})
PREDECESSOR_TERMINAL_STATUSES = frozenset({"completed", "failed", "denied", "superseded"}) | TERMINAL_UNCERTAIN_STATUSES
EVIDENCE_DAMAGE_KEYS = {
    "baseline_missing": {"kind"},
    "trace_oversized": {"kind", "path", "sha256", "bytes"},
    "draft_receipt_replaced": {"kind", "sha256"},
}
# cancel_signal: SIGTERM reached the parent without a valid cancel request (ADR 0019).
RECOVERY_INTERRUPTION_CAUSES = frozenset({"transport", "reconciliation_required", "unmarked_process_exit",
                                          "cancel_signal"})
RECOVERY_MODES = frozenset({"answer", "pending", "seal", "restart"})
RECOVERY_GRANT_REASONS = frozenset({"recovery_unconsumed_grant", "recovery_regranted"})
RECOVERY_TRIGGER_REASONS = RECOVERY_GRANT_REASONS | {"recovery_after_dispatch"}


# Expandable limits: the envelope key each extends, and its runner ceiling.
# ``tokens`` has no envelope key: it counts tranches from a base of zero, and
# only the token predicate turns tranches into tokens (ADR 0020).
EXPANSION_LIMIT_KEYS = {
    "delegations": ("max_delegations", MAX_ACTIONS),
    "paid_worker_calls": ("max_paid_worker_calls", MAX_ACTIONS),
    "verifier_calls": ("max_verifier_calls", MAX_VERIFIER_CALLS),
    "manager_calls": ("max_manager_calls", MAX_MANAGER_CALLS),
    "manager_rounds": ("max_manager_rounds", MAX_MANAGER_ROUNDS),
    "tokens": (None, MAX_TOKEN_TRANCHES),
}
# Limits whose grants and spent headroom count across the whole lineage.
LINEAGE_SCOPED_LIMITS = frozenset({"paid_worker_calls", "verifier_calls", "tokens"})


def expansion_base(envelope: dict[str, Any]) -> dict[str, int]:
    """The sealed value each expandable limit starts from; token tranches start at zero."""
    limits = envelope["limits"]
    return {name: (limits[key] if key is not None else 0) for name, (key, _) in EXPANSION_LIMIT_KEYS.items()}


def expansion_fits(envelope: dict[str, Any], name: str, units: int) -> bool:
    """Whether ``units`` of one expandable limit stay within its ceilings.

    Token tranches also keep the absolute budget within ``MAX_LINEAGE_TOKENS``,
    so no grant, automatic or engineer-decided, can push past it.
    """
    if units > EXPANSION_LIMIT_KEYS[name][1]:
        return False
    if name == "tokens":
        limits = envelope["limits"]
        if not handback_supported(envelope):
            return units == 0
        return limits["max_lineage_tokens"] + units * limits["token_tranche"] <= MAX_LINEAGE_TOKENS
    return True


def expansion_headroom(envelope: dict[str, Any]) -> dict[str, int]:
    """Return the sealed headroom an envelope projects; absent means none."""
    projected = envelope.get("expansion_headroom", {})
    return {name: projected.get(name, 0) for name in EXPANSION_LIMIT_KEYS}


# Token charging (ADR 0020). ``charged_v1`` = uncached input + cache writes +
# output; cache reads are reported, never charged. It is a stable budget unit,
# not a cost proxy.
CHARGED_UNIT = "charged_v1"
PAID_PROVIDERS = frozenset({"codex", "claude"})
SENT_STATUSES = frozenset({"started", "completed", "failed", "unknown"})
# Usage counters Flow reads; any other key a provider adds is kept and ignored.
KNOWN_USAGE_KEYS = frozenset({"input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens",
                              "cached_input_tokens", "cache_write_input_tokens", "reasoning_output_tokens",
                              "total_tokens", "prompt_eval_count", "eval_count"})


def _counter(value: Any) -> bool:
    return type(value) is int and value >= 0


def usage_values_valid(usage: Any) -> bool:
    """A usage block is absent, or a mapping whose known counters are non-negative integers.

    Unknown keys are tolerated: a provider CLI that adds a field must never turn
    a paid call into an unresolvable unknown (ADR 0020).
    """
    return usage is None or (isinstance(usage, dict) and all(_counter(usage[key]) for key in KNOWN_USAGE_KEYS & set(usage)))


def normalized_charge(provider: str, usage: Any) -> tuple[int, int] | None:
    """``(charged, cache_read)`` for a recognised paid usage block, else None."""
    if not isinstance(usage, dict) or not _counter(usage.get("input_tokens")) or not _counter(usage.get("output_tokens")):
        return None
    if provider == "claude":
        write, read = usage.get("cache_creation_input_tokens", 0), usage.get("cache_read_input_tokens", 0)
        if not _counter(write) or not _counter(read):
            return None
        return usage["input_tokens"] + write + usage["output_tokens"], read
    if provider == "codex":
        # Codex cached input is a subset of input; reasoning is inside output.
        cached = usage.get("cached_input_tokens", 0)
        if not _counter(cached) or cached > usage["input_tokens"]:
            return None
        return usage["input_tokens"] - cached + usage["output_tokens"], cached
    return None


# Counters that would be charged if the shape were recognised; cache reads and
# Codex cached input (a subset of input) are not, and reasoning is inside output.
_CHARGEABLE_KEYS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_write_input_tokens")


def conservative_charge(usage: Any, unobserved_send_tokens: int) -> int:
    """The charge of a sent paid row whose usage Flow cannot normalise (ADR 0020, RS1).

    The largest of the sealed unobserved charge, a reported ``total_tokens``,
    and the sum of the chargeable counters present, so a provider that changes
    its usage shape can never make its calls cheaper than they reported.
    """
    if not isinstance(usage, dict):
        return unobserved_send_tokens
    total = usage.get("total_tokens") if _counter(usage.get("total_tokens")) else 0
    present = sum(usage[key] for key in _CHARGEABLE_KEYS if _counter(usage.get(key)))
    return max(unobserved_send_tokens, total, present)


def charge(status: str, provider: str | None, result: Any, unobserved_send_tokens: int) -> dict[str, Any]:
    """The charge of one row, by its status only, from data a receipt carries (ADR 0020).

    A completed or failed paid row with recognised usage is charged what it
    reported; one whose usage cannot be normalised is charged conservatively
    (never less than the sealed charge). A started or unknown paid row is
    charged the sealed ``unobserved_send_tokens``. Unsent rows and unpaid
    providers cost nothing.
    """
    if provider not in PAID_PROVIDERS or status not in SENT_STATUSES:
        return {"charged": 0, "cache_read": 0, "recognised": True, "unobserved": False}
    if status in {"completed", "failed"}:
        usage = result.get("usage") if isinstance(result, dict) else None
        normalized = normalized_charge(provider, usage)
        if normalized is not None:
            return {"charged": normalized[0], "cache_read": normalized[1], "recognised": True, "unobserved": False}
        return {"charged": conservative_charge(usage, unobserved_send_tokens), "cache_read": 0, "recognised": False,
                "unobserved": True}
    return {"charged": unobserved_send_tokens, "cache_read": 0, "recognised": True, "unobserved": True}


def verifier_tokens(result: Any) -> int:
    """Local verifier tokens, reported only: never charged."""
    usage = result.get("usage") if isinstance(result, dict) else None
    if not isinstance(usage, dict):
        return 0
    return sum(usage[key] for key in ("prompt_eval_count", "eval_count") if _counter(usage.get(key)))


def attempt_token_charges(envelope: dict[str, Any], actions: list[dict[str, Any]],
                          manager_calls: list[dict[str, Any]]) -> dict[str, int]:
    """The charges of one attempt's own rows; manager calls count only when the manager is paid."""
    unobserved = envelope["limits"]["unobserved_send_tokens"]
    manager_provider = (envelope.get("manager") or {}).get("provider")
    totals = {"observed_charged": 0, "unobserved_sends": 0, "unobserved_charged": 0, "unrecognised_usage": 0,
              "cache_read_total": 0, "verifier_tokens": 0}
    rows = [(item.get("status"), (item.get("request") or {}).get("provider"), item.get("result")) for item in actions]
    rows += [(item.get("status"), manager_provider, item.get("result")) for item in manager_calls]
    for status, provider, result in rows:
        if provider not in PAID_PROVIDERS:
            if status in SENT_STATUSES:
                totals["verifier_tokens"] += verifier_tokens(result)
            continue
        item = charge(status, provider, result, unobserved)
        totals["cache_read_total"] += item["cache_read"]
        if item["unobserved"]:
            totals["unobserved_sends"] += 1
            totals["unobserved_charged"] += item["charged"]
            totals["unrecognised_usage"] += not item["recognised"]
        else:
            totals["observed_charged"] += item["charged"]
    totals["charged"] = totals["observed_charged"] + totals["unobserved_charged"]
    return totals


def token_maximum(envelope: dict[str, Any], tranches: int) -> int:
    """The effective lineage token cap: the sealed budget plus every granted tranche."""
    limits = envelope["limits"]
    return limits["max_lineage_tokens"] + tranches * limits["token_tranche"]


def token_gate(charged: int, envelope: dict[str, Any], tranches: int) -> tuple[bool, int]:
    """``(failing, units)``: whether the next paid grant is over the cap, and the tranches it needs.

    One tranche clears any shortfall below ``token_tranche``; a larger one
    needs more than one unit and is a hard refusal (ADR 0020).
    """
    maximum = token_maximum(envelope, tranches)
    if charged < maximum:
        return False, 0
    return True, (charged - maximum) // envelope["limits"]["token_tranche"] + 1


def token_usage_block(envelope: dict[str, Any], actions: list[dict[str, Any]], manager_calls: list[dict[str, Any]],
                      *, predecessor_charged: int, tranches_granted: int) -> dict[str, Any]:
    """The receipt ``token_usage`` block; recomputable from a receipt's own rows (ADR 0020)."""
    own = attempt_token_charges(envelope, actions, manager_calls)
    maximum = token_maximum(envelope, tranches_granted)
    total = own["charged"] + predecessor_charged
    return {"unit": CHARGED_UNIT, "maximum": maximum, "tranches_granted": tranches_granted,
            "observed_charged": own["observed_charged"], "unobserved_sends": own["unobserved_sends"],
            "unobserved_charged": own["unobserved_charged"], "unrecognised_usage": own["unrecognised_usage"],
            "predecessor_charged": predecessor_charged, "charged_total": total,
            "overshoot": max(0, total - maximum), "cache_read_total": own["cache_read_total"],
            "verifier_tokens": own["verifier_tokens"]}


def _validate_expansion_headroom(envelope: dict[str, Any]) -> None:
    """A v8 envelope may carry the charter's headroom; it is omitted when all zero."""
    headroom = envelope["expansion_headroom"]
    limits = envelope["limits"]
    if (envelope["execution_protocol_version"] != STRUCTURED_VERIFIER_PROTOCOL_VERSION
            or not isinstance(headroom, dict) or not headroom or not set(headroom) <= set(EXPANSION_LIMIT_KEYS)
            or any(type(value) is not int or value < 0 for value in headroom.values()) or not any(headroom.values())):
        raise ContractError("expansion headroom is invalid")
    full = expansion_headroom(envelope)
    base = expansion_base(envelope)
    if full["tokens"] and not handback_supported(envelope):
        raise ContractError("token headroom requires a sealed token budget")
    for name in EXPANSION_LIMIT_KEYS:
        if not expansion_fits(envelope, name, base[name] + full[name]):
            raise ContractError("expansion headroom exceeds the runner ceiling")
    if limits["max_paid_worker_calls"] + full["paid_worker_calls"] > limits["max_delegations"] + full["delegations"]:
        raise ContractError("paid-worker headroom exceeds delegation headroom")


def _validate_predecessors(envelope: dict[str, Any]) -> None:
    """Validate a v8 successor's immutable links to its terminal predecessors."""
    predecessors = envelope["predecessors"]
    generation = envelope["delivery_lead_claim"]["generation"]
    if not isinstance(predecessors, list) or not predecessors or len(predecessors) > 64:
        raise ContractError("delivery predecessors are invalid")
    seen: set[str] = set()
    for item in predecessors:
        if (not isinstance(item, dict)
                or set(item) != {"attempt_id", "terminal_status", "receipt_sha256", "lead_generation"}
                or not isinstance(item["attempt_id"], str) or not item["attempt_id"]
                or item["attempt_id"] in seen or item["attempt_id"] == envelope["attempt_id"]
                or item["terminal_status"] not in PREDECESSOR_TERMINAL_STATUSES
                or not (_hex_digest(item["receipt_sha256"])
                        or item["receipt_sha256"] is None and item["terminal_status"] == "superseded")
                or type(item["lead_generation"]) is not int or not 1 <= item["lead_generation"] <= generation):
            raise ContractError("delivery predecessor link is invalid")
        seen.add(item["attempt_id"])


EXPANSION_REQUEST_STATUSES = frozenset({"pending", "granted", "denied", "cancelled"})
EXPANSION_GRANT_STATUSES = frozenset({"available", "consumed", "lapsed", "denied"})


def _validate_expansion(envelope: dict[str, Any], receipt: dict[str, Any]) -> dict[str, int]:
    """Recompute a v8 receipt's expansion evidence and return its effective limits (ADR 0017).

    Validation replays headroom spending in ledger order, and binds every
    grant to its request, authority, one-unit amount, lineage, and an owner
    generation of this attempt's recovery chain. Rows allowed as
    ``expansion_granted`` must be backed by a consumed grant.
    """
    effective = expansion_base(envelope)
    rows = {item["action_id"]: item for item in receipt["actions"]}
    rows.update({item["call_id"]: item for item in receipt["manager_calls"]})
    block = receipt.get("expansion")
    backed: set[str] = set()
    if block is not None:
        names = set(EXPANSION_LIMIT_KEYS)
        counters = lambda value, keys: (isinstance(value, dict) and set(value) == keys
                                        and all(type(item) is int and item >= 0 for item in value.values()))
        predecessors = envelope.get("predecessors", [])
        # The ledger scopes expansion spend to predecessors sealed by the same
        # Delivery Charter. The compact predecessor links do not carry that
        # charter digest, so the pure receipt validator can prove only that
        # the declared authority-lineage root is either one of the sealed
        # linked predecessors or the current attempt. The latter is required
        # when a successor Delivery Charter starts a fresh budget while still
        # retaining older attempts as provenance. The seal separately compares
        # this entire block with the ledger-built block.
        lineage_ids = {item["attempt_id"] for item in predecessors} | {envelope["attempt_id"]}
        if (not isinstance(block, dict)
                or set(block) != {"lineage_id", "headroom", "predecessor_headroom_spent", "predecessor_lineage_grants", "requests"}
                or block["lineage_id"] not in lineage_ids or block["headroom"] != expansion_headroom(envelope)
                or not counters(block["predecessor_headroom_spent"], names)
                or not counters(block["predecessor_lineage_grants"], set(LINEAGE_SCOPED_LIMITS))
                or not isinstance(block["requests"], list)
                or (not predecessors and (any(block["predecessor_headroom_spent"].values())
                                          or any(block["predecessor_lineage_grants"].values())))):
            raise ContractError("receipt expansion evidence is invalid")
        recovery = receipt.get("recovery") if isinstance(receipt.get("recovery"), dict) else {}
        generations = {envelope["delivery_lead_claim"]["generation"]} | {
            item.get("generation") for item in recovery.get("recoveries", []) if isinstance(item, dict)}
        spent = dict(block["predecessor_headroom_spent"])
        if any(spent[name] > block["headroom"][name] for name in names):
            raise ContractError("receipt automatic expansion exceeds sealed headroom")
        for name, value in block["predecessor_lineage_grants"].items():
            effective[name] += value
        headroom = block["headroom"]
        seen: set[str] = set()
        for request in block["requests"]:
            grant = request.get("grant") if isinstance(request, dict) else None
            if (not isinstance(request, dict)
                    or set(request) != {"request_id", "kind", "denied_row_id", "limits", "amount", "owner_generation", "status", "grant"}
                    or not isinstance(request["request_id"], str) or request["request_id"] in seen
                    or request["kind"] not in {"delegate", "manager_call"} or request["denied_row_id"] not in rows
                    or not isinstance(request["limits"], list) or not request["limits"]
                    or request["limits"] != sorted(set(request["limits"])) or not set(request["limits"]) <= names
                    or request["amount"] != 1 or request["owner_generation"] not in generations
                    or request["status"] not in EXPANSION_REQUEST_STATUSES
                    or (request["kind"] == "delegate") != (request["denied_row_id"] in {item["action_id"] for item in receipt["actions"]})):
                raise ContractError("receipt expansion request is invalid")
            seen.add(request["request_id"])
            if request["status"] == "pending" or (grant or {}).get("status") == "available":
                # Sealing closes every open request and unused grant.
                raise ContractError("receipt keeps an open expansion request or grant")
            if grant is None:
                if request["status"] not in {"pending", "cancelled"}:
                    raise ContractError("receipt expansion decision is missing its grant")
                continue
            if (not isinstance(grant, dict)
                    or set(grant) != {"grant_id", "authority", "decision", "amount", "owner_generation", "status", "consumed_by", "actor"}
                    or grant["amount"] != 1 or grant["owner_generation"] not in generations
                    or grant["status"] not in EXPANSION_GRANT_STATUSES
                    or grant["decision"] != {"granted": "approve", "denied": "deny"}.get(request["status"])
                    or (grant["decision"] == "deny") != (grant["status"] == "denied")
                    or (grant["status"] == "consumed") != (grant["consumed_by"] is not None)
                    or grant["consumed_by"] not in {None, request["denied_row_id"]}):
                raise ContractError("receipt expansion grant is invalid")
            if grant["authority"] == "charter_headroom":
                # Automatic grants are consumed at once and draw sealed headroom in order.
                if grant["status"] != "consumed" or grant["actor"] is not None:
                    raise ContractError("receipt automatic expansion grant is invalid")
                for name in request["limits"]:
                    spent[name] += 1
                    if spent[name] > headroom[name]:
                        raise ContractError("receipt automatic expansion exceeds sealed headroom")
            elif grant["authority"] != "engineer" or not isinstance(grant["actor"], str) or not grant["actor"].strip():
                raise ContractError("receipt expansion grant authority is invalid")
            if grant["status"] == "consumed":
                row = rows[grant["consumed_by"]]
                # A spent unit whose send grant then expired stays spent.
                if row["status"] == "denied" and row.get("reason") != "grant_expired":
                    raise ContractError("receipt consumed expansion grant left its proposal denied")
                backed.add(grant["consumed_by"])
                for name in request["limits"]:
                    effective[name] += 1
    for row_id, item in rows.items():
        if item.get("reason") == "expansion_granted" and row_id not in backed:
            raise ContractError("receipt expansion-granted proposal lacks a consumed grant")
    if not all(expansion_fits(envelope, name, effective[name]) for name in EXPANSION_LIMIT_KEYS):
        raise ContractError("receipt effective limits exceed the runner ceiling")
    return effective


LEGACY_LINEAGE_USAGE_KEYS = frozenset({"predecessor_paid_calls", "predecessor_verifier_sends"})
LINEAGE_USAGE_KEYS = LEGACY_LINEAGE_USAGE_KEYS | {"predecessor_charged"}


def _validate_lineage_usage(envelope: dict[str, Any], receipt: dict[str, Any],
                            effective: dict[str, int] | None = None) -> dict[str, int]:
    """A successor receipt reports its predecessors' sends; a first attempt reports none.

    The counts are the ledger's; a receipt can only be checked for shape and
    for agreeing with its own verifier usage (the ledger stays authoritative).
    """
    usage = receipt.get("lineage_usage")
    keys = LINEAGE_USAGE_KEYS if handback_supported(envelope) else LEGACY_LINEAGE_USAGE_KEYS
    if not envelope.get("predecessors"):
        if "lineage_usage" in receipt:
            raise ContractError("receipt lineage usage requires predecessors")
        return {key: 0 for key in sorted(keys)}
    if (not isinstance(usage, dict) or set(usage) != keys
            or any(type(value) is not int or value < 0 for value in usage.values())):
        raise ContractError("receipt lineage usage is invalid")
    # The lineage shares the charter caps, so the attempt's own sends plus its
    # predecessors' can never exceed them.
    job = envelope["job_contract"]
    effective = effective or {"paid_worker_calls": envelope["limits"]["max_paid_worker_calls"],
                              "verifier_calls": envelope["limits"]["max_verifier_calls"]}
    sent = {"started", "completed", "failed", "unknown"}
    own_paid = sum(item["request"].get("provider") in {"codex", "claude"} and item["status"] in sent
                   for item in receipt["actions"])
    own_verifier = sum(item["request"].get("instance_id") in job["verifier_instance_ids"] and item["status"] in sent
                       for item in receipt["actions"])
    if (own_paid + usage["predecessor_paid_calls"] > effective["paid_worker_calls"]
            or own_verifier + usage["predecessor_verifier_sends"] > effective["verifier_calls"]):
        raise ContractError("receipt lineage usage exceeds the charter caps")
    return usage


def _validate_recovery_block(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Bind a v8 receipt's recovery claims to the evidence that shows recovery happened."""
    claim_generation = envelope["delivery_lead_claim"]["generation"]
    actions = [item for item in receipt["actions"] if isinstance(item, dict)]
    reasons = [item.get("reason") for item in actions]
    generations = [item.get("owner_generation") for key in ("checkpoints", "verifier_inputs", "verifier_evaluations")
                   for item in receipt.get(key) or [] if isinstance(item, dict)]
    block = receipt.get("recovery")
    if block is None:
        if (any(reason in RECOVERY_TRIGGER_REASONS or str(reason).startswith("operator_resolved_") for reason in reasons)
                or any(type(value) is int and value > claim_generation for value in generations)):
            raise ContractError("recovered receipt lacks its recovery block")
        return
    if (not isinstance(block, dict)
            or set(block) != {"schema_version", "interruptions", "recoveries", "resolutions", "replaced_draft_sha256"}
            or block["schema_version"] != 1 or not isinstance(block["interruptions"], list)
            or not isinstance(block["recoveries"], list) or not block["recoveries"]
            or not isinstance(block["resolutions"], list)
            or not (block["replaced_draft_sha256"] is None or _hex_digest(block["replaced_draft_sha256"]))):
        raise ContractError("receipt recovery block is invalid")
    expected = claim_generation
    allowed = {claim_generation}
    released: set[str] = set()
    for item in block["recoveries"]:
        if (not isinstance(item, dict)
                or set(item) != {"recovery_id", "expected_generation", "generation", "lead_generation",
                                 "actor", "mode", "released_action_ids", "claimed_at"}
                or not isinstance(item["recovery_id"], str) or not item["recovery_id"]
                or not isinstance(item["actor"], str) or not item["actor"].strip()
                or not isinstance(item["claimed_at"], str) or item["mode"] not in RECOVERY_MODES
                or not isinstance(item["released_action_ids"], list)
                or any(not isinstance(value, str) for value in item["released_action_ids"])):
            raise ContractError("receipt recovery claim is invalid")
        if (item["expected_generation"] != expected or item["generation"] != expected + 1
                or item["lead_generation"] != claim_generation):
            raise ContractError("receipt recovery generation chain is invalid")
        expected = item["generation"]
        allowed.add(item["generation"])
        released.update(item["released_action_ids"])
    for item in block["interruptions"]:
        if (not isinstance(item, dict)
                or set(item) != {"interruption_id", "cause", "owner_generation", "recorded_at"}
                or not isinstance(item["interruption_id"], str) or not item["interruption_id"]
                or item["cause"] not in RECOVERY_INTERRUPTION_CAUSES or item["owner_generation"] not in allowed
                or not isinstance(item["recorded_at"], str)):
            raise ContractError("receipt recovery interruption is invalid")
    if any(value not in allowed for value in generations):
        raise ContractError("receipt evidence owner generation is outside the recovery chain")
    # A released grant's reason can later move on (grant expiry, a denied
    # regrant), so every action still marked released must be listed, and
    # every listed id must be an action of this receipt.
    marked = {item.get("action_id") for item in actions if item.get("reason") in RECOVERY_GRANT_REASONS}
    if not marked <= released or not released <= {item.get("action_id") for item in actions}:
        raise ContractError("receipt recovery released grants differ from actions")
    resolved = sum(str(reason).startswith("operator_resolved_") for reason in reasons)
    if (any(not isinstance(value, str) or not value for value in block["resolutions"])
            or len(set(block["resolutions"])) != len(block["resolutions"]) or len(block["resolutions"]) != resolved):
        raise ContractError("receipt recovery resolutions differ from actions")


def action_assignment(envelope: dict[str, Any], sequence: int) -> dict[str, Any]:
    """Select the immutable assignment bound to this logical action."""
    if execution_protocol_version(envelope) in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        if type(sequence) is not int or not 1 <= sequence <= 2:
            raise ContractError("mixed action sequence is invalid")
        return envelope["assignments"][sequence - 1]
    if is_magentic_protocol(execution_protocol_version(envelope)):
        raise ContractError("dynamic action requires an assignment identity")
    return envelope


def execution_protocol_version(envelope: dict[str, Any]) -> int:
    """Return the explicit protocol for a new attempt, defaulting old records to v1."""
    validate_envelope(envelope)
    return envelope.get("execution_protocol_version", 1)


def envelope_digest(envelope: dict[str, Any]) -> str:
    validate_envelope(envelope)
    return digest(envelope)


def expected_action_id(envelope: dict[str, Any], sequence: int) -> str:
    protocol_version = execution_protocol_version(envelope)
    if is_magentic_protocol(protocol_version):
        raise ContractError("dynamic action identity requires its manager proposal")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ContractError("action sequence is invalid")
    if protocol_version == 1 and sequence != 1:
        raise ContractError("first slice permits one specialist request")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and sequence > 3:
        raise ContractError("action sequence exceeds the approved slice")
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION} and sequence > 2:
        raise ContractError("mixed action sequence exceeds the approved slice")
    assignment = action_assignment(envelope, sequence)
    identity = {
        "attempt_id": envelope["attempt_id"],
        "charter_digest": envelope["charter_digest"],
        "definition_digest": assignment["definition_digest"],
        "instance_id": assignment["instance_id"],
        "kind": "delegate", "sequence": sequence,
    }
    if protocol_version == EXECUTION_PROTOCOL_VERSION:
        identity["execution_protocol_version"] = protocol_version
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        identity["execution_protocol_version"] = protocol_version
        identity["assignment_id"] = assignment["assignment_id"]
    return digest(identity)


def validate_action(envelope: dict[str, Any], action: dict[str, Any]) -> None:
    require_fields(action, ("action_id", "attempt_id", "envelope_digest", "role", "instance_id", "provider", "model", "task_digest", "sequence", "kind"), kind="action")
    protocol_version = execution_protocol_version(envelope)
    if is_magentic_protocol(protocol_version):
        _validate_magentic_action(envelope, action)
        return
    if action["kind"] != "delegate" or not isinstance(action["sequence"], int) or isinstance(action["sequence"], bool):
        raise ContractError("first slice permits one delegation")
    if protocol_version == 1 and action["sequence"] != 1:
        raise ContractError("first slice permits one delegation")
    if protocol_version == EXECUTION_PROTOCOL_VERSION and not 1 <= action["sequence"] <= 3:
        raise ContractError("action sequence exceeds the approved slice")
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION} and not 1 <= action["sequence"] <= 2:
        raise ContractError("mixed action sequence exceeds the approved slice")
    assignment = action_assignment(envelope, action["sequence"])
    if protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        for field in ("assignment_id", "definition_digest"):
            if action.get(field) != assignment[field]:
                raise ContractError(f"action {field} differs from approved assignment")
    for field in ("attempt_id", "role", "instance_id", "provider", "model", "task_digest"):
        expected = envelope[field] if field == "attempt_id" else assignment[field]
        if action[field] != expected:
            raise ContractError(f"action {field} differs from envelope")
    if action["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("action envelope digest mismatch")
    if action["action_id"] != expected_action_id(envelope, action["sequence"]):
        raise ContractError("action ID mismatch")


def expected_magentic_action_id(action: dict[str, Any]) -> str:
    fields = ("attempt_id", "envelope_digest", "assignment_id", "definition_digest", "instance_id",
              "sequence", "manager_turn", "task_digest", "parent_action_id", "checkpoint_id")
    identity = {"kind": "delegate", **{field: action[field] for field in fields}}
    if "provider_choice" in action:
        identity["provider_choice"] = action["provider_choice"]
    return digest(identity)


def _validate_magentic_action(envelope: dict[str, Any], action: dict[str, Any]) -> None:
    require_fields(action, ("assignment_id", "definition_digest", "manager_turn", "task", "rationale",
                            "checkpoint_id"), kind="Magentic action")
    if action["kind"] != "delegate" or type(action["sequence"]) is not int or not 1 <= action["sequence"] <= 2**31 - 1:
        raise ContractError("Magentic action sequence is invalid")
    if type(action["manager_turn"]) is not int or not 1 <= action["manager_turn"] <= 6:
        raise ContractError("Magentic manager turn is invalid")
    assignment = next((item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"]), None)
    if assignment is None:
        raise ContractError("Magentic selected an unlisted specialist")
    for field in ("definition_digest", "instance_id", "role", "provider", "model"):
        if action[field] != assignment[field]:
            raise ContractError(f"Magentic action {field} differs from roster")
    if action["attempt_id"] != envelope["attempt_id"] or action["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("Magentic action envelope link mismatch")
    if not isinstance(action["task"], str) or not action["task"].strip() or len(action["task"].encode()) > MAX_TASK_BYTES or hashlib.sha256(action["task"].encode()).hexdigest() != action["task_digest"]:
        raise ContractError("Magentic action task is invalid")
    if not isinstance(action["rationale"], str) or not action["rationale"].strip() or len(action["rationale"].encode()) > MAX_TASK_BYTES:
        raise ContractError("Magentic action rationale is invalid")
    if action.get("parent_action_id") is not None and not _hex_digest(action["parent_action_id"]):
        raise ContractError("Magentic parent action identity is invalid")
    if not isinstance(action["checkpoint_id"], str) or not action["checkpoint_id"].strip():
        raise ContractError("Magentic pending checkpoint is invalid")
    if action["action_id"] != expected_magentic_action_id(action):
        raise ContractError("Magentic action identity mismatch")
    if is_delivery_protocol(execution_protocol_version(envelope)):
        choice = action.get("provider_choice")
        required = {"eligible_candidates", "selected_candidate", "rationale", "rejection_reasons"}
        if not isinstance(choice, dict) or set(choice) != required:
            raise ContractError("Delivery Lead provider choice is absent")
        candidates = choice["eligible_candidates"]
        bindings = {item["instance_id"]: item for item in envelope["roster"]}
        group = (envelope["job_contract"]["producer_instance_ids"]
                 if action["instance_id"] in envelope["job_contract"]["producer_instance_ids"]
                 else envelope["job_contract"].get("evidence_collector_instance_ids", [])
                 if action["instance_id"] in envelope["job_contract"].get("evidence_collector_instance_ids", [])
                 else envelope["job_contract"]["verifier_instance_ids"]
                 if action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"] else [])
        expected_candidates = [{key: bindings[instance][key] for key in
                                ("assignment_id", "definition_digest", "instance_id", "role", "provider", "model")}
                               for instance in group]
        if candidates != expected_candidates:
            raise ContractError("Delivery Lead eligible candidates are invalid")
        if choice["selected_candidate"] != action["instance_id"] or action["instance_id"] not in {candidate["instance_id"] for candidate in candidates}:
            raise ContractError("Delivery Lead selected candidate differs from action")
        rationale = choice["rationale"]
        if (not isinstance(rationale, dict) or set(rationale) != {"manager_reason", "facts"}
                or not isinstance(rationale["manager_reason"], str) or not rationale["manager_reason"].strip()
                or not isinstance(rationale["facts"], list) or not rationale["facts"]
                or any(not isinstance(fact, str) or not fact.strip() for fact in rationale["facts"])):
            raise ContractError("Delivery Lead selection rationale is invalid")
        rejected = choice["rejection_reasons"]
        expected_rejected = {candidate["instance_id"] for candidate in candidates} - {action["instance_id"]}
        if (not isinstance(rejected, dict) or set(rejected) != expected_rejected
                or any(not isinstance(reason, dict) or set(reason) != {"reason", "facts"}
                       or not isinstance(reason["reason"], str) or not reason["reason"].strip()
                       or not isinstance(reason["facts"], list) or not reason["facts"]
                       or any(not isinstance(fact, str) or not fact.strip() for fact in reason["facts"])
                       for reason in rejected.values())):
            raise ContractError("Delivery Lead rejection reasons are invalid")


MAGENTIC_PHASES = frozenset({"facts", "plan", "progress", "replan", "replan_facts", "replan_plan", "final"})

# The provider session identity a paid v8 manager observation carries (ADR 0020).
MANAGER_IDENTITY_FIELDS = {"claude": ("session_id", "input_sha256", "num_turns"), "codex": ("thread_id",)}


def validate_manager_identity(provider: str, result: dict[str, Any]) -> None:
    """Require the adapter's session identity on a completed paid manager observation."""
    for field in MANAGER_IDENTITY_FIELDS.get(provider, ()):
        value = result.get(field) if isinstance(result, dict) else None
        if field == "input_sha256":
            valid = _hex_digest(value)
        elif field == "num_turns":
            valid = type(value) is int and value >= 1
        else:
            valid = isinstance(value, str) and bool(value.strip()) and len(value) <= 256
        if not valid:
            raise ContractError(f"manager observation lacks provider identity: {field}")


def expected_manager_call_id(request: dict[str, Any]) -> str:
    fields = ("attempt_id", "envelope_digest", "sequence", "phase", "manager_round", "prompt_digest")
    identity = {"kind": "manager_model", **{field: request[field] for field in fields}}
    if request["phase"] in {"replan_facts", "replan_plan"}:
        identity.update({field: request[field] for field in ("replan_sequence", "replan_id")})
    return digest(identity)


def validate_manager_call(envelope: dict[str, Any], request: dict[str, Any]) -> None:
    if not is_magentic_protocol(execution_protocol_version(envelope)):
        raise ContractError("manager calls require Magentic protocol")
    require_fields(request, ("call_id", "attempt_id", "envelope_digest", "sequence", "phase",
                             "manager_round", "prompt_digest"), kind="manager call")
    if type(request["sequence"]) is not int or not 1 <= request["sequence"] <= 2**31 - 1 or type(request["manager_round"]) is not int or not 1 <= request["manager_round"] <= 7:
        raise ContractError("manager call position is invalid")
    if request["phase"] not in MAGENTIC_PHASES or not _hex_digest(request["prompt_digest"]):
        raise ContractError("manager call phase or prompt digest is invalid")
    if request["phase"] in {"replan_facts", "replan_plan"}:
        if type(request.get("replan_sequence")) is not int or not 1 <= request["replan_sequence"] <= 3 or request.get("replan_id") != expected_replan_id(envelope, request["replan_sequence"]):
            raise ContractError("manager replan identity is invalid")
    elif "replan_sequence" in request or "replan_id" in request:
        raise ContractError("non-replan manager call carries replan authority")
    if request["attempt_id"] != envelope["attempt_id"] or request["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("manager call envelope link mismatch")
    if request["call_id"] != expected_manager_call_id(request):
        raise ContractError("manager call identity mismatch")


def expected_replan_id(envelope: dict[str, Any], sequence: int) -> str:
    protocol = execution_protocol_version(envelope)
    if is_magentic_protocol(protocol):
        if type(sequence) is not int or not 1 <= sequence <= 3:
            raise ContractError("replan sequence exceeds the approved slice")
        return digest({"attempt_id": envelope["attempt_id"], "envelope_digest": envelope_digest(envelope),
                       "execution_protocol_version": protocol, "kind": "replan", "sequence": sequence})
    if protocol != EXECUTION_PROTOCOL_VERSION:
        raise ContractError("replans require execution protocol v2")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or not 1 <= sequence <= 3:
        raise ContractError("replan sequence exceeds the approved slice")
    return digest({
        "attempt_id": envelope["attempt_id"],
        "charter_digest": envelope["charter_digest"],
        "definition_digest": envelope["definition_digest"],
        "instance_id": envelope["instance_id"],
        "execution_protocol_version": EXECUTION_PROTOCOL_VERSION,
        "kind": "replan",
        "sequence": sequence,
    })


def validate_replan(envelope: dict[str, Any], replan: dict[str, Any]) -> None:
    """Validate a Flow-owned replan request without giving it action authority."""
    if is_magentic_protocol(execution_protocol_version(envelope)):
        require_fields(replan, ("replan_id", "attempt_id", "envelope_digest", "sequence", "kind", "proposal"), kind="replan")
        if replan["kind"] != "replan" or type(replan["sequence"]) is not int or not 1 <= replan["sequence"] <= 3 or not isinstance(replan["proposal"], dict) or not replan["proposal"]:
            raise ContractError("Magentic replan proposal is invalid")
        if replan["attempt_id"] != envelope["attempt_id"] or replan["envelope_digest"] != envelope_digest(envelope) or replan["replan_id"] != expected_replan_id(envelope, replan["sequence"]):
            raise ContractError("Magentic replan identity mismatch")
        return
    require_fields(replan, ("replan_id", "attempt_id", "envelope_digest", "role", "instance_id", "provider", "model", "task_digest", "sequence", "kind", "proposal"), kind="replan")
    if execution_protocol_version(envelope) != EXECUTION_PROTOCOL_VERSION:
        raise ContractError("replans require execution protocol v2")
    if replan["kind"] != "replan" or not isinstance(replan["sequence"], int) or isinstance(replan["sequence"], bool) or not 1 <= replan["sequence"] <= 3:
        raise ContractError("replan sequence exceeds the approved slice")
    if not isinstance(replan["proposal"], dict) or not replan["proposal"]:
        raise ContractError("replan proposal is invalid")
    for field in ("attempt_id", "role", "instance_id", "provider", "model", "task_digest"):
        if replan[field] != envelope[field]:
            raise ContractError(f"replan {field} differs from envelope")
    if replan["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("replan envelope digest mismatch")
    if replan["replan_id"] != expected_replan_id(envelope, replan["sequence"]):
        raise ContractError("replan ID mismatch")


def validate_result(envelope: dict[str, Any], result: dict[str, Any], *, action: dict[str, Any] | None = None) -> None:
    require_fields(result, ("status", "provider", "model", "physical_call", "evidence_level", "output", "output_sha256"), kind="result")
    if is_magentic_protocol(execution_protocol_version(envelope)):
        if action is None:
            raise ContractError("Magentic result requires selected action identity")
        validate_action(envelope, action)
        assignment = next(item for item in envelope["roster"] if item["assignment_id"] == action["assignment_id"])
    elif execution_protocol_version(envelope) in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}:
        if action is None:
            raise ContractError("mixed result requires an action identity")
        validate_action(envelope, action)
        assignment = action_assignment(envelope, action["sequence"])
    else:
        assignment = envelope
    if result["status"] != "completed" or result["provider"] != assignment["provider"] or result["model"] != assignment["model"]:
        raise ContractError("result status, provider, or model differs from approved envelope")
    physical = assignment["provider"] in {"ollama", "codex", "claude"}
    if type(result["physical_call"]) is not bool or result["physical_call"] != physical:
        raise ContractError("result physical-call claim contradicts provider")
    expected_evidence = ({"ollama": "flow_observed_local_http_response", "codex": "flow_observed_codex_cli_completed_turn", "claude": "flow_observed_claude_cli_completed_turn", "local-stub": "local_stub"})[assignment["provider"]]
    if result["evidence_level"] != expected_evidence:
        raise ContractError("result evidence level contradicts provider")
    output = result["output"]
    if not isinstance(output, str) or not output or len(output.encode("utf-8")) > 4096:
        raise ContractError("result output is empty or too large")
    if hashlib.sha256(output.encode("utf-8")).hexdigest() != result["output_sha256"]:
        raise ContractError("result output digest mismatch")
    if assignment["provider"] == "claude" and (not isinstance(result.get("session_id"), str) or not result["session_id"]):
        raise ContractError("Claude result session identity is absent")
    if not usage_values_valid(result.get("usage")):
        raise ContractError("result usage is invalid")


def validate_receipt(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    protocol_version = execution_protocol_version(envelope)
    if is_magentic_protocol(protocol_version):
        _validate_magentic_receipt(envelope, receipt)
        return
    common = ("work_id", "attempt_id", "envelope_digest", "charter_digest", "manifest_digest", "status", "actions")
    paired = protocol_version in {MIXED_PROTOCOL_VERSION, CLAUDE_PROTOCOL_VERSION}
    require_fields(receipt, common + (() if paired else ("definition_digest", "provider")), kind="receipt")
    for field in ("work_id", "attempt_id", "charter_digest", "manifest_digest") + (() if paired else ("definition_digest", "provider")):
        if receipt[field] != envelope[field]:
            raise ContractError(f"receipt {field} link mismatch")
    if receipt["envelope_digest"] != envelope_digest(envelope):
        raise ContractError("receipt envelope link mismatch")
    if receipt.get("charter_sources") != envelope["charter_sources"] or receipt.get("run_protocol_revision") != envelope["run_protocol_revision"]:
        raise ContractError("receipt charter source link mismatch")
    if receipt["status"] not in {"completed", "failed", "denied", "unknown"} or not isinstance(receipt["actions"], list):
        raise ContractError("receipt status or actions invalid")
    if protocol_version == 1:
        return
    require_fields(receipt, ("execution_protocol_version", "replans", "checkpoints"), kind="versioned receipt")
    if receipt["execution_protocol_version"] != protocol_version:
        raise ContractError("receipt execution protocol link mismatch")
    if paired:
        if receipt.get("assignments") != envelope["assignments"]:
            raise ContractError("receipt mixed assignments link mismatch")
        if receipt["replans"] != []:
            raise ContractError("mixed receipt cannot claim replans")
        seen_sequences: set[int] = set()
        for item in receipt["actions"]:
            if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
                raise ContractError("mixed receipt action is invalid")
            request = item["request"]
            validate_action(envelope, request)
            sequence = request["sequence"]
            if sequence in seen_sequences or item.get("action_id") != request["action_id"]:
                raise ContractError("mixed receipt action identity is duplicated or changed")
            seen_sequences.add(sequence)
            if item.get("status") not in {"allowed", "started", "completed", "failed", "denied", "unknown", "not_dispatched"}:
                raise ContractError("mixed receipt action status is invalid")
            if item["status"] == "completed":
                if not isinstance(item.get("result"), dict):
                    raise ContractError("completed mixed action lacks a result")
                validate_result(envelope, item["result"], action=request)
            elif item.get("result") is not None and item["status"] != "failed":
                raise ContractError("mixed action result contradicts status")
        if receipt["status"] == "completed":
            if [item["request"]["sequence"] for item in receipt["actions"]] != [1, 2] or any(item["status"] != "completed" for item in receipt["actions"]):
                raise ContractError("completed mixed receipt requires both completed actions")
            if protocol_version == MIXED_PROTOCOL_VERSION:
                fixture_diff = receipt.get("fixture_diff")
                if not isinstance(fixture_diff, dict) or set(fixture_diff) != {"changed_files", "before_sha256", "after_sha256", "diff_sha256", "behavior_check"}:
                    raise ContractError("completed mixed receipt requires a fixture diff")
                if fixture_diff["changed_files"] != ["greet.py"] or fixture_diff["behavior_check"] != "passed":
                    raise ContractError("mixed fixture scope or behavior check is invalid")
                for key in ("before_sha256", "after_sha256", "diff_sha256"):
                    value = fixture_diff[key]
                    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                        raise ContractError("mixed fixture digest is invalid")
                if fixture_diff["before_sha256"] == fixture_diff["after_sha256"]:
                    raise ContractError("mixed fixture has no changed content")
            else:
                if receipt.get("source_commit") != envelope["source_commit"] or receipt.get("source_files") != envelope["source_files"]:
                    raise ContractError("Claude review source link mismatch")
                review = receipt.get("review_artifact")
                if not isinstance(review, dict) or set(review) != {"path", "sha256", "plan_sha256"} or review["path"] != "review-output.md":
                    raise ContractError("Claude review artifact link is invalid")
                for key in ("sha256", "plan_sha256"):
                    value = review[key]
                    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                        raise ContractError("Claude review artifact digest is invalid")
                if review["plan_sha256"] != receipt["actions"][0]["result"]["output_sha256"]:
                    raise ContractError("Claude review plan link mismatch")
    if not isinstance(receipt["replans"], list) or not isinstance(receipt["checkpoints"], list):
        raise ContractError("receipt v2 decision or checkpoint list is invalid")
    seen_replans: set[tuple[str, int]] = set()
    for replan in receipt["replans"]:
        if not isinstance(replan, dict) or not isinstance(replan.get("replan_id"), str) or not isinstance(replan.get("sequence"), int) or replan.get("status") not in {"allowed", "denied"} or not isinstance(replan.get("reason"), str):
            raise ContractError("receipt replan is invalid")
        key = (replan["replan_id"], replan["sequence"])
        if key in seen_replans:
            raise ContractError("receipt replan is duplicated")
        seen_replans.add(key)
    seen_positions: set[tuple[str, int]] = set()
    for checkpoint in receipt["checkpoints"]:
        if not isinstance(checkpoint, dict) or checkpoint.get("kind") not in {"delegate", "pending_delegate", "replan"} or not isinstance(checkpoint.get("sequence"), int) or not isinstance(checkpoint.get("file_sha256"), str) or len(checkpoint["file_sha256"]) != 64:
            raise ContractError("receipt checkpoint is invalid")
        position = (checkpoint["kind"], checkpoint["sequence"])
        if position in seen_positions:
            raise ContractError("receipt checkpoint position is duplicated")
        seen_positions.add(position)
    endpoint_evidence = receipt.get("endpoint_evidence")
    if endpoint_evidence is None:
        return
    if not isinstance(endpoint_evidence, dict) or endpoint_evidence.get("status") not in {"observed", "unavailable"} or not isinstance(endpoint_evidence.get("actions"), list):
        raise ContractError("receipt endpoint evidence is invalid")
    status = endpoint_evidence["status"]
    path, sha256 = endpoint_evidence.get("path"), endpoint_evidence.get("sha256")
    if (path is None) != (sha256 is None) or (path is not None and (not isinstance(path, str) or not path or not isinstance(sha256, str) or len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256))):
        raise ContractError("receipt endpoint evidence link is invalid")
    if status == "observed" and path is None:
        raise ContractError("observed endpoint evidence requires a sealed link")
    seen_actions: set[str] = set()
    for action in endpoint_evidence["actions"]:
        if not isinstance(action, dict) or not isinstance(action.get("action_id"), str) or not action["action_id"] or type(action.get("flow_send_observed")) is not bool:
            raise ContractError("receipt endpoint action evidence is invalid")
        arrivals = action.get("endpoint_arrivals")
        if arrivals is not None and (not isinstance(arrivals, int) or isinstance(arrivals, bool) or arrivals < 0):
            raise ContractError("receipt endpoint arrival count is invalid")
        if status == "unavailable" and arrivals is not None:
            raise ContractError("unavailable endpoint evidence cannot claim arrivals")
        if action["action_id"] in seen_actions:
            raise ContractError("receipt endpoint action evidence is duplicated")
        seen_actions.add(action["action_id"])


def manager_progress_block(manager_calls: list[dict[str, Any]]) -> dict[str, list[str]] | None:
    """Repaired and unparsable progress replies among completed manager calls (ADR 0018).

    Recomputed from each call's recorded request phase and response text, so a
    receipt cannot claim a different history than its own manager calls show.
    """
    block: dict[str, list[str]] = {"repaired": [], "unparsable": []}
    for call in manager_calls:
        if not isinstance(call, dict):
            raise ContractError("manager call entry is invalid")
        result = call.get("result")
        if (call.get("status") != "completed" or not isinstance(call.get("request"), dict)
                or call["request"].get("phase") != "progress" or not isinstance(result, dict)
                or not isinstance(result.get("output"), str)):
            continue
        kind = classify_progress(result["output"])
        if kind in block:
            block[kind].append(call["call_id"])
    return block if block["repaired"] or block["unparsable"] else None


def _validate_manager_progress(receipt: dict[str, Any]) -> None:
    """A present block must be v8, non-empty and match its own manager calls.

    Absence is checked against the ledger when the attempt seals; receipts
    sealed before ADR 0018 carry no block.
    """
    if "manager_progress" not in receipt:
        return
    if receipt["execution_protocol_version"] != 8:
        raise ContractError("manager_progress evidence requires protocol v8")
    block = receipt["manager_progress"]
    if block is None or block != manager_progress_block(receipt["manager_calls"]):
        raise ContractError("manager_progress evidence differs from the receipt's manager calls")


def _validate_token_usage(envelope: dict[str, Any], receipt: dict[str, Any], lineage: dict[str, int],
                          effective: dict[str, int]) -> None:
    """A handback receipt carries the token block its own rows recompute to; a pre-release one carries none.

    Required or not is read from the envelope, never from the receipt, so
    deleting the block from a handback receipt is a failure (ADR 0020).
    """
    if not handback_supported(envelope):
        if "token_usage" in receipt:
            raise ContractError("token usage requires a sealed token budget")
        return
    expected = token_usage_block(envelope, receipt["actions"], receipt["manager_calls"],
                                 predecessor_charged=lineage.get("predecessor_charged", 0),
                                 tranches_granted=effective["tokens"])
    if receipt.get("token_usage") != expected:
        raise ContractError("receipt token usage differs from its rows")


def _validate_magentic_receipt(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    require_fields(receipt, ("work_id", "attempt_id", "envelope_digest", "charter_digest", "manifest_digest",
                             "status", "execution_protocol_version", "roster", "manager_calls", "actions",
                             "replans", "checkpoints", "evidence"), kind="Magentic receipt", max_bytes=512 * 1024)
    protocol = execution_protocol_version(envelope)
    statuses = ({"completed", "failed", "denied"} | TERMINAL_UNCERTAIN_STATUSES if protocol == STRUCTURED_VERIFIER_PROTOCOL_VERSION
                else {"completed", "failed", "denied", "unknown"})
    if receipt["execution_protocol_version"] != protocol or receipt["status"] not in statuses:
        raise ContractError("Magentic receipt status or protocol is invalid")
    for field in ("work_id", "attempt_id", "charter_digest", "manifest_digest"):
        if receipt[field] != envelope[field]:
            raise ContractError(f"Magentic receipt {field} link mismatch")
    if receipt["envelope_digest"] != envelope_digest(envelope) or receipt.get("charter_sources") != envelope["charter_sources"] or receipt.get("run_protocol_revision") != envelope["run_protocol_revision"] or receipt["roster"] != envelope["roster"]:
        raise ContractError("Magentic receipt envelope or roster link mismatch")
    if is_delivery_protocol(execution_protocol_version(envelope)):
        for field in ("shaper_contract_digest", "delivery_charter_digest", "handoff_digest", "delivery_lead_claim_digest", "delivery_lead_claim"):
            if receipt.get(field) != envelope[field]:
                raise ContractError("Delivery receipt ownership link mismatch")
    if "maf_runtime" in envelope and receipt.get("maf_runtime") != envelope["maf_runtime"]:
        raise ContractError("Delivery receipt MAF runtime identity link mismatch")
    evidence = receipt["evidence"]
    if not isinstance(evidence, dict) or any(evidence.get(field) != envelope[field] for field in ("source_commit", "worktree", "allowed_paths")):
        raise ContractError("Magentic receipt source or scope link mismatch")
    for key in ("tree_sha256", "diff_sha256"):
        if key in evidence and not _hex_digest(evidence[key]):
            raise ContractError("Magentic receipt evidence digest is invalid")
    trace = evidence.get("diagnostic_trace")
    if trace is not None and (not isinstance(trace, dict)
                              or set(trace) != {"path", "sha256", "bytes"}
                              or trace["path"] != "claude-implementer.debug.log"
                              or not _hex_digest(trace["sha256"])
                              or type(trace["bytes"]) is not int
                              or not 0 <= trace["bytes"] <= 1024 * 1024):
        raise ContractError("Magentic diagnostic trace evidence is invalid")
    event_trace = evidence.get("event_trace")
    if event_trace is not None and (not isinstance(event_trace, dict)
                                    or set(event_trace) != {"path", "sha256", "bytes"}
                                    or event_trace["path"] != "claude-implementer.events.ndjson"
                                    or not _hex_digest(event_trace["sha256"])
                                    or type(event_trace["bytes"]) is not int
                                    or event_trace["bytes"] < 0):
        raise ContractError("Magentic event trace evidence is invalid")
    continuation = evidence.get("continuation")
    if continuation is not None and (not isinstance(continuation, dict)
                                     or set(continuation) != {"epoch_id", "original_receipt_sha256",
                                                              "checkpoint_sha256", "resolution_id"}
                                     or not all(isinstance(continuation[key], str) and continuation[key]
                                                for key in ("epoch_id", "resolution_id"))
                                     or not _hex_digest(continuation["original_receipt_sha256"])
                                     or not _hex_digest(continuation["checkpoint_sha256"])):
        raise ContractError("Magentic continuation evidence is invalid")
    for key in ("manager_calls", "actions", "replans", "checkpoints"):
        if not isinstance(receipt[key], list):
            raise ContractError("Magentic receipt decision list is invalid")
    seen_calls: set[str] = set()
    for item in receipt["manager_calls"]:
        if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
            raise ContractError("Magentic manager receipt is invalid")
        request = item["request"]
        validate_manager_call(envelope, request)
        if item.get("call_id") != request["call_id"] or request["call_id"] in seen_calls or item.get("status") not in {"allowed", "started", "completed", "denied", "unknown"}:
            raise ContractError("Magentic manager receipt identity or status is invalid")
        seen_calls.add(request["call_id"])
        if item["status"] == "completed" and not isinstance(item.get("result"), dict):
            raise ContractError("Magentic completed manager call lacks observed result")
        if item["status"] == "completed" and handback_supported(envelope):
            validate_manager_identity(envelope["manager"].get("provider", "claude"), item["result"])
    # After the manager calls themselves are validated, so recomputation reads sound entries.
    _validate_manager_progress(receipt)
    seen_actions: set[str] = set()
    for item in receipt["actions"]:
        if not isinstance(item, dict) or not isinstance(item.get("request"), dict):
            raise ContractError("Magentic action receipt is invalid")
        action = item["request"]
        validate_action(envelope, action)
        if item.get("action_id") != action["action_id"] or action["action_id"] in seen_actions or item.get("status") not in {"allowed", "started", "completed", "failed", "denied", "unknown", "not_dispatched"}:
            raise ContractError("Magentic action receipt identity or status is invalid")
        seen_actions.add(action["action_id"])
        if item["status"] == "completed":
            is_structured_verifier = (has_structured_verifier_evaluations(execution_protocol_version(envelope))
                                      and action["instance_id"] in envelope["job_contract"]["verifier_instance_ids"])
            if not is_structured_verifier:
                validate_result(envelope, item.get("result"), action=action)
    if has_structured_verifier_evaluations(execution_protocol_version(envelope)):
        inputs = receipt.get("verifier_inputs")
        evaluations = receipt.get("verifier_evaluations")
        usage = receipt.get("verifier_usage")
        if not isinstance(inputs, list) or not isinstance(evaluations, list) or not isinstance(usage, dict) or set(usage) != {
                "maximum", "reserved", "consumed", "denied", "retry_eligible"}:
            raise ContractError("structured verifier receipt evidence is invalid")
        effective = _validate_expansion(envelope, receipt)
        if usage["maximum"] != effective["verifier_calls"] or any(
                type(usage[key]) is not int or usage[key] < 0 for key in ("maximum", "reserved", "consumed", "denied")) or type(usage["retry_eligible"]) is not bool:
            raise ContractError("structured verifier usage is invalid")
        action_ids = {item["action_id"] for item in receipt["actions"]}
        verifier_ids = set(envelope["job_contract"]["verifier_instance_ids"])
        verifier_actions = [item for item in receipt["actions"]
                            if item["request"]["instance_id"] in verifier_ids]
        input_by_action: dict[str, dict[str, Any]] = {}
        for item in inputs:
            if (not isinstance(item, dict) or item.get("action_id") not in action_ids
                    or item["action_id"] in input_by_action or not _hex_digest(item.get("input_digest"))
                    or not _hex_digest(item.get("diff_digest")) or not _hex_digest(item.get("test_digest"))
                    or not isinstance(item.get("input"), dict)
                    or item["input_digest"] != digest(item["input"])
                    or item["input"].get("action_id") != item["action_id"]
                    or not isinstance(item["input"].get("provider_task"), str)
                    or not item["input"]["provider_task"].endswith(VERIFIER_CONTRACT_INSTRUCTION)):
                raise ContractError("structured verifier input binding is invalid")
            input_by_action[item["action_id"]] = item
        seen_evaluations: set[str] = set()
        for item in evaluations:
            evaluation = item.get("evaluation") if isinstance(item, dict) else None
            try:
                validate_evaluation(evaluation)
            except ValueError as exc:
                raise ContractError("structured verifier evaluation is invalid") from exc
            action_id = evaluation["action_id"]
            action_item = next((entry for entry in receipt["actions"] if entry["action_id"] == action_id), None)
            result = action_item.get("result") if isinstance(action_item, dict) else None
            output = result.get("output") if isinstance(result, dict) else None
            input_binding = input_by_action.get(action_id)
            action_request = action_item.get("request") if isinstance(action_item, dict) else None
            if (action_id not in action_ids or action_id in seen_evaluations
                    or not isinstance(action_request, dict)
                    or action_request.get("instance_id") not in verifier_ids
                    or item.get("evaluation_digest") != evaluation["evaluation_digest"]
                    or item.get("outcome") != evaluation["disposition"]
                    or action_item.get("status") != "completed"
                    or not isinstance(output, str)
                    or result.get("output_sha256") != hashlib.sha256(output.encode()).hexdigest()
                    or evaluation["raw_output_digest"] != result["output_sha256"]
                    or input_binding is None
                    or evaluation["verifier_input_digest"] != input_binding["input_digest"]
                    or evaluation["diff_digest"] != input_binding["diff_digest"]
                    or evaluation["test_evidence_digest"] != input_binding["test_digest"]):
                raise ContractError("structured verifier evaluation binding is invalid")
            # Flow's judgment is deterministic, so the receipt must carry
            # exactly what Flow would decide again from the bound facts.
            try:
                validate_structured_verifier_result(result)
                recomputed = evaluate_candidate(
                    action_id=action_id, verifier_input_digest=input_binding["input_digest"], raw_output=output,
                    diff_digest=input_binding["diff_digest"], test_evidence_digest=input_binding["test_digest"],
                    forced_unusable_reason=("provider_binding_mismatch"
                                            if provider_binding_mismatch(action_request, result) else None))
            except ValueError as exc:
                raise ContractError("structured verifier evaluation is invalid") from exc
            if recomputed != evaluation:
                raise ContractError("structured verifier evaluation differs from Flow recomputation")
            seen_evaluations.add(action_id)
        if seen_evaluations != {item["action_id"] for item in verifier_actions if item["status"] == "completed"}:
            raise ContractError("every completed structured verifier requires exactly one evaluation")
        reserved = sum(item["status"] in {"allowed", "started", "completed", "failed", "unknown"}
                       for item in verifier_actions)
        consumed = sum(item["status"] in {"started", "completed", "failed", "unknown"}
                       for item in verifier_actions)
        denied = sum(item["status"] == "denied" and item.get("reason") in {
            "verifier_call_cap", "verifier_retry_denied"} for item in verifier_actions)
        latest = evaluations[-1]["outcome"] if evaluations else None
        lineage = _validate_lineage_usage(envelope, receipt, effective)
        expected_usage = {"maximum": effective["verifier_calls"],
                          "reserved": reserved, "consumed": consumed, "denied": denied,
                          "retry_eligible": latest in {"valid_fail", "unusable"}
                          and reserved + lineage["predecessor_verifier_sends"] < effective["verifier_calls"]}
        if usage != expected_usage:
            raise ContractError("structured verifier usage differs from receipt facts")
        _validate_recovery_block(envelope, receipt)
        _validate_termination(envelope, receipt)
        _validate_token_usage(envelope, receipt, lineage, effective)
    if receipt["status"] == "completed":
        completed = [item["request"] for item in receipt["actions"] if item["status"] == "completed"]
        if is_chartered_protocol(execution_protocol_version(envelope)):
            if has_structured_verifier_evaluations(execution_protocol_version(envelope)):
                if (not receipt["verifier_evaluations"]
                        or receipt["verifier_evaluations"][-1]["evaluation"]["disposition"] != "valid_pass"):
                    raise ContractError("completed structured verifier receipt requires a valid pass")
                final = receipt["verifier_evaluations"][-1]["evaluation"]
                if (final["diff_digest"] != (evidence.get("edit") or {}).get("diff_sha256")
                        or final["test_evidence_digest"] != (evidence.get("tests") or {}).get("output_sha256")):
                    raise ContractError("completed structured verifier pass is not bound to the receipt evidence")
            _validate_chartered_completion(envelope, evidence, completed)
            return
        producers = [item for item in completed if item["role"] == "lead-developer" and item["provider"] == "claude"]
        if len(producers) != 1 or not any(item["role"] == "test-engineer" and item["instance_id"] != producers[0]["instance_id"] and item["sequence"] > producers[0]["sequence"] for item in completed):
            raise ContractError("completed Magentic receipt requires Claude producer and later distinct verifier")
        baseline, edit, tests = (evidence.get(key) for key in ("baseline", "edit", "tests"))
        if not isinstance(baseline, dict) or baseline.get("source_commit") != envelope["source_commit"] or not _hex_digest(baseline.get("regression_diff_sha256")) or not isinstance(baseline.get("files"), dict) or not all(_hex_digest(v) for v in baseline["files"].values()):
            raise ContractError("Magentic baseline evidence is invalid")
        if not isinstance(edit, dict) or not isinstance(edit.get("changed_files"), list) or not edit["changed_files"] or not set(edit["changed_files"]).issubset(set(envelope["allowed_paths"])) or "cli/codex_worker.py" not in edit["changed_files"] or not _hex_digest(edit.get("diff_sha256")) or not isinstance(edit.get("diff_path"), str) or not edit["diff_path"] or not isinstance(edit.get("files"), dict) or not all(_hex_digest(v) for v in edit["files"].values()):
            raise ContractError("Magentic edit evidence is invalid")
        if not isinstance(tests, dict) or tests.get("status") != "passed" or not isinstance(tests.get("command"), list) or not tests["command"] or not all(isinstance(v, str) and v for v in tests["command"]) or not _hex_digest(tests.get("output_sha256")):
            raise ContractError("Magentic focused test evidence is invalid")


def _validate_termination(envelope: dict[str, Any], receipt: dict[str, Any]) -> None:
    """Uncertain rows seal only as cancelled or abandoned, with who stopped it and what was lost (ADR 0019)."""
    terminal = receipt["status"] in TERMINAL_UNCERTAIN_STATUSES
    uncertain = any(item["status"] in {"started", "unknown"} for item in receipt["actions"] + receipt["manager_calls"])
    if uncertain and not terminal:
        raise ContractError("only a cancelled or abandoned receipt may keep an uncertain send")
    if not terminal:
        if "termination" in receipt or "evidence_damage" in receipt:
            raise ContractError("termination evidence requires a cancelled or abandoned receipt")
        return
    termination, damage = receipt.get("termination"), receipt.get("evidence_damage")
    claim_generation = envelope["delivery_lead_claim"]["generation"]
    text = lambda value, limit: isinstance(value, str) and value.strip() and len(value) <= limit
    if (not isinstance(termination, dict)
            or set(termination) != {"actor", "explanation", "cause", "owner_generation", "lead_generation"}
            or not text(termination["actor"], 256) or not text(termination["explanation"], 2048)
            or not isinstance(termination["cause"], str) or not 1 <= len(termination["cause"]) <= 64
            or any(not (char.islower() or char == "_") for char in termination["cause"])
            or (receipt["status"] == "cancelled") != (termination["cause"] == "cancel_request")
            or termination["lead_generation"] != claim_generation
            or type(termination["owner_generation"]) is not int or termination["owner_generation"] < claim_generation):
        raise ContractError("receipt termination is invalid")
    if not isinstance(damage, list):
        raise ContractError("receipt evidence damage is invalid")
    kinds = []
    for item in damage:
        if (not isinstance(item, dict) or set(item) != EVIDENCE_DAMAGE_KEYS.get(item.get("kind"))
                or ("sha256" in item and not _hex_digest(item["sha256"]))
                or ("bytes" in item and (type(item["bytes"]) is not int or item["bytes"] < 0))
                or ("path" in item and item["path"] not in {"claude-implementer.debug.log", "claude-implementer.events.ndjson"})):
            raise ContractError("receipt evidence damage is invalid")
        kinds.append((item["kind"], item.get("path")))
    if len(kinds) != len(set(kinds)):
        raise ContractError("receipt evidence damage is duplicated")
    recovery = receipt.get("recovery")
    replaced = recovery.get("replaced_draft_sha256") if isinstance(recovery, dict) else None
    listed = [item["sha256"] for item in damage if item["kind"] == "draft_receipt_replaced"]
    if replaced is not None and listed != [replaced]:
        raise ContractError("receipt replaced draft differs from its evidence damage")


def _validate_chartered_completion(envelope: dict[str, Any], evidence: dict[str, Any],
                                   completed: list[dict[str, Any]]) -> None:
    job = envelope["job_contract"]
    producers = [action for action in completed if action["instance_id"] in job["producer_instance_ids"]]
    if len(producers) != 1 or not any(action["instance_id"] in job["verifier_instance_ids"]
                                      and action["instance_id"] != producers[0]["instance_id"]
                                      and action["sequence"] > producers[0]["sequence"]
                                      for action in completed):
        raise ContractError("completed chartered receipt requires producer and later distinct verifier")
    baseline, edit, tests = (evidence.get(key) for key in ("baseline", "edit", "tests"))
    if (not isinstance(baseline, dict) or baseline.get("source_commit") != envelope["source_commit"]
            or baseline.get("regression_diff_sha256") != job["baseline"]["diff_sha256"]
            or not isinstance(baseline.get("files"), dict)
            or not all(_hex_digest(value) for value in baseline["files"].values())):
        raise ContractError("chartered baseline evidence is invalid")
    if (not isinstance(edit, dict) or not _paths_within_scopes(edit.get("changed_files"), job["write_paths"])
            or not _hex_digest(edit.get("diff_sha256")) or not isinstance(edit.get("diff_path"), str)
            or not edit["diff_path"] or not isinstance(edit.get("files"), dict)
            or not all(_hex_digest(value) for value in edit["files"].values())):
        raise ContractError("chartered edit evidence is invalid")
    if (not isinstance(tests, dict) or tests.get("status") != "passed"
            or tests.get("command") != job["test"]["argv"]
            or not _hex_digest(tests.get("output_sha256"))
            or ("output_excerpt" in tests and (
                not isinstance(tests["output_excerpt"], str)
                or len(tests["output_excerpt"].encode()) > 8192
                or hashlib.sha256(tests["output_excerpt"].encode()).hexdigest() != tests["output_sha256"]
            ))):
        raise ContractError("chartered test evidence is invalid")


RECOVERY_DISPOSITIONS = frozenset({"resolved_completed", "resolved_not_dispatched", "still_unknown"})


def validate_recovery_evidence(evidence: list[dict[str, Any]]) -> None:
    """Validate immutable evidence references used by an operator resolution.

    The ledger deliberately retains references and digests rather than mutable
    evidence bytes. Callers that accept filesystem paths must independently
    verify the path and its digest before recording this contract.
    """
    if not isinstance(evidence, list) or not evidence:
        raise ContractError("recovery resolution requires immutable evidence")
    seen: set[tuple[str, str]] = set()
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"kind", "path", "sha256"}:
            raise ContractError("recovery evidence is invalid")
        if not isinstance(item["kind"], str) or not item["kind"].strip() or not isinstance(item["path"], str) or not item["path"].strip():
            raise ContractError("recovery evidence is invalid")
        value = item["sha256"]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ContractError("recovery evidence digest is invalid")
        key = (item["path"], value)
        if key in seen:
            raise ContractError("recovery evidence is duplicated")
        seen.add(key)


def validate_recovery_resolution(disposition: str, explanation: str, evidence: list[dict[str, Any]]) -> None:
    if disposition not in RECOVERY_DISPOSITIONS:
        raise ContractError("recovery disposition is invalid")
    if not isinstance(explanation, str) or not explanation.strip() or len(explanation.encode("utf-8")) > 4096:
        raise ContractError("recovery explanation is invalid")
    validate_recovery_evidence(evidence)
