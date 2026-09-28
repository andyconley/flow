"""``flow run verify-receipt`` (ADR 0020): AC15-AC19 on the fixture lineage.

Each tamper case changes one source and declares the exact set of checks
that must fail; every other check must keep its clean status, so the tests
prove each check is specific. Two expected sets differ from the AC16 table,
for the reasons recorded in validation-plan.md: the charter file is shared
by the lineage, so the recursive predecessor check (V6) also fails; and a
ledger envelope edit fails V2 through both envelope.json and the envelope
digest the receipt links.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import flow  # noqa: E402
import receipt_compare  # noqa: E402
import receipt_verify  # noqa: E402
from execution_contracts import canonical  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from receipt_verify import REQUIREDNESS, UNVERIFIABLE, VerifyRefused, verify_receipt  # noqa: E402
from tests.delivery_handback_fixture import (EDITOR_USAGE, MANAGER_USAGE, PREDECESSOR_MANAGER_USAGE, M, T, U,  # noqa: E402
                                             HandbackLineageFixture)
from tests.legacy_v8_rows import legacy_envelope  # noqa: E402
import tests.test_delivery_termination as termination_tests  # noqa: E402

ALL = [f"V{number}" for number in range(1, 18)]


def tree(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


class VerifyFixture(HandbackLineageFixture):
    def setUp(self):
        super().setUp()
        self.a, self.b = self.build_lineage()
        self.clean = self.statuses(verify_receipt("sample", root=self.root))

    def verify(self, attempt=None, **kwargs):
        return verify_receipt("sample", attempt, root=self.root, **kwargs)

    @staticmethod
    def statuses(report):
        return {item["check"]: item["status"] for item in report["checks"]}

    def dir(self, attempt):
        return self.run / "execution" / attempt

    def db(self):
        return sqlite3.connect(self.run / "execution" / "ledger.sqlite")

    def assert_fails_exactly(self, expected, report=None):
        report = report or self.verify()
        statuses = self.statuses(report)
        failing = {check for check, status in statuses.items() if status == "fail"}
        self.assertEqual(failing, set(expected), [item for item in report["checks"] if item["status"] == "fail"])
        for check in ALL:
            if check not in expected:
                self.assertEqual(statuses[check], self.clean[check], f"{check} changed status")
        self.assertEqual(report["exit_code"], 1)
        for item in report["checks"]:
            if item["status"] == "fail":
                self.assertTrue(item["detail"].strip(), f"{item['check']} fails without a diagnosis")
        return report


class CleanPassTests(VerifyFixture):
    def test_every_check_passes_or_is_not_applicable_where_the_table_allows(self):
        report = self.verify()
        self.assertEqual((report["attempt_id"], report["status"], report["exit_code"]), (self.b, "completed", 0))
        self.assertEqual([item["check"] for item in report["checks"]], ALL)
        for item in report["checks"]:
            with self.subTest(check=item["check"]):
                self.assertEqual(item["status"], "pass", item)
                self.assertGreaterEqual(item["compared"], 1)
        self.assertEqual([(item["item"], item["status"]) for item in report["unverifiable"]],
                         [(item, "unverifiable_offline") for item, _ in UNVERIFIABLE])

    def test_the_lineage_is_the_one_the_fixture_describes(self):
        snapshot = self.read_ledger().snapshot(self.b)
        [request_auto, request_engineer] = sorted(snapshot["expansions"], key=lambda item: item["created_at"])
        self.assertEqual((request_auto["grant"]["authority"], request_engineer["grant"]["authority"]),
                         ("charter_headroom", "engineer"))
        receipt = json.loads((self.dir(self.b) / "receipt.json").read_text())
        block = receipt["token_usage"]
        self.assertEqual(block["predecessor_charged"], PREDECESSOR_MANAGER_USAGE + U)
        self.assertEqual(block["observed_charged"], sum(MANAGER_USAGE.values()) + EDITOR_USAGE)
        self.assertEqual((block["tranches_granted"], block["maximum"]), (2, M + 2 * T))
        self.assertEqual(receipt["recovery"]["recoveries"][0]["mode"], "answer")
        # The automatic tranche went to manager call 4, after the verifier checkpoint, so the
        # answer-mode resume replayed it from the ledger (the D5 case) without sending it again.
        calls = {item["sequence"]: item for item in snapshot["manager_calls"]}
        self.assertEqual(request_auto["denied_row_id"], calls[4]["call_id"])
        self.assertEqual(request_engineer["denied_row_id"], calls[6]["call_id"])
        self.assertEqual(sum(1 for attempt, sequence in self.manager_sends if attempt == self.b and sequence == 4), 1)
        self.assertEqual(sum(1 for attempt, sequence in self.manager_sends if attempt == self.b and sequence == 6), 1)

    def test_no_lineage_skips_the_recursion(self):
        report = self.verify(lineage=False)
        [v6] = [item for item in report["checks"] if item["check"] == "V6"]
        self.assertEqual(v6["status"], "pass")
        self.assertIn("not recursed", v6["detail"])

    def test_the_requiredness_table_is_r14(self):
        literal = {  # R14, copied from requirements.md
            "V5": {"completed": "P", "failed": "P", "cancelled": "R", "abandoned": "R"},
            "V9": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
            "V11": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
            "V12": {"completed": "R", "failed": "P", "cancelled": "P", "abandoned": "P"},
            "V13": {"completed": "R", "failed": "R", "cancelled": "P", "abandoned": "P"},
            "V16": {"completed": "R", "failed": "R", "cancelled": "P", "abandoned": "P"},
        }
        for check in ("V1", "V2", "V3", "V4", "V7", "V8", "V15", "V17"):
            literal[check] = {status: "R" for status in ("completed", "failed", "cancelled", "abandoned")}
        for check, row in literal.items():
            for status, cell in row.items():
                with self.subTest(check=check, status=status):
                    self.assertEqual(REQUIREDNESS[check][status], cell)
        # Conditional cells ("R if ..."): callables that return R or P.
        self.assertTrue(all(callable(REQUIREDNESS["V6"][status]) for status in ("completed", "failed", "cancelled", "abandoned")))
        self.assertEqual((REQUIREDNESS["V10"]["completed"], REQUIREDNESS["V10"]["cancelled"], REQUIREDNESS["V10"]["abandoned"]),
                         ("R", "P", "P"))
        self.assertTrue(callable(REQUIREDNESS["V10"]["failed"]))
        self.assertTrue(callable(REQUIREDNESS["V14"]["completed"]) and callable(REQUIREDNESS["V14"]["failed"]))
        self.assertEqual((REQUIREDNESS["V14"]["cancelled"], REQUIREDNESS["V14"]["abandoned"]), ("P", "P"))


class TamperTests(VerifyFixture):
    """AC16: one change, one declared set of failing checks, each with a diagnosis."""

    def rewrite_json(self, path, mutate):
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(canonical(value) + "\n")

    def ledger_row(self, table, key, row_id, mutate):
        with self.db() as db:
            column = "result_json"
            value = json.loads(db.execute(f"SELECT {column} FROM {table} WHERE {key}=?", (row_id,)).fetchone()[0])
            mutate(value)
            db.execute(f"UPDATE {table} SET {column}=? WHERE {key}=?", (canonical(value), row_id))

    def editor(self):
        return next(item for item in self.read_ledger().snapshot(self.b)["actions"]
                    if item["request"]["assignment_id"] == "editor")

    def test_byte_only_receipt_change(self):
        path = self.dir(self.b) / "receipt.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assert_fails_exactly({"V1"})

    def test_receipt_content_change(self):
        self.rewrite_json(self.dir(self.b) / "receipt.json",
                          lambda r: r["manager_calls"][0].update(observed_at="2000-01-01T00:00:00+00:00"))
        report = self.assert_fails_exactly({"V1", "V3"})
        [v3] = [item for item in report["checks"] if item["check"] == "V3"]
        self.assertIn("manager_calls", v3["detail"])
        self.assertIn("observed_at", v3["detail"])
        self.assertIn("2000-01-01", v3["detail"])

    def test_ledger_result_content_with_the_same_status(self):
        self.ledger_row("actions", "action_id", self.editor()["action_id"], lambda r: r.update(thread_id="forged"))
        report = self.assert_fails_exactly({"V3"})
        [v3] = [item for item in report["checks"] if item["check"] == "V3"]
        self.assertIn("thread_id", v3["detail"])

    def test_ledger_usage_with_the_same_status(self):
        self.ledger_row("actions", "action_id", self.editor()["action_id"],
                        lambda r: r["usage"].update(output_tokens=M))
        self.assert_fails_exactly({"V3", "V4", "V17"})

    def test_ledger_envelope_limit(self):
        with self.db() as db:
            envelope = json.loads(db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (self.b,)).fetchone()[0])
            envelope["limits"]["max_runtime_seconds"] += 1
            db.execute("UPDATE attempts SET envelope_json=? WHERE attempt_id=?", (canonical(envelope), self.b))
        self.assert_fails_exactly({"V2", "V7"})

    def test_envelope_file_only(self):
        self.rewrite_json(self.dir(self.b) / "envelope.json", lambda e: e["limits"].update(max_runtime_seconds=1))
        self.assert_fails_exactly({"V2"})

    def test_charter_file_content(self):
        envelope = self.read_ledger().snapshot(self.b)["envelope"]
        path = self.run / "delivery" / envelope["delivery_charter_digest"] / "delivery-charter.json"
        self.rewrite_json(path, lambda c: c["outcomes"].append({"value": "forged", "provenance": []}))
        # The charter is shared by the lineage, so the recursive predecessor check fails too.
        self.assert_fails_exactly({"V6", "V7"})
        self.assert_fails_exactly({"V7"}, self.verify(lineage=False))

    def test_requirements_snapshot(self):
        path = self.dir(self.b) / "requirements.snapshot.md"
        path.write_bytes(path.read_bytes() + b"forged\n")
        self.assert_fails_exactly({"V8"})

    def test_checkpoint_byte(self):
        [path] = [p for p in (self.dir(self.b) / "checkpoints").glob("checkpoint-2.json")]
        path.write_bytes(path.read_bytes().replace(b"flow-magentic-action-2", b"flow-magentic-action-9"))
        self.assert_fails_exactly({"V9"})

    def test_request_file_message(self):
        path = sorted((self.dir(self.b) / "manager-requests").glob("*.json"))[0]
        self.rewrite_json(path, lambda r: r["messages"][0]["contents"][0].update(text="forged"))
        report = self.assert_fails_exactly({"V10"})
        self.assertIn(path.stem[:12], [item for item in report["checks"] if item["check"] == "V10"][0]["detail"])

    def test_repair_diff_byte(self):
        path = self.dir(self.b) / "repair.diff"
        path.write_bytes(path.read_bytes() + b"\n")
        self.assert_fails_exactly({"V11"})

    def test_trace_byte(self):
        path = self.dir(self.b) / "claude-implementer.debug.log"
        path.write_bytes(path.read_bytes() + b"x")
        self.assert_fails_exactly({"V14"})

    def test_baseline_field(self):
        self.rewrite_json(self.dir(self.b) / "baseline.json", lambda b: b.update(source_commit="0" * 40))
        self.assert_fails_exactly({"V13"})

    def test_duplicated_send_start(self):
        with self.db() as db:
            at, attempt, action, event, detail = db.execute(
                "SELECT at,attempt_id,action_id,event,detail FROM events WHERE attempt_id=? AND event='manager_send_started' "
                "ORDER BY seq LIMIT 1", (self.b,)).fetchone()
            db.execute("INSERT INTO events(at,attempt_id,action_id,event,detail) VALUES(?,?,?,?,?)",
                       (at, attempt, action, event, detail))
        report = self.assert_fails_exactly({"V15"})
        self.assertIn("resent", [item for item in report["checks"] if item["check"] == "V15"][0]["detail"])

    def test_predecessor_receipt_byte(self):
        path = self.dir(self.a) / "receipt.json"
        path.write_bytes(path.read_bytes() + b" ")
        self.assert_fails_exactly({"V6"})

    def test_group_line_row_id(self):
        path = self.dir(self.b) / "control-g1.groups.jsonl"
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        provider = [line for line in lines if line["kind"] == "provider"]
        provider[0]["row_id"] = provider[1]["row_id"]
        path.write_text("".join(json.dumps(line, sort_keys=True) + "\n" for line in lines))
        self.assert_fails_exactly({"V16"})

    def test_a_deleted_grant_issue_event(self):
        with self.db() as db:
            db.execute("DELETE FROM events WHERE seq=(SELECT MIN(seq) FROM events WHERE action_id=? AND event='grant_changed')",
                       (self.editor()["action_id"],))
        self.assert_fails_exactly({"V15", "V17"})


class NoVacuousPassTests(VerifyFixture):
    """AC17."""

    def test_a_completed_attempt_without_action_rows_fails_v3(self):
        with self.db() as db:
            db.execute("DELETE FROM actions WHERE attempt_id=?", (self.b,))
        [v3] = [item for item in self.verify()["checks"] if item["check"] == "V3"]
        self.assertEqual(v3["status"], "fail")
        self.assertIn("required block empty", v3["detail"])

    def test_missing_required_files_fail(self):
        (self.dir(self.b) / "repair.diff").unlink()
        for path in (self.dir(self.b) / "checkpoints").glob("*.json"):
            path.unlink()
        statuses = self.statuses(self.verify())
        self.assertEqual((statuses["V11"], statuses["V9"]), ("fail", "fail"))

    def test_a_supported_receipt_without_its_token_block_fails_not_unsupported(self):
        path = self.dir(self.b) / "receipt.json"
        receipt = json.loads(path.read_text())
        receipt.pop("token_usage")
        path.write_text(canonical(receipt) + "\n")
        report = self.verify()
        self.assertEqual(report["exit_code"], 1)
        self.assertEqual(self.statuses(report)["V4"], "fail")

    def test_an_unsealed_attempt_and_a_pre_release_contract_refuse(self):
        with self.db() as db:
            db.execute("UPDATE attempts SET status='started',sealed_receipt_sha256=NULL WHERE attempt_id=?", (self.b,))
        with self.assertRaises(VerifyRefused) as raised:
            self.verify(self.b)
        self.assertEqual(raised.exception.code, "attempt_not_sealed")
        with self.db() as db:
            db.execute("UPDATE attempts SET status='abandoned' WHERE attempt_id=?", (self.b,))
            envelope = json.loads(db.execute("SELECT envelope_json FROM attempts WHERE attempt_id=?", (self.a,)).fetchone()[0])
            db.execute("UPDATE attempts SET envelope_json=? WHERE attempt_id=?", (canonical(legacy_envelope(envelope)), self.a))
        report = self.verify(self.a)  # the file still seals a budget: tampering, not an old receipt
        self.assertEqual((report["exit_code"], self.statuses(report)), (1, {"V2": "fail"}))
        (self.dir(self.a) / "envelope.json").write_text(canonical(legacy_envelope(envelope)) + "\n")
        with self.assertRaises(VerifyRefused) as raised:
            self.verify(self.a)
        self.assertEqual(raised.exception.code, "unsupported_receipt")


class ReadOnlyOfflineTests(VerifyFixture):
    """AC18."""

    def test_nothing_is_written_and_nothing_leaves_the_process(self):
        before = tree(self.run)
        calls = []
        real = ExecutionLedger._db

        def counting(ledger):
            calls.append(1)
            return real(ledger)

        refuse = lambda *a, **k: (_ for _ in ()).throw(AssertionError("verify-receipt made an external call"))
        with patch.object(ExecutionLedger, "_db", counting), patch("subprocess.Popen", side_effect=refuse), \
             patch("subprocess.run", side_effect=refuse), patch("socket.socket", side_effect=refuse), \
             patch("urllib.request.urlopen", side_effect=refuse):
            report = self.verify()
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(len(calls), 1, "one read transaction through lineage_view")
        self.assertEqual(tree(self.run), before)

    def test_the_verifier_shares_the_seal_comparison(self):
        self.assertIs(receipt_verify.compare_receipt_rows, receipt_compare.compare_receipt_rows)

    def test_the_cli_exit_codes(self):
        def run(*argv):
            out = io.StringIO()
            with patch.object(sys, "argv", ["flow", "run", "verify-receipt", *argv, "--project-root", str(self.root)]), \
                 contextlib.redirect_stdout(out):
                return flow.main(), out.getvalue()
        code, text = run("sample")
        self.assertEqual(code, 0)
        self.assertTrue(text.startswith(f"verify-receipt sample {self.b} (completed): PASS"))
        code, text = run("sample", "--json")
        self.assertEqual((code, json.loads(text)["exit_code"]), (0, 0))
        receipt = self.dir(self.b) / "receipt.json"
        receipt.write_bytes(receipt.read_bytes() + b" ")
        self.assertEqual(run("sample")[0], 1)
        self.assertEqual(run("missing-work")[0], 2)


class AbandonedAndCancelledTests(VerifyFixture):
    """AC19: the abandoned predecessor verifies on its own."""

    def test_the_abandoned_attempt_passes_with_its_fixed_not_applicable_reasons(self):
        report = self.verify(self.a)
        statuses = self.statuses(report)
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(statuses["V5"], "pass", "termination is required and checked")
        for check in ("V11", "V12"):
            self.assertEqual(statuses[check], "not_applicable")
        self.assertEqual(statuses["V13"], "pass", "the baseline is always written (A12)")


class CancelledTests(termination_tests.TerminationFixture):
    def test_a_cancelled_attempt_verifies(self):
        attempt_id = self.allowed_editor_grant()
        self.seal(attempt_id, "cancelled")
        report = verify_receipt("sample", attempt_id, root=self.root)
        statuses = {item["check"]: item["status"] for item in report["checks"]}
        self.assertEqual(report["exit_code"], 0, [item for item in report["checks"] if item["status"] == "fail"])
        self.assertEqual(statuses["V5"], "pass")
        for check in ("V11", "V12", "V16"):
            self.assertEqual(statuses[check], "not_applicable")


if __name__ == "__main__":
    import unittest

    unittest.main()


import tests.test_maf_expansion as maf_expansion  # noqa: E402  (module import: its tests are not re-collected)
from maf_env import requires_maf  # noqa: E402
from tests.delivery_handback_fixture import _child  # noqa: E402


@requires_maf
class StockRunnerVerifyTests(maf_expansion.MafExpansionFixture):
    """verify-receipt on a lineage driven by the pinned stock Magentic runner (real MAF checkpoints and messages).

    Stub calls report no usage, so each paid send is charged U: m1-m3 and the
    editor bring the lineage to 4,000; m4 to 5,000; call 5 hits the 5,000 cap
    and is granted one tranche from headroom; the final call hits 6,000 and
    pauses. Recovery replays call 5 from the ledger and sends the final once.
    """

    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 8,
              "max_lineage_tokens": 5_000, "token_tranche": 1_000, "unobserved_send_tokens": 1_000}
    headroom = {"tokens": 1}

    def manager(self, message, *, envelope, workspace):
        _child(message["call_id"])
        return super().manager(message, envelope=envelope, workspace=workspace)

    def worker(self, action, *, envelope, workspace):
        _child(action["action_id"])
        return super().worker(action, envelope=envelope, workspace=workspace)

    def test_a_stock_runner_lineage_verifies(self):
        paused = self.run_live()
        self.assertEqual(paused["status"], "expansion_paused", paused)
        calls = self.ledger().snapshot(paused["attempt_id"])["manager_calls"]
        self.assertEqual(calls[-1]["reason"], "token_cap")
        self.decide(paused, approve=True)
        result = self.recover(paused["attempt_id"])
        self.assertEqual((result["mode"], result["status"]), ("answer", "completed"), result)
        self.assert_calls_unique(paused["attempt_id"])
        report = verify_receipt("sample", root=self.root)
        failed = [item for item in report["checks"] if item["status"] == "fail"]
        self.assertEqual((report["exit_code"], failed), (0, []))
        statuses = {item["check"]: item["status"] for item in report["checks"]}
        self.assertEqual(statuses["V9"], "pass", "real MAF checkpoint files bind")
        self.assertEqual(statuses["V17"], "pass")
