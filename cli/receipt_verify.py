"""``flow run verify-receipt``: verify a sealed v8 receipt offline against its sources (ADR 0020).

Read-only and offline. The ledger is read in one read transaction through
``lineage_view``; every other source is a file under the run directory. No
provider, subprocess or network call is made, no diff is applied and no test
runs. Each check compares in full and names how many facts it compared; a
required input that is missing fails, so nothing passes vacuously.

Verification is a consistency check, not a signature: anyone who can write
``.flow`` can rewrite every source consistently.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Callable

from delivery_contracts import (DeliveryContractError, digest as delivery_digest, project_envelope_limits,
                                validate_delivery_charter, validate_shaper_contract)
from delivery_recovery import build_recovery_block
from execution_contracts import (PAID_PROVIDERS, SENT_STATUSES, ContractError, attempt_token_charges, canonical,
                                 charge, digest, handback_supported, token_maximum, validate_receipt)
from execution_ledger import ExecutionLedger
from fsutil import repo_root
from manager_requests import REQUEST_DIR, list_request_files, render_manager_prompt
from receipt_compare import DERIVED_BLOCKS, ROW_BLOCKS, compare_receipt_rows, describe, expected_blocks
from verifier_contracts import VERIFIED_HANDOFF_AUTHORITY, verifier_provider_task
import process_identity
from selection_receipt import verify_selection_receipt_snapshot as verify_v9_selection_receipt_snapshot

SCHEMA_VERSION = 1
# A v8 attempt never seals ``denied``; such a receipt is refused rather than judged against a missing column.
TERMINAL = frozenset({"completed", "failed", "cancelled", "abandoned"})
MAX_FILE_BYTES = 8 * 1024 * 1024
WORKFLOW_NAME = "flow-magentic-delivery-v8"
SEND_START = {"manager_call": "manager_send_started", "producer": "worker_dispatched", "verifier": "verifier_send_claimed"}
UNVERIFIABLE = (
    ("provider_ran", "that a provider actually ran, and what it billed: Flow keeps only what the CLI reported"),
    ("unknown_outcome", "the outcome of an unknown send: no response was observed"),
    ("test_output", "the test output bytes: only their digest is kept"),
    ("worktree", "the current worktree: it is not evidence once the attempt is sealed"),
    ("replaced_draft", "the bytes of a replaced draft receipt: only its digest is kept"),
    ("timestamps", "the truth of ledger timestamps: they are recorded, not attested"),
)
NAMES = {
    "V1": "sealed digest", "V2": "envelope and receipt validation", "V3": "ledger rows",
    "V4": "derived blocks", "V5": "recovery and termination", "V6": "predecessors", "V7": "sealed authority",
    "V8": "source snapshots", "V9": "bound checkpoints", "V10": "manager request files", "V11": "edit chain",
    "V12": "test chain", "V13": "baseline", "V14": "traces", "V15": "events", "V16": "process groups",
    "V17": "token gate replay",
}


class VerifyRefused(Exception):
    """Verification cannot run; the CLI exits 2 with ``code``."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


class Absent(Exception):
    """A check's input is missing; requiredness decides whether that fails."""


def _required_if(predicate: Callable[[dict[str, Any]], bool]) -> Callable[[dict[str, Any]], str]:
    return lambda ctx: "R" if predicate(ctx) else "P"


def _has_predecessors(ctx):
    return bool(ctx["envelope"].get("predecessors"))


def _claude_editor_sent(ctx):
    # Read from the ledger snapshot, never the receipt (ADR 0020).
    return any(item["status"] in SENT_STATUSES and item["request"].get("provider") == "claude"
               and item["request"].get("instance_id") in ctx["job"]["producer_instance_ids"] for item in ctx["actions"].values())


# R14: required (R), checked if present (P), or not applicable (-), per terminal status.
REQUIREDNESS: dict[str, dict[str, Any]] = {
    **{check: {status: "R" for status in ("completed", "failed", "cancelled", "abandoned")}
       for check in ("V1", "V2", "V3", "V4", "V7", "V8", "V15", "V17")},
    "V5": {"completed": "P", "failed": "P", "cancelled": "R", "abandoned": "R"},
    "V6": {status: _required_if(_has_predecessors) for status in ("completed", "failed", "cancelled", "abandoned")},
    "V9": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
    "V10": {"completed": "R", "failed": _required_if(lambda ctx: bool(ctx["issued_calls"])), "cancelled": "P",
            "abandoned": "P"},
    "V11": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
    "V12": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
    "V13": {"completed": "R", "failed": "R", "cancelled": "P", "abandoned": "P"},
    "V14": {"completed": _required_if(_claude_editor_sent), "failed": _required_if(_claude_editor_sent),
            "cancelled": "P", "abandoned": "P"},
    "V16": {"completed": "R", "failed": "R", "cancelled": "P", "abandoned": "P"},
}
NA_REASONS = {
    "V5": "no recovery ran and the attempt was not cancelled or abandoned",
    "V6": "the attempt has no predecessors",
    "V9": "no checkpoint was bound",
    "V10": "no manager call was granted",
    "V11": "no edit was verified",
    "V12": "no test evidence was bound",
    "V13": "no baseline was recorded",
    "V14": "no trace was recorded",
    "V16": "no provider group was recorded",
}


# ------------------------------------------------------------------ files


def _read(path: Path, root: Path, *, limit: int = MAX_FILE_BYTES) -> bytes | None:
    """A regular file under ``root``, never following a symlink, never past ``limit``; None when absent."""
    try:
        resolved = path.parent.resolve(strict=True)
    except FileNotFoundError:
        return None
    if root.resolve() not in (resolved, *resolved.parents):
        raise ContractError(f"{path.name} is outside the run directory")
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ContractError(f"{path.name} is unsafe: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ContractError(f"{path.name} is not a regular file")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            data = handle.read(limit + 1)
    finally:
        if fd != -1:
            os.close(fd)
    if len(data) > limit:
        raise ContractError(f"{path.name} exceeds the verification size limit")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes | None) -> Any:
    if data is None:
        return None
    try:
        return json.loads(data)
    except (ValueError, RecursionError) as exc:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        raise ContractError(f"not JSON: {type(exc).__name__}") from exc


_DIGEST = re.compile(r"[0-9a-f]{64}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
MAX_DIRECTORY_ENTRIES = 4096


def _entries(directory: Path, pattern: str = "*") -> list[Path]:
    """At most MAX_DIRECTORY_ENTRIES entries of a real directory; more is a failure, not a slow read."""
    if directory.is_symlink() or not directory.is_dir():
        return []
    found = []
    for path in directory.glob(pattern):
        found.append(path)
        if len(found) > MAX_DIRECTORY_ENTRIES:
            raise ContractError(f"{directory.name}/ has more than {MAX_DIRECTORY_ENTRIES} entries")
    return sorted(found)


def _within_declared_paths(path: str, scopes: set[str]) -> bool:
    """Return whether a repository-relative path is equal to or below a scope."""
    return any(path == scope or path.startswith(scope.rstrip("/") + "/") for scope in scopes)


def _same_delivery_authority(current: dict[str, Any], prior: dict[str, Any]) -> bool:
    return prior.get("delivery_charter_digest") == current.get("delivery_charter_digest")


# ------------------------------------------------------------------ helpers


def _events(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return snapshot["events"]


def _detail(event: dict[str, Any]) -> Any:
    try:
        return json.loads(event["detail"])
    except (TypeError, json.JSONDecodeError):
        return event["detail"]


def _row_kind(ctx: dict[str, Any], row_id: str) -> str:
    if row_id in ctx["calls"]:
        return "manager_call"
    request = ctx["actions"][row_id]["request"]
    return "verifier" if request.get("instance_id") in ctx["job"]["verifier_instance_ids"] else "producer"


def _paid(ctx: dict[str, Any], row_id: str) -> bool:
    if row_id in ctx["calls"]:
        return ctx["manager_provider"] in PAID_PROVIDERS
    return ctx["actions"][row_id]["request"].get("provider") in PAID_PROVIDERS


def _grant_history(snapshot: dict[str, Any]) -> dict[str, list[tuple[str, str | None]]]:
    history: dict[str, list[tuple[str, str | None]]] = {}
    for event in _events(snapshot):
        if event["event"] == "grant_changed":
            detail = _detail(event)
            if isinstance(detail, dict):
                history.setdefault(event["action_id"], []).append((detail.get("op"), detail.get("grant_id")))
    return history


# ------------------------------------------------------------------ checks (status, compared, detail)


def check_v1(ctx):
    receipt_bytes, entry = ctx["receipt_bytes"], ctx["entry"]
    if receipt_bytes is None:
        return "fail", 1, (f"the sealed receipt file is unsafe: {ctx['receipt_unsafe']}" if ctx.get("receipt_unsafe")
                           else "the sealed receipt file is missing")
    compared = 0
    if _sha(receipt_bytes) != entry["sealed_receipt_sha256"]:
        return "fail", 1, f"receipt sha256 {_sha(receipt_bytes)[:16]} differs from the sealed {str(entry['sealed_receipt_sha256'])[:16]}"
    compared += 1
    recorded = ctx["snapshot"].get("receipt_path") or ""
    if not recorded.replace("\\", "/").endswith(f"execution/{ctx['attempt_id']}/receipt.json"):
        return "fail", compared + 1, f"the ledger receipt_path names another file: {recorded[-80:]}"
    compared += 1
    if entry["status"] not in TERMINAL or ctx["receipt"].get("status") != entry["status"]:
        return "fail", compared + 1, f"ledger status {entry['status']} and receipt status {ctx['receipt'].get('status')} differ"
    return "pass", compared + 1, "file digest, receipt path and terminal status match the ledger"


def check_v2(ctx):
    data = _read(ctx["attempt_dir"] / "envelope.json", ctx["run_dir"])
    if data is None:
        raise Absent("envelope.json is missing")
    if data != (canonical(ctx["envelope"]) + "\n").encode():
        return "fail", 1, "envelope.json differs from the ledger envelope"
    try:
        validate_receipt(ctx["envelope"], ctx["receipt"])
    except ContractError as exc:
        return "fail", 2, f"validate_receipt: {exc}"
    return "pass", 2, "envelope.json equals the ledger envelope; validate_receipt passes"


def check_v3(ctx):
    expected = expected_blocks(ctx["snapshot"], ctx["blocks"])
    if ctx["status"] == "completed" and not ctx["snapshot"]["actions"]:
        return "fail", 0, "required block empty: the ledger has no action rows for a completed attempt"
    mismatches = compare_receipt_rows(ctx["receipt"], expected, blocks=ROW_BLOCKS)
    rows = sum(len(expected[key]) if isinstance(expected[key], list) else 1 for key in ROW_BLOCKS)
    if mismatches:
        return "fail", rows, describe(mismatches[0])
    return "pass", rows, f"{rows} rows across {len(ROW_BLOCKS)} blocks equal the ledger, key for key"


def check_v4(ctx):
    expected = expected_blocks(ctx["snapshot"], ctx["blocks"])
    mismatches = compare_receipt_rows(ctx["receipt"], expected, blocks=DERIVED_BLOCKS)
    if mismatches:
        return "fail", len(DERIVED_BLOCKS), describe(mismatches[0])
    return "pass", len(DERIVED_BLOCKS), "lineage, expansion, manager progress and token blocks equal the seal's own"


def check_v5(ctx):
    snapshot, receipt, compared = ctx["snapshot"], ctx["receipt"], 0
    if snapshot.get("recoveries") or "recovery" in receipt:
        replaced = (receipt.get("recovery") or {}).get("replaced_draft_sha256")
        expected = build_recovery_block(snapshot, replaced_draft_sha256=replaced) if snapshot.get("recoveries") else None
        if receipt.get("recovery") != expected:
            return "fail", 1, "recovery block differs from the one the ledger rebuilds"
        compared += 1
    if ctx["status"] in {"cancelled", "abandoned"}:
        try:
            recorded = json.loads(snapshot.get("reason") or "")
        except json.JSONDecodeError:
            return "fail", compared + 1, "the ledger termination reason is not a record"
        termination = receipt.get("termination") or {}
        for key in ("actor", "cause", "owner_generation"):
            if termination.get(key) != recorded.get(key):
                return "fail", compared + 1, f"termination.{key}: expected {recorded.get(key)!r}, found {termination.get(key)!r}"
        if termination.get("lead_generation") != ctx["envelope"]["delivery_lead_claim"]["generation"]:
            return "fail", compared + 1, "termination.lead_generation differs from the envelope claim"
        compared += 1
    elif "termination" in receipt:
        return "fail", compared + 1, "a termination block on a status that was never cancelled or abandoned"
    if not compared:
        raise Absent("no recovery and no termination")
    return "pass", compared, "recovery and termination equal the ledger (the explanation is receipt-only)"


def check_v6(ctx):
    predecessors = ctx["envelope"].get("predecessors", [])
    if not predecessors:
        raise Absent("no predecessors")
    by_id = ctx["view_entries"]
    target_index = [item["attempt_id"] for item in ctx["work_lineage"]].index(ctx["attempt_id"]) \
        if ctx["attempt_id"] in [item["attempt_id"] for item in ctx["work_lineage"]] else len(ctx["work_lineage"])
    if predecessors != ctx["work_lineage"][:target_index]:
        return "fail", 1, "the predecessor list differs from the ledger lineage before this attempt"
    compared, charged = 1, 0
    for link in predecessors:
        entry = by_id.get(link["attempt_id"])
        if entry is None:
            return "fail", compared, f"predecessor {link['attempt_id']} is missing from the ledger view"
        prior = json.loads(entry["envelope_json"])
        if link["receipt_sha256"] is None:
            # Superseded: no receipt exists; its charge comes from the ledger only.
            charged += attempt_token_charges({**prior, "limits": ctx["envelope"]["limits"]} if not handback_supported(prior)
                                             else prior, entry["snapshot"]["actions"], entry["snapshot"]["manager_calls"])["charged"]
            compared += 1
            continue
        data = _read(ctx["run_dir"] / "execution" / link["attempt_id"] / "receipt.json", ctx["run_dir"])
        if data is None or entry["sealed_receipt_sha256"] != link["receipt_sha256"] or _sha(data) != link["receipt_sha256"]:
            return "fail", compared, f"predecessor {link['attempt_id'][:12]} receipt digest differs from its link"
        compared += 1
        prior_receipt = _json(data)
        same_authority = _same_delivery_authority(ctx["envelope"], prior)
        if handback_supported(ctx["envelope"]) and same_authority:
            charges = prior if handback_supported(prior) else {**prior, "limits": ctx["envelope"]["limits"]}
            charged += attempt_token_charges(charges, prior_receipt["actions"], prior_receipt["manager_calls"])["charged"]
        if ctx["recurse"] and not same_authority:
            ctx["informational"].append({"check": "V6", "item": "predecessor_other_authority",
                                         "attempt_id": link["attempt_id"],
                                         "detail": "predecessor receipt belongs to a superseded Delivery Charter"})
        elif ctx["recurse"] and not handback_supported(prior):
            # A pre-release receipt is never judged by ADR 0020 rules (P9); its link and charge are checked above.
            ctx["informational"].append({"check": "V6", "item": "predecessor_not_recursed",
                                         "attempt_id": link["attempt_id"], "detail": "predecessor predates ADR 0020"})
        elif ctx["recurse"]:
            memo = ctx["base"].setdefault("memo", {})
            if link["attempt_id"] not in memo:
                memo[link["attempt_id"]] = _verify_entry(ctx["base"], entry, recurse=True)
            nested = memo[link["attempt_id"]]
            failed = [item for item in nested["checks"] if item["status"] == "fail"]
            if failed:
                return "fail", compared, (f"predecessor {link['attempt_id'][:12]} fails "
                                          + ", ".join(f"{item['check']} ({item['detail'][:80]})" for item in failed))
    if handback_supported(ctx["envelope"]):
        recorded = (ctx["receipt"].get("lineage_usage") or {}).get("predecessor_charged")
        if recorded != charged:
            return "fail", compared + 1, f"lineage_usage.predecessor_charged: expected {charged}, found {recorded}"
        compared += 1
    return "pass", compared, f"{len(predecessors)} predecessor link(s) match" + ("" if ctx["recurse"] else " (not recursed)")


def check_v7(ctx):
    envelope, run_dir = ctx["envelope"], ctx["run_dir"]
    if not isinstance(envelope.get("delivery_charter_digest"), str) or not _DIGEST.fullmatch(envelope["delivery_charter_digest"]):
        return "fail", 0, "the envelope's delivery_charter_digest is not a digest"
    directory = run_dir / "delivery" / envelope["delivery_charter_digest"]
    shaper = _json(_read(directory / "shaper-contract.json", run_dir))
    charter = _json(_read(directory / "delivery-charter.json", run_dir))
    handoff = _json(_read(directory / "handoff.json", run_dir))
    if not all(isinstance(item, dict) for item in (shaper, charter, handoff)):
        raise Absent("a sealed authority file is missing")
    try:
        validate_shaper_contract(shaper)
        validate_delivery_charter(charter)
    except DeliveryContractError as exc:
        return "fail", 1, f"sealed contract invalid: {exc}"
    handoff_payload = {key: value for key, value in handoff.items() if key != "digest"}
    for label, found, expected in (("Shaper Contract", shaper["digest"], envelope["shaper_contract_digest"]),
                                   ("Delivery Charter", charter["digest"], envelope["delivery_charter_digest"]),
                                   ("handoff", handoff.get("digest"), envelope["handoff_digest"])):
        if found != expected:
            return "fail", 3, f"{label} digest {str(found)[:16]} differs from the envelope's {str(expected)[:16]}"
    if handoff.get("digest") != delivery_digest(handoff_payload):
        return "fail", 3, "handoff digest does not recompute"
    claims: dict[str, dict[str, Any]] = {}
    delivery_root = run_dir / "delivery"
    claim_paths = [path for authority_dir in _entries(delivery_root)
                   for path in _entries(authority_dir, "lead-claim*.json")]
    for path in claim_paths:
        claim = _json(_read(path, run_dir))
        if isinstance(claim, dict) and claim.get("digest") == delivery_digest({k: v for k, v in claim.items() if k != "digest"}):
            claims[claim["digest"]] = claim
    if envelope["delivery_lead_claim_digest"] not in claims:
        return "fail", 4, "no sealed lead claim file matches the envelope's lead claim digest"
    run = _json(_read(run_dir / "run.json", run_dir)) or {}
    current = (run.get("delivery") or {}).get("lead_claim_digest")
    walked, seen = current, set()
    while walked is not None and walked != envelope["delivery_lead_claim_digest"]:
        if walked not in claims or walked in seen:
            return "fail", 5, "the supersedes chain from the current claim does not reach the envelope's claim"
        seen.add(walked)
        walked = claims[walked].get("supersedes")
    if walked is None:
        return "fail", 5, "the supersedes chain from the current claim does not reach the envelope's claim"
    limits, headroom = project_envelope_limits(charter["limits"])
    if limits != envelope["limits"] or headroom != envelope.get("expansion_headroom", {}):
        return "fail", 6, "the charter's limit projection differs from the envelope limits or headroom"
    return "pass", 6, "authority files recompute and link; the claim chain is unbroken; limits project exactly"


def check_v8(ctx):
    envelope, attempt_dir, run_dir = ctx["envelope"], ctx["attempt_dir"], ctx["run_dir"]
    files = {"requirements": "requirements.snapshot.md", "acceptance": "acceptance.snapshot.md"}
    for name, filename in files.items():
        data = _read(attempt_dir / filename, run_dir)
        if data is None:
            raise Absent(f"{filename} is missing")
        if _sha(data) != envelope["charter_sources"][name]["sha256"]:
            return "fail", 1, f"{filename} sha256 differs from charter_sources.{name}"
    manifest = _read(attempt_dir / "manifest.snapshot.json", run_dir)
    if manifest is None or _sha(manifest) != envelope["manifest_digest"]:
        return "fail", 3, "manifest.snapshot.json differs from manifest_digest"
    recomputed = digest({"requirements": envelope["charter_sources"]["requirements"]["sha256"],
                         "acceptance": envelope["charter_sources"]["acceptance"]["sha256"]})
    if recomputed != envelope["charter_digest"]:
        return "fail", 4, "charter_digest does not recompute from charter_sources"
    return "pass", 4, "requirements, acceptance and manifest snapshots and charter_digest match"


def check_v9(ctx):
    links = ctx["snapshot"].get("magentic_checkpoints", [])
    if not links:
        raise Absent("no bound checkpoint")
    compared = 0
    for link in links:
        name = Path(link["path"]).name
        data = _read(ctx["attempt_dir"] / "checkpoints" / name, ctx["run_dir"])
        if data is None:
            quarantine = ctx["attempt_dir"] / "checkpoints-quarantine"
            for folder in _entries(quarantine):
                data = _read(folder / name, ctx["run_dir"])
                if data is not None:
                    break
        if data is None:
            return "fail", compared, f"checkpoint {link['checkpoint_id']} is missing from checkpoints/ and quarantine"
        if _sha(data) != link["file_sha256"] or len(data) != link["file_size"]:
            return "fail", compared, f"checkpoint {link['checkpoint_id']} sha256 or size differs from its link"
        value = _json(data)
        if not isinstance(value, dict) or value.get("checkpoint_id") != link["checkpoint_id"] \
                or value.get("workflow_name") != WORKFLOW_NAME:
            return "fail", compared, f"checkpoint {link['checkpoint_id']} identity or workflow differs"
        if link["pending_kind"] == "worker":
            action = ctx["actions"].get(link["pending_id"])
            key = f"flow-magentic-action-{action['request']['sequence']}" if action else None
            if not isinstance(value.get("pending_request_info_events"), dict) or set(value["pending_request_info_events"]) != {key}:
                return "fail", compared, f"checkpoint {link['checkpoint_id']} pending request differs from its proposal"
        if value.get("previous_checkpoint_id") != link.get("previous_checkpoint_id"):
            return "fail", compared, f"checkpoint {link['checkpoint_id']} parent differs from the recorded parent"
        compared += 1
    return "pass", compared, f"{compared} bound checkpoint(s) match their files (bound links only; no chain rule)"


def check_v10(ctx):
    directory = ctx["attempt_dir"] / REQUEST_DIR
    _entries(directory)  # refuses a directory past MAX_DIRECTORY_ENTRIES
    calls, leftovers, unexpected = list_request_files(ctx["attempt_dir"])
    if unexpected:
        return "fail", 0, f"unexpected file in {REQUEST_DIR}/: {unexpected[0]}"
    present: dict[str, bytes] = {}
    for call_id in calls:
        present[call_id] = _read(directory / f"{call_id}.json", ctx["run_dir"], limit=65536) or b""
        ctx["informational"].append({"check": "V10", "item": "file_mode", "call_id": call_id,
                                     "mode": oct(stat.S_IMODE((directory / f"{call_id}.json").lstat().st_mode))})
    if leftovers:
        ctx["informational"].append({"check": "V10", "item": "leftover_temporary_files", "names": leftovers})
    orphans = sorted(set(present) - set(ctx["calls"]))
    if orphans:
        return "fail", len(present), f"request file {orphans[0][:12]} has no manager call row"
    if not ctx["issued_calls"] and not present:
        raise Absent("no manager call was granted")
    compared = 0
    for call_id in ctx["issued_calls"]:
        call = ctx["calls"][call_id]
        data = present.get(call_id)
        history = ctx["grant_history"].get(call_id, [])
        consumed = any(op == "consume" for op, _ in history)
        if data is None:
            if history and history[-1][0] == "deny" and not consumed:
                continue  # re-checked and denied before it reached the send section; never sendable
            if consumed or ctx["status"] in {"completed", "failed"}:
                return "fail", compared, f"manager call {call_id[:12]} has no request file"
            continue
        stored = _json(data)
        if (not isinstance(stored, dict) or set(stored) != {"call_id", "messages", "prompt_digest"}
                or data != (canonical(stored) + "\n").encode()):
            return "fail", compared, f"request file {call_id[:12]} is not canonical"
        if stored["call_id"] != call_id or stored["prompt_digest"] != call["request"]["prompt_digest"] \
                or digest(stored["messages"]) != stored["prompt_digest"]:
            return "fail", compared, f"request file {call_id[:12]} does not bind to its call's prompt_digest"
        result = call.get("result") or {}
        if ctx["manager_provider"] == "claude" and call["status"] == "completed":
            try:
                rendered = hashlib.sha256(render_manager_prompt(stored["messages"]).encode()).hexdigest()
            except ContractError as exc:
                return "fail", compared, f"request file {call_id[:12]} messages do not render: {exc}"
            if rendered != result.get("input_sha256"):
                return "fail", compared, f"manager call {call_id[:12]} input_sha256 differs from its rendered request"
        compared += 1
    return "pass", compared, f"{compared} request file(s) are canonical and bind to their calls"


def check_v11(ctx):
    evidence = ctx["receipt"].get("evidence") or {}
    edit = evidence.get("edit")
    diff = _read(ctx["attempt_dir"] / "repair.diff", ctx["run_dir"])
    completed = ctx["status"] == "completed"
    if not edit and (diff is None or not completed):
        # A cancelled or abandoned receipt never binds its edit, even when a diff exists.
        raise Absent("no edit evidence")
    if diff is None or not isinstance(edit, dict):
        return "fail", 0, "repair.diff or evidence.edit is missing"
    sha = _sha(diff)
    inputs, evaluations = ctx["receipt"].get("verifier_inputs") or [], ctx["receipt"].get("verifier_evaluations") or []
    write_paths = set(ctx["job"]["write_paths"])
    headers = set(re.findall(r"^diff --git a/(\S+) b/", diff.decode(errors="replace"), re.M))
    in_scope = all(_within_declared_paths(path, write_paths)
                   for path in set(edit.get("changed_files", [])) | headers)
    if not inputs or not evaluations:
        if completed:
            return "fail", 1, "no verifier input or evaluation binds the edit"
        # Failed before the verifier ran: check what is present.
        if edit.get("diff_sha256") != sha:
            return "fail", 1, f"evidence.edit.diff_sha256: expected {sha[:16]} (repair.diff), found {str(edit.get('diff_sha256'))[:16]}"
        if not in_scope:
            return "fail", 2, "the diff changes files outside the job's write paths"
        return "pass", 2, "repair.diff binds the edit and stays in scope (no verifier ran)"
    final_input, final_evaluation = inputs[-1], evaluations[-1]["evaluation"]
    for label, value in (("evidence.edit.diff_sha256", edit.get("diff_sha256")),
                         ("final verifier input diff_digest", final_input.get("diff_digest")),
                         ("final evaluation diff_digest", final_evaluation.get("diff_digest"))):
        if value != sha:
            return "fail", 2, f"{label}: expected {sha[:16]} (repair.diff), found {str(value)[:16]}"
    tests = evidence.get("tests") or {}
    retained_output = tests.get("output_excerpt")
    actual_task = final_input["input"].get("provider_task")
    output_marker = "\nFlow-retained targeted-test output (bound by the receipt test digest):\n"
    authority_marker = "\nFlow-verified control-plane authority:\n"
    if (not isinstance(retained_output, str) and isinstance(actual_task, str)
            and output_marker in actual_task and authority_marker in actual_task):
        candidate = actual_task.split(output_marker, 1)[1].split(authority_marker, 1)[0]
        if hashlib.sha256(candidate.encode()).hexdigest() == tests.get("output_sha256"):
            retained_output = candidate
    task = verifier_provider_task(
        final_input["input"]["task"], diff.decode(errors="replace"), sha, structured=True,
        test_output=retained_output if isinstance(retained_output, str) else "",
        authority_statement=VERIFIED_HANDOFF_AUTHORITY if isinstance(retained_output, str) else "")
    acceptable_tasks = {task}
    if not isinstance(retained_output, str):
        # Receipts sealed while the retained-output contract was introduced can
        # carry the new fixed authority statement with legacy digest-only test
        # evidence. Older sealed receipts carry neither addition.
        acceptable_tasks.add(verifier_provider_task(
            final_input["input"]["task"], diff.decode(errors="replace"), sha, structured=True,
            authority_statement=VERIFIED_HANDOFF_AUTHORITY))
    if actual_task not in acceptable_tasks:
        return "fail", 3, "the final verifier input's provider_task differs from the one rebuilt from repair.diff"
    if not in_scope:
        return "fail", 4, "the diff changes files outside the job's write paths"
    return "pass", 4, "repair.diff binds the edit, the final verifier input and evaluation; scope holds"


def check_v12(ctx):
    evidence = ctx["receipt"].get("evidence") or {}
    tests = evidence.get("tests")
    if not isinstance(tests, dict):
        raise Absent("no test evidence")
    inputs, evaluations = ctx["receipt"].get("verifier_inputs") or [], ctx["receipt"].get("verifier_evaluations") or []
    if not inputs or not evaluations:
        if ctx["status"] == "completed":
            return "fail", 1, "no verifier input or evaluation binds the test evidence"
        if tests.get("command") != ctx["job"]["test"]["argv"]:
            return "fail", 1, "the test command differs from the job's test argv"
        return "pass", 1, "the test command is the job's (no verifier ran)"
    sha = tests.get("output_sha256")
    for label, value in (("final verifier input test_digest", inputs[-1].get("test_digest")),
                         ("final evaluation test_evidence_digest", evaluations[-1]["evaluation"].get("test_evidence_digest"))):
        if value != sha:
            return "fail", 2, f"{label}: expected {str(sha)[:16]}, found {str(value)[:16]}"
    if tests.get("command") != ctx["job"]["test"]["argv"]:
        return "fail", 3, "the test command differs from the job's test argv"
    return "pass", 3, "test digest binds the final verifier input and evaluation; the command is the job's"


def check_v13(ctx):
    data = _read(ctx["attempt_dir"] / "baseline.json", ctx["run_dir"])
    if data is None:
        raise Absent("baseline.json is missing")
    baseline = _json(data)
    if not isinstance(baseline, dict) or baseline != (ctx["receipt"].get("evidence") or {}).get("baseline"):
        return "fail", 1, "baseline.json differs from evidence.baseline"
    if baseline.get("regression_diff_sha256") != ctx["job"]["baseline"]["diff_sha256"]:
        return "fail", 2, "the baseline regression digest differs from the job's"
    return "pass", 2, "baseline.json equals evidence.baseline and the job baseline"


def check_v14(ctx):
    evidence = ctx["receipt"].get("evidence") or {}
    records = [evidence[key] for key in ("diagnostic_trace", "event_trace") if isinstance(evidence.get(key), dict)]
    if not records:
        raise Absent("no trace recorded")
    for record in records:
        name = record.get("path")
        if name not in {"claude-implementer.debug.log", "claude-implementer.events.ndjson"}:
            return "fail", 0, f"trace path {str(name)[:40]!r} is not a trace file name"
        data = _read(ctx["attempt_dir"] / name, ctx["run_dir"])
        if data is None or _sha(data) != record["sha256"] or len(data) != record["bytes"]:
            return "fail", 1, f"trace {record['path']} differs from its recorded sha256 and size"
    return "pass", len(records), f"{len(records)} trace file(s) match"


_TRANSITIONS = {  # op -> the states it may follow
    "issue": {None, "not_dispatched", "denied"}, "deny": {None, "allowed"},
    "rotate": {"allowed"}, "consume": {"allowed"}, "expire": {"allowed"}, "release": {"allowed"},
}
_AFTER = {"issue": "allowed", "rotate": "allowed", "consume": "sent", "expire": "denied", "release": "not_dispatched",
          "deny": "denied"}


def check_v15(ctx):
    events, compared = _events(ctx["snapshot"]), 0
    # (a) exactly one send start per sent row, and contiguous manager sequences.
    for row_id in list(ctx["calls"]) + list(ctx["actions"]):
        row = ctx["calls"].get(row_id) or ctx["actions"][row_id]
        if row["status"] not in SENT_STATUSES:
            continue
        starts = sum(1 for event in events if event["action_id"] == row_id and event["event"] == SEND_START[_row_kind(ctx, row_id)])
        if starts != 1:
            return "fail", compared, f"row {row_id[:12]} has {starts} {SEND_START[_row_kind(ctx, row_id)]} events (resent?)"
        compared += 1
    sequences = [call["sequence"] for call in ctx["snapshot"]["manager_calls"]]
    if sequences != list(range(1, len(sequences) + 1)):
        return "fail", compared, f"manager sequences are not contiguous from 1: {sequences[:8]}"
    # (b) every consumed expansion grant has its consumption event.
    for request in ctx["snapshot"].get("expansions") or []:
        grant = request.get("grant") or {}
        if grant.get("status") != "consumed":
            continue
        name = "expansion_granted" if grant.get("authority") == "charter_headroom" else "expansion_grant_consumed"
        key = request["request_id"] if name == "expansion_granted" else grant.get("grant_id")
        if not any(event["event"] == name and (_detail(event) if name == "expansion_grant_consumed" else
                                               (_detail(event) or {}).get("request_id")) == key for event in events):
            return "fail", compared, f"consumed expansion grant of {request['request_id']} has no {name} event"
        compared += 1
    # (c) the grant history folds through legal transitions to each row's final state.
    for row_id in list(ctx["calls"]) + list(ctx["actions"]):
        row = ctx["calls"].get(row_id) or ctx["actions"][row_id]
        history = ctx["grant_history"].get(row_id, [])
        if not history:
            return "fail", compared, f"row {row_id[:12]} has no grant_changed history"
        state, grant = None, None
        for op, grant_id in history:
            if op not in _TRANSITIONS or state not in _TRANSITIONS[op]:
                return "fail", compared, f"row {row_id[:12]}: illegal grant transition {op} after {state}"
            if op in {"rotate", "consume", "expire", "release"} and grant_id != grant:
                return "fail", compared, f"row {row_id[:12]}: {op} names grant {str(grant_id)[:8]}, not {str(grant)[:8]}"
            state = _AFTER[op]
            grant = grant_id if op in {"issue", "rotate", "consume", "expire"} else None
        final = row["status"]
        expected_state = ("sent" if final in SENT_STATUSES else final)
        if state != expected_state or row.get("grant_id") != grant:
            return "fail", compared, f"row {row_id[:12]}: history ends at {state}/{str(grant)[:8]}, row is {final}"
        compared += 1
    # (d) checkpoint binding precedes its bound event.
    for link in ctx["snapshot"].get("magentic_checkpoints", []):
        bound = [event["seq"] for event in events if event["event"] == "magentic_checkpoint_bound"
                 and event["action_id"] == link["pending_id"]]
        if not bound or not link["ledger_seq"] < bound[0]:
            return "fail", compared, f"checkpoint {link['checkpoint_id']} ledger_seq does not precede its bound event"
        compared += 1
    # (e) no send falls inside a pending escalation window (by seq).
    automatic = {request["request_id"] for request in ctx["snapshot"].get("expansions") or []
                 if (request.get("grant") or {}).get("authority") == "charter_headroom"}
    windows = []
    for event in events:
        detail = _detail(event)
        if event["event"] == "expansion_requested" and isinstance(detail, dict) and detail.get("request_id") not in automatic:
            close = next((later["seq"] for later in events if later["seq"] > event["seq"]
                          and later["event"] in {"expansion_decided", "expansion_cancelled"}
                          and (_detail(later) or {}).get("request_id") == detail.get("request_id")), None)
            if close is None:
                return "fail", compared, f"expansion {detail.get('request_id')} is still pending at the seal"
            windows.append((event["seq"], close))
    for start, end in windows:
        inside = [event for event in events if start < event["seq"] < end and (
            event["event"] in {"manager_send_started", "verifier_send_claimed"}
            or event["event"] == "worker_dispatched" and _paid(ctx, event["action_id"]))]
        if inside:
            return "fail", compared, f"{inside[0]['event']} at seq {inside[0]['seq']} falls inside a pending escalation"
        compared += 1
    return "pass", compared, "send starts, expansion consumption, grant history, checkpoint order and escalation windows hold"


def check_v16(ctx):
    records = process_identity.records(ctx["attempt_dir"])
    lines = [(record["owner_generation"], line) for record in records for line in record["groups"]]
    if not lines:
        raise Absent("no provider group recorded")
    rows = set(ctx["calls"]) | set(ctx["actions"])
    for _, line in lines:
        if line["kind"] == "provider" and line.get("row_id") not in rows:
            return "fail", 1, f"a provider group line names {str(line.get('row_id'))[:12]}, which is no receipt row"
        if line["kind"] != "provider" and line.get("row_id") is not None:
            return "fail", 1, f"a {line['kind']} group line names a row"
    compared = 1
    for row_id in sorted(rows):
        row = ctx["calls"].get(row_id) or ctx["actions"][row_id]
        if row["status"] not in SENT_STATUSES or not _paid(ctx, row_id):
            continue
        generation = next((detail.get("owner_generation") for event in _events(ctx["snapshot"])
                           if event["event"] == "grant_changed" and event["action_id"] == row_id
                           for detail in [_detail(event)] if isinstance(detail, dict) and detail.get("op") == "consume"), None)
        if not any(gen == generation and line.get("row_id") == row_id for gen, line in lines):
            return "fail", compared, f"sent row {row_id[:12]} has no provider group in control-g{generation}"
        compared += 1
    return "pass", compared, "group lines name receipt rows; every sent paid row has its group (consistency only)"


def check_v17(ctx):
    if not handback_supported(ctx["envelope"]):
        raise Absent("no token budget")
    envelope = ctx["envelope"]
    lineage = []
    for item in envelope.get("predecessors", []):
        entry = ctx["view_entries"].get(item["attempt_id"])
        if entry is None:
            continue
        prior = json.loads(entry["envelope_json"])
        if _same_delivery_authority(envelope, prior):
            lineage.append(entry)
    lineage.append(ctx["entry"])
    events: list[dict[str, Any]] = []
    rows: dict[str, tuple[str, str | None, Any]] = {}
    tranche_marks: list[int] = []
    for entry in lineage:
        snapshot = entry["snapshot"]
        prior = json.loads(entry["envelope_json"])
        manager = (prior.get("manager") or {}).get("provider")
        events += snapshot["events"]
        for item in snapshot["actions"]:
            rows[item["action_id"]] = (item["status"], item["request"].get("provider"), item.get("result"))
        for item in snapshot["manager_calls"]:
            rows[item["call_id"]] = (item["status"], manager, item.get("result"))
        tokens = {request["request_id"]: request for request in snapshot.get("expansions", [])
                  if "tokens" in (request.get("limits") or [])}
        for event in snapshot["events"]:
            detail = _detail(event)
            if event["event"] == "expansion_granted" and isinstance(detail, dict) and detail.get("request_id") in tokens:
                tranche_marks.append(event["seq"])
            if event["event"] == "expansion_grant_consumed" and any(
                    (request.get("grant") or {}).get("grant_id") == detail for request in tokens.values()):
                tranche_marks.append(event["seq"])
    events.sort(key=lambda event: event["seq"])
    first_send: dict[str, int] = {}
    for event in events:
        if event["event"] in {"manager_send_started", "worker_dispatched", "verifier_send_claimed"}:
            first_send.setdefault(event["action_id"], event["seq"])
    unobserved = envelope["limits"]["unobserved_send_tokens"]
    compared = 0
    for event in events:
        detail = _detail(event)
        if event["event"] != "grant_changed" or not isinstance(detail, dict) or detail.get("op") not in {"issue", "rotate"}:
            continue
        status, provider, _ = rows.get(event["action_id"], (None, None, None))
        if provider not in PAID_PROVIDERS:
            continue
        charged = sum(charge(row_status, row_provider, result, unobserved)["charged"]
                      for row_id, (row_status, row_provider, result) in rows.items()
                      if first_send.get(row_id, 1 << 62) < event["seq"])
        tranches = sum(1 for seq in tranche_marks if seq < event["seq"])
        if not charged < token_maximum(envelope, tranches):
            return "fail", compared, (f"paid grant at seq {event['seq']} issued with {charged} charged against a cap of "
                                      f"{token_maximum(envelope, tranches)}")
        compared += 1
    if not compared and not any(provider in PAID_PROVIDERS and status in SENT_STATUSES
                                for status, provider, _ in rows.values()):
        return "pass", 1, "no paid grant was issued and no paid call was sent"
    for row_id, (status, provider, _) in rows.items():
        if provider in PAID_PROVIDERS and status in SENT_STATUSES:
            issued = [event["seq"] for event in events if event["action_id"] == row_id and event["event"] == "grant_changed"
                      and (_detail(event) or {}).get("op") in {"issue", "rotate"}]
            if not issued or min(issued) > first_send.get(row_id, 1 << 62):
                return "fail", compared, f"sent paid row {row_id[:12]} has no grant issued before its send"
    return "pass", compared, f"{compared} paid grant(s) were issued under the token cap"


CHECKS = [("V1", check_v1), ("V2", check_v2), ("V3", check_v3), ("V4", check_v4), ("V5", check_v5),
          ("V6", check_v6), ("V7", check_v7), ("V8", check_v8), ("V9", check_v9), ("V10", check_v10),
          ("V11", check_v11), ("V12", check_v12), ("V13", check_v13), ("V14", check_v14), ("V15", check_v15),
          ("V16", check_v16), ("V17", check_v17)]


def _requiredness(check: str, ctx: dict[str, Any]) -> str:
    rule = REQUIREDNESS.get(check, {}).get(ctx["status"], "R")
    return rule(ctx) if callable(rule) else rule


def _verify_entry(base: dict[str, Any], entry: dict[str, Any], *, recurse: bool) -> dict[str, Any]:
    run_dir = base["run_dir"]
    attempt_id = entry["attempt_id"]
    attempt_dir = run_dir / "execution" / attempt_id
    envelope = json.loads(entry["envelope_json"])
    unsafe = None
    try:
        receipt_bytes = _read(attempt_dir / "receipt.json", run_dir)
    except ContractError as exc:
        receipt_bytes, unsafe = None, str(exc)
    try:
        receipt = json.loads(receipt_bytes) if receipt_bytes is not None else {}
    except (ValueError, RecursionError):
        receipt = {}
    snapshot = entry["snapshot"]
    ctx = {"base": base, "run_dir": run_dir, "attempt_id": attempt_id, "attempt_dir": attempt_dir, "entry": entry,
           "envelope": envelope, "receipt_bytes": receipt_bytes, "receipt": receipt if isinstance(receipt, dict) else {},
           "snapshot": snapshot, "blocks": entry.get("blocks") or {}, "status": entry["status"],
           "job": envelope["job_contract"], "manager_provider": (envelope.get("manager") or {}).get("provider"),
           "calls": {item["call_id"]: item for item in snapshot["manager_calls"]},
           "actions": {item["action_id"]: item for item in snapshot["actions"]},
           "grant_history": _grant_history(snapshot), "view_entries": base["entries"],
           "work_lineage": base["work_lineage"], "recurse": recurse, "informational": [], "receipt_unsafe": unsafe}
    ctx["issued_calls"] = [call_id for call_id in ctx["calls"]
                           if any(op in {"issue", "rotate"} for op, _ in ctx["grant_history"].get(call_id, []))]
    checks = []
    for check, function in CHECKS:
        try:
            required = _requiredness(check, ctx)
        except Exception:  # requiredness is read from the ledger; a malformed row still decides "required"
            required = "R"
        try:
            status, compared, detail = function(ctx)
        except Absent as missing:
            status, compared, detail = (("fail", 0, f"required input missing: {missing}") if required == "R" else
                                        ("not_applicable", 0, NA_REASONS.get(check, str(missing))))
        except ContractError as exc:
            status, compared, detail = "fail", 0, str(exc)
        except Exception as exc:  # a malformed source fails its check; it never crashes the report
            status, compared, detail = "fail", 0, f"{type(exc).__name__}: {str(exc)[:160]}"
        if status == "pass" and compared < 1:
            status, detail = "fail", f"nothing was compared: {detail}"
        checks.append({"check": check, "name": NAMES[check], "status": status, "compared": compared, "detail": detail})
    return {"attempt_id": attempt_id, "status": entry["status"], "checks": checks,
            "informational": ctx["informational"]}


def verify_receipt(work_id: str, attempt_id: str | None = None, *, root: Path | None = None,
                   lineage: bool = True) -> dict[str, Any]:
    """Verify ``attempt_id`` (default: the latest sealed attempt) of ``work_id``; see the module docstring."""
    project_root = (root or repo_root()).resolve()
    if not isinstance(work_id, str) or not _ID.fullmatch(work_id) or (attempt_id is not None and not _ID.fullmatch(attempt_id)):
        raise VerifyRefused("run_unreadable", "work or attempt id is invalid")
    run_dir = project_root / ".flow" / "runs" / work_id
    ledger_path = run_dir / "execution" / "ledger.sqlite"
    if run_dir.is_symlink() or not run_dir.is_dir() or ledger_path.is_symlink() or not ledger_path.is_file():
        raise VerifyRefused("run_unreadable", f"no delivery ledger for {work_id}")
    try:
        view = ExecutionLedger(ledger_path, read_only=True).lineage_view(work_id, attempt_id, sealed_only=True)
    except ContractError as exc:
        raise VerifyRefused("attempt_not_sealed", str(exc)) from exc
    except Exception as exc:  # sqlite3.Error: the ledger cannot be read
        raise VerifyRefused("run_unreadable", f"ledger unreadable: {exc}") from exc
    entries = {entry["attempt_id"]: entry for entry in view["attempts"]}
    target = entries[view["attempt_id"]]
    if target["execution_protocol_version"] == 9:
        if target["sealed_receipt_sha256"] is None or target["status"] not in TERMINAL:
            raise VerifyRefused("attempt_not_sealed", f"{view['attempt_id']} is {target['status']}")
        attempt_dir = run_dir / "execution" / view["attempt_id"]
        receipt_path = attempt_dir / "receipt.json"
        stored_path = target["snapshot"].get("receipt_path")
        try:
            stored_is_canonical = (isinstance(stored_path, str)
                                   and Path(stored_path).resolve() == receipt_path.resolve()
                                   and Path(stored_path).resolve().is_relative_to(attempt_dir.resolve()))
        except OSError:
            stored_is_canonical = False
        if not stored_is_canonical:
            checks = [{"check": "S1", "name": "selection receipt closure", "status": "fail", "compared": 1,
                       "detail": "the ledger receipt_path does not name the canonical v9 receipt"}]
            return _report(work_id, view["attempt_id"], target["status"], checks, [])
        receipt_bytes = _read(receipt_path, run_dir)
        if receipt_bytes is None:
            checks = [{"check": "S1", "name": "selection receipt closure", "status": "fail", "compared": 1,
                       "detail": "the canonical v9 receipt is missing"}]
            return _report(work_id, view["attempt_id"], target["status"], checks, [])
        if _sha(receipt_bytes) != target["sealed_receipt_sha256"]:
            checks = [{"check": "S1", "name": "selection receipt closure", "status": "fail", "compared": 1,
                       "detail": "the canonical v9 receipt digest differs from the ledger seal"}]
            return _report(work_id, view["attempt_id"], target["status"], checks, [])
        try:
            receipt = json.loads(receipt_bytes)
            result = verify_v9_selection_receipt_snapshot(receipt, target["snapshot"])
        except (ValueError, ContractError) as exc:
            checks = [{"check": "S1", "name": "selection receipt closure", "status": "fail", "compared": 1,
                       "detail": str(exc)}]
            return _report(work_id, view["attempt_id"], target["status"], checks, [])
        checks = [{"check": "S1", "name": "selection receipt closure", "status": "pass",
                   "compared": result["compared"] + 3,
                   "detail": "selection receipt recomputes and exactly matches the sealed ledger snapshot"}]
        return _report(work_id, view["attempt_id"], target["status"], checks, [])
    if target["execution_protocol_version"] != 8:
        raise VerifyRefused("unsupported_receipt", "only protocol v8 receipts are verified")
    if target["status"] == "denied":
        raise VerifyRefused("unsupported_receipt", "a v8 attempt never seals denied")
    if target["sealed_receipt_sha256"] is None or target["status"] not in TERMINAL:
        raise VerifyRefused("attempt_not_sealed", f"{view['attempt_id']} is {target['status']}")
    envelope = json.loads(target["envelope_json"])
    base = {"run_dir": run_dir, "entries": entries, "work_lineage": view["work_lineage"]}
    if not handback_supported(envelope):
        try:
            on_disk = _json(_read(run_dir / "execution" / view["attempt_id"] / "envelope.json", run_dir))
        except ContractError:
            on_disk = None
        if handback_supported(on_disk):
            # A supported file over a pre-release ledger envelope is tampering, not an old receipt.
            checks = [{"check": "V2", "name": NAMES["V2"], "status": "fail", "compared": 1,
                       "detail": "envelope.json seals a token budget but the ledger envelope does not"}]
            return _report(work_id, view["attempt_id"], target["status"], checks, [])
        raise VerifyRefused("unsupported_receipt", "the attempt predates the sealed token budget (ADR 0020)")
    result = _verify_entry(base, target, recurse=lineage)
    return _report(work_id, view["attempt_id"], target["status"], result["checks"], result["informational"])


def _report(work_id: str, attempt_id: str, status: str, checks: list[dict[str, Any]],
            informational: list[dict[str, Any]]) -> dict[str, Any]:
    failed = any(item["status"] == "fail" for item in checks)
    return {"schema_version": SCHEMA_VERSION, "work_id": work_id, "attempt_id": attempt_id, "status": status,
            "exit_code": 1 if failed else 0, "checks": checks,
            "unverifiable": [{"item": item, "status": "unverifiable_offline", "detail": text} for item, text in UNVERIFIABLE],
            "informational": informational}


def render_text(report: dict[str, Any]) -> str:
    lines = [f"verify-receipt {report['work_id']} {report['attempt_id']} ({report['status']}): "
             + ("FAIL" if report["exit_code"] else "PASS")]
    for item in report["checks"]:
        lines.append(f"  {item['check']:<4} {item['status']:<15} {item['name']} [{item['compared']}] {item['detail']}")
    for item in report["unverifiable"]:
        lines.append(f"  --   unverifiable_offline {item['detail']}")
    return "\n".join(lines)
