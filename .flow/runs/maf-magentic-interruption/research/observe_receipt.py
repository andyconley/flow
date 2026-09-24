"""Observe Flow ledger, Magentic checkpoint, stream marker, and Git fixture."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from agent_framework import FileCheckpointStorage

from flow_gate import FlowGate
from magentic_guard_probe import CHARTER, DEFINITION, FIXTURE


async def has_checkpoint(root: Path, checkpoint_id: str, request_id: str) -> bool:
    storage = FileCheckpointStorage(root / "checkpoints")
    checkpoints = await storage.list_checkpoints(workflow_name="flow-guarded-magentic")
    return any(cp.checkpoint_id == checkpoint_id and request_id in cp.pending_request_info_events for cp in checkpoints)


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(FIXTURE), *args], text=True).strip()


def main() -> None:
    denied_root = Path(sys.argv[1])
    interrupted_root = Path(sys.argv[2])
    denied = FlowGate(denied_root / "flow-policy.sqlite").snapshot()
    interrupted = FlowGate(interrupted_root / "flow-policy.sqlite").snapshot()
    denied_handoff = json.loads((denied_root / "handoff.json").read_text())
    handoff = json.loads((interrupted_root / "handoff.json").read_text())
    marker = json.loads((interrupted_root / "stream-observed.json").read_text())
    recovery = json.loads((Path(__file__).parent / "recovery-result.json").read_text())
    assert asyncio.run(has_checkpoint(denied_root, denied_handoff["checkpoint_id"], denied_handoff["plan_request_id"]))
    assert asyncio.run(has_checkpoint(interrupted_root, handoff["checkpoint_id"], handoff["plan_request_id"]))
    definition_digest = hashlib.sha256(DEFINITION.read_bytes()).hexdigest()
    charter_digest = hashlib.sha256(CHARTER.encode()).hexdigest()
    assert handoff["definition_sha256"] == definition_digest
    assert handoff["charter_sha256"] == charter_digest
    assert len(denied["dispatches"]) == 0
    assert any(row[5] == "denied" and row[6] == "specialist_denied" for row in denied["requests"])
    assert any(event[2] == "policy_denied" and event[3] == "specialist_denied" for event in denied["events"])
    assert len(interrupted["dispatches"]) == 1
    request_id, result_digest, dispatch_state = interrupted["dispatches"][0]
    assert request_id == marker["request_id"]
    assert dispatch_state == "unknown" and result_digest is None
    assert marker["first_stream_chunk_chars"] > 0
    assert sum(event[2] == "worker_dispatched" for event in interrupted["events"]) == 1
    assert sum(event[2] == "worker_unknown" for event in interrupted["events"]) == 1
    assert sum(event[2] == "manual_reconciliation_required" for event in interrupted["events"]) == 1
    assert recovery["terminal_reconciliation_required"] and recovery["provider_dispatch_count"] == 1
    assert recovery["request_statuses"] == ["unknown"]
    assert recovery["run_id"] == handoff["run_id"]
    assert recovery["checkpoint_id"] == handoff["checkpoint_id"]
    assert recovery["work_request_id"] == request_id
    head = git("rev-parse", "HEAD")
    changed = git("status", "--porcelain")
    assert head == "f23b769cd00636f11cb06d1c7e52e8b2add9e795"
    assert not changed
    print(json.dumps({
        "schema_version": 1,
        "source": "Flow-side policy ledger, MAF checkpoint, stream marker, and Git readback",
        "denied_magentic_role": "security-reviewer",
        "denied_flow_recorded_dispatches": 0,
        "interrupted_role": "test-engineer",
        "interrupted_flow_recorded_dispatches": 1,
        "dispatch_state": dispatch_state,
        "recovery_requires_manual_reconciliation": True,
        "checkpoint_readback": True,
        "first_stream_chunk_observed_by_wrapper": True,
        "first_stream_chunk_sha256": marker["first_stream_chunk_sha256"],
        "physical_ollama_request_count_independently_observed": False,
        "paid_flow_recorded_dispatches": 0,
        "definition_sha256": definition_digest,
        "charter_sha256": charter_digest,
        "git_head": head,
        "changed_paths": [],
        "model_output_semantics_attested": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
