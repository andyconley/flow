"""Malformed manager progress replies against the pinned stock runner (ADR 0018).

The real ``runtime.maf_runner.delivery_lead`` child runs through the gateway
with scripted manager text. A spoiled progress reply is either repaired in
place or retried as a new Flow-gated manager call, and a retry counts against
the manager-call limit like any other call, so ADR 0017 expansion applies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import execution_contracts  # noqa: E402
from execution_contracts import ContractError  # noqa: E402
from maf_env import requires_maf  # noqa: E402
from tests.test_maf_expansion import MafExpansionFixture  # noqa: E402

INVALID_ESCAPE = "Verify the row `| a \\` b |` in target.py"


class SpoilingManagerFixture(MafExpansionFixture):
    # Manager call sequence -> "bad" (no JSON object) or "escape" (invalid JSON escape).
    spoil: dict[int, str] = {}

    def manager(self, message, *, envelope, workspace):
        reply = super().manager(message, envelope=envelope, workspace=workspace)
        kind = self.spoil.get(message["sequence"]) if message["phase"] == "progress" else None
        if kind == "bad":
            return {"output": "The verifier should go next."}
        if kind == "escape":
            value = json.loads(reply["output"])
            value["instruction_or_question"]["answer"] = "@@"
            return {"output": json.dumps(value).replace('"@@"', '"' + INVALID_ESCAPE + '"')}
        return reply

    def receipt(self, result):
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        envelope = json.loads((Path(result["receipt_path"]).parent / "envelope.json").read_text())
        return envelope, receipt

    def progress_events(self, attempt):
        return [(item["event"], item["action_id"]) for item in self.ledger().snapshot(attempt)["events"]
                if item["event"].startswith("manager_progress_")]


@requires_maf
class RetryPastBaseIsGrantedFromHeadroomTests(SpoilingManagerFixture):
    # facts, plan, progress->editor, progress->verifier, progress(satisfied), final = 6 calls;
    # the unparsable first progress adds a seventh, granted from the one unit of headroom.
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 6}
    headroom = {"manager_calls": 1}
    spoil = {3: "bad"}

    def test_retry_is_a_counted_call_granted_automatically(self):
        result = self.run_live()
        self.assertEqual(result["status"], "completed", result)
        calls = self.ledger().snapshot(result["attempt_id"])["manager_calls"]
        self.assertEqual([item["request"]["phase"] for item in calls],
                         ["facts", "plan", "progress", "progress", "progress", "progress", "final"])
        self.assertEqual(calls[2]["request"]["manager_round"], calls[3]["request"]["manager_round"])
        [request] = self.ledger().expansion_state(result["attempt_id"])["requests"]
        self.assertEqual((request["kind"], request["grant"]["authority"]), ("manager_call", "charter_headroom"))
        self.assertEqual([name for name, _ in self.worker_sends], ["editor", "verifier"])
        self.assertEqual(self.progress_events(result["attempt_id"]),
                         [("manager_progress_unparsable", calls[2]["call_id"])])
        self.assert_calls_unique(result["attempt_id"])
        envelope, receipt = self.receipt(result)
        self.assertEqual(receipt["manager_progress"], {"repaired": [], "unparsable": [calls[2]["call_id"]]})
        execution_contracts.validate_receipt(envelope, receipt)
        for label, block in (("tampered", {"repaired": [calls[2]["call_id"]], "unparsable": []}),
                             ("empty", {"repaired": [], "unparsable": []}), ("null", None)):
            with self.subTest(label), self.assertRaises(ContractError):
                execution_contracts.validate_receipt(envelope, {**receipt, "manager_progress": block})
        # The protocol guard itself, not the earlier envelope-protocol check.
        with self.assertRaisesRegex(ContractError, "requires protocol v8"):
            execution_contracts._validate_manager_progress({**receipt, "execution_protocol_version": 7})


@requires_maf
class RepairedReplyTests(SpoilingManagerFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 6}
    spoil = {4: "escape"}

    def test_invalid_escape_is_repaired_with_no_extra_call(self):
        result = self.run_live()
        self.assertEqual(result["status"], "completed", result)
        calls = self.ledger().snapshot(result["attempt_id"])["manager_calls"]
        self.assertEqual(len(calls), 6)
        self.assertEqual(self.progress_events(result["attempt_id"]),
                         [("manager_progress_repaired", calls[3]["call_id"])])
        self.assertEqual([name for name, _ in self.worker_sends], ["editor", "verifier"])
        envelope, receipt = self.receipt(result)
        self.assertEqual(receipt["manager_progress"], {"repaired": [calls[3]["call_id"]], "unparsable": []})
        execution_contracts.validate_receipt(envelope, receipt)


@requires_maf
class CleanRunHasNoBlockTests(SpoilingManagerFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 6}

    def test_receipt_omits_the_block_when_every_reply_parsed(self):
        result = self.run_live()
        self.assertEqual(result["status"], "completed", result)
        envelope, receipt = self.receipt(result)
        self.assertNotIn("manager_progress", receipt)
        self.assertEqual(self.progress_events(result["attempt_id"]), [])
        execution_contracts.validate_receipt(envelope, receipt)


@requires_maf
class ReplayThroughRetryTests(SpoilingManagerFixture):
    # Call 5 (the satisfied progress) is unparsable; its retry, call 6, is granted from
    # headroom; the final call 7 escalates. Recovery restores from the verifier's
    # checkpoint, so calls 5 and 6 replay from the ledger before call 7 is sent.
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 5}
    headroom = {"manager_calls": 1}
    spoil = {5: "bad"}

    def test_recovery_replays_the_retry_with_identical_ids_and_no_resend(self):
        paused = self.run_live()
        self.assertEqual(paused["status"], "expansion_paused", paused)
        first = self.ledger().snapshot(paused["attempt_id"])["manager_calls"]
        self.assertEqual([(item["sequence"], item["status"]) for item in first][-3:],
                         [(5, "completed"), (6, "completed"), (7, "denied")])
        self.assertEqual(first[4]["request"]["manager_round"], first[5]["request"]["manager_round"])
        self.decide(paused, approve=True)
        result = self.recover(paused["attempt_id"])
        self.assertEqual((result["mode"], result["status"]), ("answer", "completed"), result)
        calls = self.ledger().snapshot(paused["attempt_id"])["manager_calls"]
        self.assertEqual([item["call_id"] for item in calls], [item["call_id"] for item in first])
        sent = [call_id for _, _, call_id in self.manager_sends]
        for item in first[4:]:
            self.assertEqual(sent.count(item["call_id"]), 1)
        self.assertEqual(len(self.worker_sends), 2, "completed actions are answered, not resent")
        self.assert_calls_unique(paused["attempt_id"])


@requires_maf
class ExhaustedRetriesTests(SpoilingManagerFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 8}
    spoil = {3: "bad", 4: "bad", 5: "bad"}

    def test_three_unparsable_replies_fail_the_attempt_without_replan(self):
        result = self.run_live()
        self.assertEqual(result["status"], "failed", result)
        self.assertIn("manager progress unparsable after 3 attempts", result["reason"])
        phases = [item["request"]["phase"] for item in self.ledger().snapshot(result["attempt_id"])["manager_calls"]]
        self.assertEqual(phases, ["facts", "plan", "progress", "progress", "progress"])
        self.assertEqual(self.worker_sends, [])

