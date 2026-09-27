"""A real v8 delivery parent for cancel tests, run as its own process (ADR 0019).

Usage: delivery_cancel_harness.py SCENARIO ROOT WORKTREE COMMIT FIFO

The parent prepares and runs through ``execute_chartered_delivery`` with stub
adapters that start real process groups, announces on FIFO when it is blocked,
and prints its result as JSON. Scenarios:

- ``worker``: a provider call blocked in flight (a real sleeper group)
- ``manager``: a manager call blocked in flight
- ``child``: the real MAF launcher blocked on its child (``FLOW_MAF_PYTHON``)
- ``claude``: the real Claude edit worker, with a fake ``claude`` on PATH
- ``outcome``: completes, pausing after the runtime outcome is recorded
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import traceback
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO))

import delivery_cancel  # noqa: E402
import process_identity  # noqa: E402
from delivery_gateway import execute_chartered_delivery  # noqa: E402
from execution_contracts import digest, envelope_digest, expected_manager_call_id  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture  # noqa: E402

PASS = CharteredFixture.PASS


def test_runtime_identity() -> dict:
    """Provide a sealed test-only identity for subprocess cancellation seams.

    These scenarios exercise parent cancellation and receipt handling, not
    managed-runtime provisioning.  The normal gateway's readiness fence is
    covered separately; this local patch keeps the child harness hermetic.
    """
    interpreter = os.environ.get("FLOW_MAF_PYTHON") or sys.executable
    return {"schema_version": 1, "interpreter": interpreter, "python": [3, 12, 0],
            "packages": {"agent-framework-core": "1.19.0", "agent-framework-orchestrations": "1.2.0"},
            "lock_digest": "a" * 64, "protocols": [5, 6, 7, 8], "runtime_digest": "b" * 64}


def announce(fifo: str, line: str) -> None:
    fd = os.open(fifo, os.O_WRONLY)
    try:
        os.write(fd, (line + "\n").encode())
    finally:
        os.close(fd)


def blocked_group(fifo: str, sends: list[str], label: str) -> None:
    """Start a real session like a provider call, record it, then wait until cancelled."""
    sends.append(label)
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], start_new_session=True)
    try:
        process_identity.register_group(sleeper.pid, "provider")
        announce(fifo, f"blocked {sleeper.pid}")
        with delivery_cancel.interruptible():
            sleeper.wait()
        raise RuntimeError("the blocked call returned without a cancel")
    finally:
        if sleeper.poll() is None:
            os.killpg(sleeper.pid, signal.SIGKILL)
            sleeper.wait()


def checkpoint(envelope: dict, proposal: dict, sequence: int) -> None:
    (Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json").write_text(json.dumps(
        {"checkpoint_id": proposal["checkpoint_id"], "workflow_name": "flow-magentic-delivery-v8",
         "pending_request_info_events": {f"flow-magentic-action-{sequence}": {}}}))


def main() -> int:
    scenario, root, worktree, commit, fifo = sys.argv[1:6]
    root_path = Path(root)
    state = json.loads((root_path / ".flow" / "runs" / "sample" / "run.json").read_text())
    sends: list[str] = []
    kwargs: dict = {}

    def plan_supervisor(plan):
        def supervisor(envelope, task, on_manager, on_action, **_):
            for sequence, assignment_id in enumerate(plan, 1):
                proposal = CharteredFixture._proposal(None, envelope, assignment_id, sequence)
                checkpoint(envelope, proposal, sequence)
                on_action(proposal)
            return {"attempt_id": envelope["attempt_id"]}
        return supervisor

    def quick_worker(action, *, envelope, workspace):
        sends.append(action["assignment_id"])
        if action["assignment_id"] == "editor":
            (workspace / "target.py").write_text("new\n")
            return CharteredFixture._result("codex", "editor-model", "Edited target")
        return CharteredFixture._result("ollama", "local-model", PASS)

    if scenario == "worker":
        kwargs["supervisor"] = plan_supervisor(("editor",))
        kwargs["worker_adapter"] = lambda action, **_: blocked_group(fifo, sends, action["assignment_id"])
    elif scenario == "manager":
        messages = [{"role": "user", "contents": [{"type": "text", "text": "progress 1"}]}]

        def supervisor(envelope, task, on_manager, on_action, **_):
            request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                       "envelope_digest": envelope_digest(envelope), "sequence": 1, "phase": "facts",
                       "manager_round": 1, "prompt_digest": digest(messages)}
            on_manager({**request, "call_id": expected_manager_call_id(request), "messages": messages})
            return {"attempt_id": envelope["attempt_id"]}

        kwargs["supervisor"] = supervisor
        kwargs["manager_adapter"] = lambda message, **_: blocked_group(fifo, sends, "manager")
    elif scenario == "child":
        pass  # the real run_maf_delivery launches FLOW_MAF_PYTHON, which announces and blocks
    elif scenario == "claude":
        kwargs["supervisor"] = plan_supervisor(("editor",))  # the default worker adapter runs the real CLI
    elif scenario == "outcome":
        kwargs["supervisor"] = plan_supervisor(("editor", "verifier"))
        kwargs["worker_adapter"] = quick_worker

        def hook(point):
            if point != "after-runtime-outcome":
                return
            announce(fifo, "outcome")
            controller = delivery_cancel.current()
            deadline = time.monotonic() + 30
            # A wait after the outcome: disarm means a cancel here must not raise.
            with delivery_cancel.interruptible():
                while not controller.requested and time.monotonic() < deadline:
                    time.sleep(0.01)
        kwargs["seal_hook"] = hook
    else:
        raise SystemExit(f"unknown scenario {scenario}")
    def fake_test(worktree, job, **_):
        return {"command": job["test"]["argv"], "status": "passed", "output_sha256": "0" * 64}
    try:
        with patch("delivery_gateway.run_status", return_value=state), \
             patch("delivery_gateway.require_ready", return_value=test_runtime_identity()), \
             patch("delivery_gateway.validate_orchestration", return_value=(True, None, [])), \
             patch("delivery_gateway._effective_specialist_for", side_effect=lambda role: "instructions for " + role), \
             patch("delivery_gateway._run_chartered_test", side_effect=fake_test):
            result = execute_chartered_delivery("sample", Path(worktree), commit, root=root_path, **kwargs)
    except BaseException as exc:  # reported to the test instead of a bare traceback
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-2000:],
                          "sends": sends}))
        return 1
    print(json.dumps({"result": result, "sends": sends}, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
