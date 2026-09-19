"""Recovery protocol tests for the supervised MAF child boundary.

The child is a local executable fixture.  It proves that Flow, rather than a
checkpoint, supplies the resumed action result and preserves the same action
identity.  No optional MAF package or provider is used.
"""

from __future__ import annotations

import sys
import multiprocessing
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "cli"))
sys.path.insert(0, str(REPO / "tests"))

from maf_supervisor import MafProtocolError, run_maf  # noqa: E402
from test_maf_supervisor import SupervisorProtocolTests  # noqa: E402
import execution_gateway as gateway  # noqa: E402
from test_execution import ASSIGNMENT_ID, ExecutionFixture, WORK_ID, action_for, stub_result  # noqa: E402


def _resume_in_process(root: str, attempt_id: str, results) -> None:
    try:
        results.put(gateway.resume_local(WORK_ID, attempt_id, root=Path(root)))
    except Exception as exc:
        results.put({"error": str(exc)})


class MafRecoveryProtocolTests(SupervisorProtocolTests):
    def test_resume_message_replays_one_flow_result_for_original_action(self) -> None:
        executable = self.script('''import hashlib,json,sys
start=json.loads(sys.stdin.readline())
assert start["type"] == "resume"
assert start["resume"] == {"schema_version":2,"attempt_id":"attempt-1","checkpoint_id":"checkpoint-1","ledger_seq":7}
e=start["envelope"]
def dig(v):
 return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
aid=dig({"attempt_id":e["attempt_id"],"charter_digest":e["charter_digest"],"definition_digest":e["definition_digest"],"instance_id":e["instance_id"],"kind":"delegate","sequence":1})
proposal={"protocol_version":1,"type":"propose_action","schema_version":1,"kind":"delegate","attempt_id":e["attempt_id"],"action_id":aid,"role":e["role"],"instance_id":e["instance_id"],"provider":e["provider"],"model":e["model"],"task_digest":e["task_digest"],"envelope_digest":dig(e),"sequence":1}
print(json.dumps(proposal),flush=True)
response=json.loads(sys.stdin.readline())
assert response["action_id"] == aid and response["result"]["output"] == "stored result"
print(json.dumps({"protocol_version":1,"type":"workflow_finished","attempt_id":e["attempt_id"],"checkpoint_id":"checkpoint-1","summary":"replayed"}),flush=True)
''')
        seen = []
        outcome = run_maf(
            self.envelope,
            lambda action: seen.append(action) or {"status": "completed", "action_id": action["action_id"], "output": "stored result"},
            python_path=executable,
            timeout_s=2,
            resume={"schema_version": 2, "attempt_id": "attempt-1", "checkpoint_id": "checkpoint-1", "ledger_seq": 7},
        )
        self.assertEqual(outcome["summary"], "replayed")
        self.assertEqual(len(seen), 1)

    def test_invalid_resume_contract_is_rejected_before_any_flow_callback(self) -> None:
        executable = self.script("import sys\nsys.stdin.readline()\n")
        with self.assertRaisesRegex(MafProtocolError, "invalid Flow resume message"):
            run_maf(self.envelope, lambda _: self.fail("resume must not propose"), python_path=executable,
                    timeout_s=2, resume={"schema_version": 1, "checkpoint_id": "wrong"})

    def test_resume_child_cannot_propose_a_foreign_action(self) -> None:
        executable = self.script('''import json,sys
start=json.loads(sys.stdin.readline())
e=start["envelope"]
print(json.dumps({"protocol_version":1,"type":"propose_action","schema_version":1,"kind":"delegate","attempt_id":e["attempt_id"],"action_id":"foreign","role":e["role"],"instance_id":e["instance_id"],"provider":e["provider"],"model":e["model"],"task_digest":e["task_digest"],"envelope_digest":"foreign","sequence":1}),flush=True)
''')
        with self.assertRaisesRegex(MafProtocolError, "not bound to the envelope"):
            run_maf(self.envelope, lambda _: self.fail("foreign resume must not reach Flow"), python_path=executable,
                    timeout_s=2, resume={"schema_version": 2, "attempt_id": "attempt-1", "checkpoint_id": "checkpoint-1", "ledger_seq": 7})


class ReceiptSplitRecoveryTests(ExecutionFixture):
    def test_two_full_gateway_resumes_race_without_a_second_send(self) -> None:
        envelope, attempt_dir, ledger = self.prepare()
        action = action_for(envelope)
        grant = ledger.decide(envelope, action, generation=1)
        self.assertTrue(ledger.consume_grant(action["action_id"], grant["grant_id"], generation=1))
        ledger.observe_send(action["action_id"], 1)
        counter = attempt_dir / "send-count.txt"
        counter.write_text("send\n")
        ctx = multiprocessing.get_context("spawn")
        results = ctx.Queue()
        processes = [ctx.Process(target=_resume_in_process, args=(str(self.root), envelope["attempt_id"], results)) for _ in range(2)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        outcomes = [results.get(timeout=2) for _ in processes]
        self.assertEqual({item.get("status") for item in outcomes}, {"reconciliation_required"})
        self.assertEqual({item.get("owner_generation") for item in outcomes}, {2, 3})
        self.assertEqual(counter.read_text().count("send\n"), 1)
        final = gateway.ExecutionLedger(ledger.path).snapshot(envelope["attempt_id"])
        self.assertEqual(final["actions"][0]["status"], "unknown")
        self.assertEqual(sum(e["event"] == "adapter_send_started" for e in final["events"]), 1)

    def _make_receipt_split(self):
        calls = []

        def adapter(envelope):
            calls.append(envelope["attempt_id"])
            return stub_result(envelope)

        def supervisor(envelope, on_propose, **_kwargs):
            self.assertEqual(on_propose(action_for(envelope))["status"], "completed")
            checkpoint_id = "11111111-1111-4111-8111-111111111111"
            (Path(envelope["checkpoint_dir"]) / f"{checkpoint_id}.json").write_text("{}")
            return {"attempt_id": envelope["attempt_id"], "checkpoint_id": checkpoint_id, "runtime_version": "fixture-maf-1"}

        with patch.object(gateway.ExecutionLedger, "finish_attempt", side_effect=RuntimeError("simulated post-receipt crash")):
            with self.assertRaisesRegex(RuntimeError, "post-receipt crash"):
                self.run_gateway(supervisor, adapter)
        ledger = gateway.ExecutionLedger(self.run_dir / "execution" / "ledger.sqlite")
        attempt_id = next(path.name for path in (self.run_dir / "execution").iterdir() if path.is_dir())
        return attempt_id, calls, ledger

    def test_receipt_ledger_split_repairs_without_supervisor_or_adapter_send(self) -> None:
        attempt_id, calls, ledger = self._make_receipt_split()
        before = ledger.snapshot(attempt_id)
        self.assertEqual(before["status"], "started")
        self.assertIsNone(before["receipt_path"])

        repaired = gateway.resume_local(WORK_ID, attempt_id, root=self.root,
                                        supervisor=lambda *_args, **_kwargs: self.fail("repair must not supervise"))
        after = gateway.ExecutionLedger(ledger.path).snapshot(attempt_id)

        self.assertEqual(repaired["status"], "repaired")
        self.assertEqual(after["status"], "completed")
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(event["event"] == "adapter_send_started" for event in after["events"]), 1)
        self.assertTrue((self.run_dir / "execution" / attempt_id / "receipt.json").is_file())

    def test_completed_action_replays_through_uuid_checkpoint_and_seals_terminal_receipt(self) -> None:
        attempt_id, calls, ledger = self._make_receipt_split()
        receipt_path = self.run_dir / "execution" / attempt_id / "receipt.json"
        receipt_path.unlink()  # Model the earlier crash before the receipt write.
        seen = []

        def replay_supervisor(envelope, on_propose, **kwargs):
            seen.append(kwargs["resume"])
            result = on_propose(action_for(envelope))
            self.assertEqual(result["status"], "completed")
            return {"attempt_id": envelope["attempt_id"], "summary": "replayed"}

        resumed = gateway.resume_local(WORK_ID, attempt_id, root=self.root, supervisor=replay_supervisor)
        after = gateway.ExecutionLedger(ledger.path).snapshot(attempt_id)
        sealed = __import__("json").loads(receipt_path.read_text())

        self.assertEqual(resumed["status"], "replayed")
        self.assertEqual(seen[0]["checkpoint_id"], "11111111-1111-4111-8111-111111111111")
        self.assertEqual(after["status"], "completed")
        self.assertEqual(sealed["status"], "completed")
        self.assertEqual(len(calls), 1)

    def test_conflicting_receipt_split_fails_closed_without_adapter_send(self) -> None:
        attempt_id, calls, ledger = self._make_receipt_split()
        receipt_path = self.run_dir / "execution" / attempt_id / "receipt.json"
        receipt = __import__("json").loads(receipt_path.read_text())
        receipt["status"] = "unknown"
        receipt_path.write_text(__import__("json").dumps(receipt))

        with self.assertRaisesRegex(Exception, "receipt terminal status conflicts|receipt is invalid"):
            gateway.resume_local(WORK_ID, attempt_id, root=self.root,
                                 supervisor=lambda *_args, **_kwargs: self.fail("conflict must not supervise"))
        after = gateway.ExecutionLedger(ledger.path).snapshot(attempt_id)
        self.assertEqual(after["status"], "started")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
