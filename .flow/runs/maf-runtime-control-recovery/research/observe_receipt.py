"""Flow-side observer for the local live recovery proof."""

from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from agent_framework import FileCheckpointStorage

from flow_gate import FlowGate
from live_recovery import CHARTER, DEFINITION, FIXTURE


LIVE = Path("/private/tmp/flow-maf-control-live-20260919")
DENIED = Path("/private/tmp/flow-maf-control-denied-v2-20260919")


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(FIXTURE), *args], text=True).strip()


async def checkpoint_present(checkpoint_id: str, request_id: str) -> bool:
    storage = FileCheckpointStorage(LIVE / "checkpoints")
    checkpoints = await storage.list_checkpoints(workflow_name="flow-live-recovery")
    return any(cp.checkpoint_id == checkpoint_id and request_id in cp.pending_request_info_events for cp in checkpoints)


def main() -> None:
    handoff = json.loads((LIVE / "handoff.json").read_text())
    live = FlowGate(LIVE / "flow-policy.sqlite").snapshot()
    denied = FlowGate(DENIED / "flow-policy.sqlite").snapshot()
    definition_digest = hashlib.sha256(DEFINITION.read_bytes()).hexdigest()
    charter_digest = hashlib.sha256(CHARTER.encode()).hexdigest()
    assert handoff["definition_sha256"] == definition_digest
    assert handoff["charter_sha256"] == charter_digest
    assert len(live["dispatches"]) == 1
    dispatch_id, reported_digest, state = live["dispatches"][0]
    assert (dispatch_id, state) == (handoff["work_request_id"], "completed")
    assert sum(event[2] == "worker_dispatched" for event in live["events"]) == 1
    assert any(event[2] == "policy_allowed" and event[1] == dispatch_id for event in live["events"])
    assert any(event[2] == "policy_denied" and event[3] == "duplicate_request" for event in live["events"])
    assert len(denied["dispatches"]) == 0
    assert any(event[2] == "policy_denied" and event[3] == "specialist_denied" for event in denied["events"])
    assert asyncio.run(checkpoint_present(handoff["checkpoint_id"], handoff["final_request_id"]))
    head = git("rev-parse", "HEAD")
    changed_paths = git("status", "--porcelain")
    assert head == "f23b769cd00636f11cb06d1c7e52e8b2add9e795"
    assert not changed_paths
    print(json.dumps({
        "schema_version": 1,
        "source": "Flow-side Git, definition, policy-ledger, and MAF-checkpoint readback",
        "flow_policy_allowed_count": sum(event[2] == "policy_allowed" for event in live["events"]),
        "flow_policy_denial_count": sum(event[2] == "policy_denied" for event in live["events"]) + sum(event[2] == "policy_denied" for event in denied["events"]),
        "denied_scenario_flow_recorded_dispatch_count": len(denied["dispatches"]),
        "live_flow_recorded_dispatch_count": len(live["dispatches"]),
        "live_provider": "ollama:llama3.1:8b",
        "paid_flow_recorded_dispatch_count": 0,
        "physical_provider_call_count_independently_observed": False,
        "checkpoint_id": handoff["checkpoint_id"],
        "checkpoint_readback": True,
        "definition_sha256": definition_digest,
        "charter_sha256": charter_digest,
        "reported_result_sha256": reported_digest,
        "reported_result_independently_attested": False,
        "git_head": head,
        "changed_paths": [],
        "worker_commit_created": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
