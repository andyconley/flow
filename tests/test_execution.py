"""Behavior tests for Flow's first supervised local execution slice.

Every gateway test supplies a local-stub adapter and a deterministic
supervisor.  These tests never start MAF or contact Ollama.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))

import execution_gateway as gateway  # noqa: E402
from execution_contracts import (  # noqa: E402
    ContractError,
    envelope_digest,
    expected_action_id,
    validate_action,
    validate_receipt,
    validate_result,
)
from execution_ledger import ExecutionLedger  # noqa: E402
import local_worker  # noqa: E402
from local_worker import call_local  # noqa: E402


WORK_ID = "execution-fixture"
ASSIGNMENT_ID = "test-producer"


def action_for(envelope: dict) -> dict:
    """Return the sole action the first-slice contract permits."""
    return {
        "schema_version": 1,
        "action_id": expected_action_id(envelope, 1),
        "attempt_id": envelope["attempt_id"],
        "envelope_digest": envelope_digest(envelope),
        "role": envelope["role"],
        "instance_id": envelope["instance_id"],
        "provider": envelope["provider"],
        "model": envelope["model"],
        "task_digest": envelope["task_digest"],
        "sequence": 1,
        "kind": "delegate",
    }


def stub_result(envelope: dict, output: str = "deterministic local result") -> dict:
    return {
        "schema_version": 1,
        "status": "completed",
        "provider": "local-stub",
        "model": envelope["model"],
        "physical_call": False,
        "evidence_level": "local_stub",
        "output": output,
        "output_sha256": hashlib.sha256(output.encode()).hexdigest(),
        "usage": None,
    }


class ExecutionFixture(unittest.TestCase):
    """A valid implementing C-Lite run with a test-engineer assignment."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / ".git").mkdir()
        self.run_dir = self._make_run(WORK_ID)

    def _make_run(self, work_id: str) -> Path:
        source_run = REPO / ".flow" / "runs" / "maf-supervised-local-worker"
        run = json.loads((source_run / "run.json").read_text())
        # The source run is archived; this disposable fixture represents the
        # earlier implementation state required by the dispatch gateway.
        run["state"] = "implementing"
        run["phase"] = "implementing"
        run["lane"] = "implement"
        run["last_event"] = "start-implementation"
        for key in ("archive", "handback", "implementation_evidence", "review"):
            run["artifacts"].pop(key, None)
        manifest = json.loads((source_run / "orchestration.json").read_text())
        self._replace_work_id(run, work_id)
        self._replace_work_id(manifest, work_id)
        manifest["work_id"] = work_id
        test_assignment = next(item for item in manifest["assignments"] if item["id"] == ASSIGNMENT_ID)
        test_assignment["execution"] = {"provider": "ollama", "model": "fixture-model"}
        # The gateway needs only the selected assignment. Keeping one writer
        # avoids manufacturing a false overlap in this disposable fixture.
        manifest["mode"] = "single"
        manifest["assignments"] = [test_assignment]
        test_assignment["write_scopes"] = [f".flow/runs/{work_id}"]
        manifest["verification"]["producer_assignments"] = [ASSIGNMENT_ID]
        manifest["verification"]["evidence_collector_assignment"] = ASSIGNMENT_ID
        manifest["verification"]["verifier_assignment"] = ASSIGNMENT_ID
        manifest["verification"]["independent"] = False
        run_dir = self.root / ".flow" / "runs" / work_id
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(json.dumps(run))
        (run_dir / "orchestration.json").write_text(json.dumps(manifest))
        (run_dir / "task.md").write_text("Return a short test report.\n")
        self._write_manifest_artifacts(manifest)
        self._write_state_artifacts(run)
        return run_dir

    def _replace_work_id(self, value, work_id: str):
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str):
                    value[key] = item.replace("maf-supervised-local-worker", work_id)
                else:
                    self._replace_work_id(item, work_id)
        elif isinstance(value, list):
            for item in value:
                self._replace_work_id(item, work_id)

    def _write_relative(self, raw: str) -> None:
        path = self.root / raw
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("fixture evidence\n")

    def _write_manifest_artifacts(self, manifest: dict) -> None:
        for assignment in manifest["assignments"]:
            self._write_relative(assignment["brief_path"])
            for raw in assignment["input_evidence"]:
                self._write_relative(raw)
            self._write_relative(assignment["output"]["path"])
        self._write_relative(manifest["reconciliation"]["artifact_path"])
        self._write_relative(manifest["verification"]["artifact_path"])

    def _write_state_artifacts(self, state: dict) -> None:
        for raw in state["artifacts"].values():
            self._write_relative(raw)

    def prepare(self, work_id: str = WORK_ID):
        return gateway.prepare(work_id, ASSIGNMENT_ID, f".flow/runs/{work_id}/task.md", root=self.root, test_provider="local-stub")

    def run_gateway(self, supervisor, adapter=stub_result):
        return gateway.execute_local(
            WORK_ID, ASSIGNMENT_ID, f".flow/runs/{WORK_ID}/task.md", root=self.root,
            supervisor=supervisor, adapter=adapter,
        )


class ExecutionContractTests(ExecutionFixture):
    def test_action_rejects_tampered_identity_before_ledger_or_adapter(self) -> None:
        envelope, _, _ = self.prepare()
        action = action_for(envelope)
        action["model"] = "other-model"
        with self.assertRaisesRegex(ContractError, "model differs"):
            validate_action(envelope, action)

    def test_ledger_grant_is_single_use_and_duplicate_action_is_denied(self) -> None:
        envelope, _, ledger = self.prepare()
        action = action_for(envelope)
        decision = ledger.decide(envelope, action)
        self.assertTrue(decision["allowed"])
        self.assertTrue(ledger.consume_grant(action["action_id"], decision["grant_id"]))
        self.assertFalse(ledger.consume_grant(action["action_id"], decision["grant_id"]))
        duplicate = ledger.decide(envelope, action)
        self.assertEqual(duplicate["reason"], "duplicate_request")
        snapshot = ledger.snapshot(envelope["attempt_id"])
        self.assertEqual(snapshot["actions"][0]["status"], "started")

    def test_expired_grant_is_denied_without_a_worker_dispatch(self) -> None:
        envelope, _, ledger = self.prepare()
        action = action_for(envelope)
        with patch("execution_ledger.utc_now", return_value="2000-01-01T00:00:00+00:00"):
            decision = ledger.decide(envelope, action)
        self.assertTrue(decision["allowed"])
        self.assertFalse(ledger.consume_grant(action["action_id"], decision["grant_id"]))
        stored = ledger.snapshot(envelope["attempt_id"])["actions"][0]
        self.assertEqual(stored["status"], "denied")
        self.assertEqual(stored["reason"], "grant_expired")

    def test_run_limits_do_not_reset_when_a_new_attempt_starts(self) -> None:
        """Terminal actions from earlier attempts constrain the same Flow run."""
        unknown_attempts = []
        for _ in range(3):
            envelope, _, ledger = self.prepare()
            decision = ledger.decide(envelope, action_for(envelope))
            self.assertTrue(decision["allowed"])
            self.assertTrue(ledger.consume_grant(decision["action_id"], decision["grant_id"]))
            ledger.mark_unknown(decision["action_id"], "simulated interrupted worker")
            unknown_attempts.append(envelope["attempt_id"])

        blocked_envelope, _, blocked_ledger = self.prepare()
        concurrency = blocked_ledger.decide(blocked_envelope, action_for(blocked_envelope))
        self.assertFalse(concurrency["allowed"])
        self.assertEqual(concurrency["reason"], "concurrency_cap")

        delegation_work_id = "execution-delegation-fixture"
        self._make_run(delegation_work_id)
        completed_attempts = []
        for _ in range(6):
            envelope, _, ledger = self.prepare(delegation_work_id)
            decision = ledger.decide(envelope, action_for(envelope))
            self.assertTrue(decision["allowed"])
            self.assertTrue(ledger.consume_grant(decision["action_id"], decision["grant_id"]))
            ledger.complete(decision["action_id"], stub_result(envelope))
            completed_attempts.append(envelope["attempt_id"])

        final_envelope, _, final_ledger = self.prepare(delegation_work_id)
        delegation = final_ledger.decide(final_envelope, action_for(final_envelope))
        self.assertFalse(delegation["allowed"])
        self.assertEqual(delegation["reason"], "delegation_cap")
        self.assertEqual(len(set(unknown_attempts)), 3)
        self.assertEqual(len(set(completed_attempts)), 6)

    def test_local_stub_requires_explicit_test_transport(self) -> None:
        envelope, _, _ = self.prepare()
        with self.assertRaisesRegex(ContractError, "explicit test transport"):
            call_local(envelope)
        result = call_local(envelope, transport=lambda _: "stub proof")
        self.assertEqual(result["provider"], "local-stub")
        self.assertFalse(result["physical_call"])

    def test_result_rejects_tampered_model_output_digest_and_evidence(self) -> None:
        envelope, _, _ = self.prepare()
        for field, value, message in (
            ("model", "other-model", "model differs"),
            ("output_sha256", "0" * 64, "output digest mismatch"),
            ("evidence_level", "flow_observed_local_http_response", "evidence level"),
        ):
            with self.subTest(field=field):
                result = stub_result(envelope)
                result[field] = value
                with self.assertRaisesRegex(ContractError, message):
                    validate_result(envelope, result)

    def test_result_output_limit_is_measured_in_utf8_bytes(self) -> None:
        envelope, _, _ = self.prepare()
        output = "é" * 2049  # 4,098 UTF-8 bytes despite fewer characters.
        result = stub_result(envelope, output)
        with self.assertRaisesRegex(ContractError, "output is empty or too large"):
            validate_result(envelope, result)

    def test_receipt_rejects_changed_envelope_link(self) -> None:
        envelope, _, _ = self.prepare()
        receipt = {"schema_version": 1, "work_id": envelope["work_id"], "attempt_id": envelope["attempt_id"],
                   "envelope_digest": envelope_digest(envelope), "charter_digest": envelope["charter_digest"],
                   "charter_sources": envelope["charter_sources"], "run_protocol_revision": envelope["run_protocol_revision"],
                   "manifest_digest": envelope["manifest_digest"], "definition_digest": envelope["definition_digest"],
                   "provider": envelope["provider"], "status": "failed", "actions": []}
        validate_receipt(envelope, receipt)
        receipt["envelope_digest"] = "0" * 64
        with self.assertRaisesRegex(ContractError, "receipt envelope link mismatch"):
            validate_receipt(envelope, receipt)

    def test_prepare_creates_owner_only_execution_records(self) -> None:
        envelope, attempt_dir, ledger = self.prepare()
        execution_dir = attempt_dir.parent
        for path in (execution_dir, attempt_dir, attempt_dir / "checkpoints"):
            with self.subTest(path=path):
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((attempt_dir / "envelope.json").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(ledger.path.stat().st_mode), 0o600)
        self.assertEqual(envelope["checkpoint_dir"], str(attempt_dir / "checkpoints"))
        for name, expected in (("manifest.snapshot.json", envelope["manifest_digest"]),
                               ("requirements.snapshot.md", envelope["charter_sources"]["requirements"]["sha256"]),
                               ("acceptance.snapshot.md", envelope["charter_sources"]["acceptance"]["sha256"])):
            snapshot = attempt_dir / name
            self.assertEqual(hashlib.sha256(snapshot.read_bytes()).hexdigest(), expected)
            self.assertEqual(stat.S_IMODE(snapshot.stat().st_mode), 0o600)

    def test_ollama_request_disables_proxy_and_refuses_redirect_without_network(self) -> None:
        envelope, _, _ = self.prepare()
        envelope = {**envelope, "provider": "ollama", "model": "fixture-model"}

        class Response:
            status = 200

            def read(self, _size):
                return json.dumps({"model": "fixture-model", "message": {"content": "local answer"}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Opener:
            def open(self, request, timeout):
                self.request, self.timeout = request, timeout
                return Response()

        opener = Opener()
        with patch.dict(os.environ, {"http_proxy": "http://proxy.invalid:8080", "https_proxy": "http://proxy.invalid:8080"}), \
             patch.object(local_worker.urllib.request, "build_opener", return_value=opener) as build:
            result = call_local(envelope)
        self.assertTrue(result["physical_call"])
        self.assertEqual(opener.request.full_url, local_worker.OLLAMA_URL)
        handlers = build.call_args.args
        proxy = next(handler for handler in handlers if isinstance(handler, local_worker.urllib.request.ProxyHandler))
        redirect = next(handler for handler in handlers if isinstance(handler, local_worker._NoRedirect))
        self.assertEqual(proxy.proxies, {})
        with self.assertRaisesRegex(RuntimeError, "redirect refused"):
            redirect.redirect_request(opener.request, None, 302, "Found", {}, "http://elsewhere.invalid")


class ExecutionGatewayTests(ExecutionFixture):
    def test_completed_stub_attempt_seals_truthful_nonphysical_receipt(self) -> None:
        def supervisor(envelope, on_propose, **_kwargs):
            result = on_propose(action_for(envelope))
            self.assertEqual(result["status"], "completed")
            checkpoint_id = str(uuid.uuid4())
            checkpoint = Path(envelope["checkpoint_dir"]) / f"{checkpoint_id}.json"
            checkpoint.write_text("{}\n")
            return {"attempt_id": envelope["attempt_id"], "checkpoint_id": checkpoint_id, "runtime_version": "fixture-maf-1"}

        result = self.run_gateway(supervisor)
        self.assertEqual(result["status"], "completed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["provider"], "local-stub")
        self.assertEqual(receipt["actions"][0]["result"]["physical_call"], False)
        self.assertEqual(uuid.UUID(receipt["checkpoint_id"]).version, 4)

    def test_missing_supervisor_checkpoint_seals_failed_receipt(self) -> None:
        def supervisor(envelope, on_propose, **_kwargs):
            self.assertEqual(on_propose(action_for(envelope))["status"], "completed")
            return {"attempt_id": envelope["attempt_id"], "checkpoint_id": str(uuid.uuid4())}

        result = self.run_gateway(supervisor)
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"][0]["status"], "completed")
        self.assertIn("checkpoint is absent", receipt["reason"])

    def test_duplicate_proposal_is_denied_before_a_second_adapter_call(self) -> None:
        calls = []

        def adapter(envelope):
            calls.append(envelope["attempt_id"])
            return stub_result(envelope)

        def supervisor(envelope, on_propose, **_kwargs):
            proposal = action_for(envelope)
            self.assertEqual(on_propose(proposal)["status"], "completed")
            duplicate = on_propose(proposal)
            self.assertEqual(duplicate["status"], "denied")
            self.assertEqual(duplicate["reason"], "duplicate_request")
            return {"attempt_id": envelope["attempt_id"]}

        result = self.run_gateway(supervisor, adapter)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(calls), 1)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(len(receipt["actions"]), 1)
        self.assertEqual(receipt["actions"][0]["status"], "completed")

    def test_supervisor_launch_failure_seals_receipt_without_dispatch(self) -> None:
        def launch_failure(*_args, **_kwargs):
            raise RuntimeError("MAF optional dependency unavailable")

        result = self.run_gateway(launch_failure)
        self.assertEqual(result["status"], "failed")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"], [])
        self.assertIn("optional dependency unavailable", receipt["reason"])
        self.assertEqual(stat.S_IMODE(Path(result["receipt_path"]).stat().st_mode), 0o600)

    def test_adapter_failure_marks_unknown_and_does_not_retry(self) -> None:
        calls = []

        def broken_adapter(envelope):
            calls.append(envelope["attempt_id"])
            raise RuntimeError("simulated response-loss")

        def supervisor(envelope, on_propose, **_kwargs):
            on_propose(action_for(envelope))
            self.fail("adapter failure must interrupt the supervised proposal")

        result = self.run_gateway(supervisor, broken_adapter)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(calls), 1)
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["reason"], "reconciliation_required")
        self.assertEqual(receipt["actions"][0]["status"], "unknown")
        self.assertEqual(receipt["actions"][0]["reason"], "adapter_outcome_uncertain")

    def test_raw_invalid_child_action_never_reaches_adapter(self) -> None:
        calls = []

        def adapter(envelope):
            calls.append(envelope)
            return stub_result(envelope)

        def supervisor(envelope, on_propose, **_kwargs):
            proposal = action_for(envelope)
            proposal["action_id"] = "unbound-child-action"
            on_propose(proposal)

        result = self.run_gateway(supervisor, adapter)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(calls, [])
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual(receipt["actions"], [])

    def test_prepare_refuses_missing_run_invalid_manifest_and_outside_task(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "run not found"):
            gateway.prepare("missing", ASSIGNMENT_ID, "task.md", root=self.root)
        manifest_path = self.run_dir / "orchestration.json"
        original = manifest_path.read_text()
        manifest_path.write_text("{}")
        with self.assertRaisesRegex(ContractError, "orchestration dispatch invalid"):
            gateway.prepare(WORK_ID, ASSIGNMENT_ID, f".flow/runs/{WORK_ID}/task.md", root=self.root)
        manifest_path.write_text(original)
        (self.root / "outside.md").write_text("outside\n")
        with self.assertRaisesRegex(ContractError, "outside the run"):
            gateway.prepare(WORK_ID, ASSIGNMENT_ID, "outside.md", root=self.root)


class ExecutionCliTests(unittest.TestCase):
    def test_execute_local_cli_reports_structured_result_and_gateway_has_no_maf_dependency(self) -> None:
        spec = importlib.util.spec_from_file_location("flow_execution_cli_fixture", REPO / "cli" / "flow.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {"attempt_id": "attempt", "status": "completed", "receipt_path": "/tmp/receipt.json", "reason": ""}
        with patch.object(module, "execute_local", return_value=expected) as execute, \
             patch.object(sys, "argv", ["flow", "run", "execute-local", "fixture", "--assignment", "a", "--task-file", "task.md", "--json"]), \
             redirect_stdout(io.StringIO()) as stdout:
            code = module.main()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), expected)
        execute.assert_called_once_with("fixture", "a", "task.md")
        fresh = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import execution_gateway; assert 'agent_framework' not in sys.modules", str(REPO / "cli")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(fresh.returncode, 0, fresh.stderr)


if __name__ == "__main__":
    unittest.main()
