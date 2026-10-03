"""Grant history: every v8 grant change writes one ``grant_changed`` event (ADR 0020, AC3)."""

from __future__ import annotations

import ast
import json
import re
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT / "tests"))
import execution_ledger  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from tests.test_expansion_ledger import manager_request, v8  # noqa: E402
from tests.test_structured_verifier_ledger import _action  # noqa: E402

LEDGER = REPO_ROOT / "cli" / "execution_ledger.py"
WRITE = re.compile(r"(UPDATE|INSERT(\s+OR\s+\w+)?\s+INTO|REPLACE\s+INTO|DELETE\s+FROM)\s+(actions|manager_calls)\b",
                   re.IGNORECASE)
EXECUTE = {"execute", "executemany", "executescript"}
# Calls whose SQL is built at run time; each is a read, never a write.
NON_STATIC = {"_granted_units": "reads grant counts", "_snapshot_locked": "reads checkpoint links"}

# Every write to actions or manager_calls, classified. ``op`` sites must emit
# grant_changed with that op in the same function; exempt sites say why not.
SITES = {
    ("decide", "INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,result_json,kind,"
               "sequence,proposal_digest) VALUES(?,?,?,?,?,?,?,?,?,?)"): ("op", ("issue", "deny")),
    ("decide_manager_call", "INSERT INTO manager_calls(call_id,attempt_id,sequence,request_json,status,reason,"
                            "grant_id) VALUES(?,?,?,?,?,?,?)"): ("op", ("issue", "deny")),
    ("consume_grant", "UPDATE actions SET status='started' WHERE action_id=?"): ("op", ("consume",)),
    ("consume_grant", "UPDATE actions SET status='denied',reason='grant_expired' WHERE action_id=?"): ("op", ("expire",)),
    ("consume_manager_grant", "UPDATE manager_calls SET status='started' WHERE call_id=?"): ("op", ("consume",)),
    ("consume_manager_grant", "UPDATE manager_calls SET status='denied',reason='grant_expired' WHERE call_id=?"):
        ("op", ("expire",)),
    ("prepare_verifier_send", "UPDATE actions SET status='started' WHERE action_id=?"): ("op", ("consume",)),
    ("prepare_verifier_send", "UPDATE actions SET status='denied',reason='grant_expired' WHERE action_id=?"):
        ("op", ("expire",)),
    ("close_pre_send_failure", "UPDATE actions SET status='not_dispatched',reason='pre_send_failure',grant_id=NULL "
                               "WHERE action_id=?"): ("op", ("release",)),
    ("seal_superseded_attempts", "UPDATE actions SET status='not_dispatched',reason='superseded_unconsumed_grant',"
                                 "grant_id=NULL WHERE action_id=?"): ("op", ("release",)),
    ("seal_terminal_uncertain", "UPDATE actions SET status='not_dispatched',reason=?,grant_id=NULL WHERE action_id=?"):
        ("op", ("release",)),
    ("claim_chartered_recovery", "UPDATE actions SET status='not_dispatched',reason='recovery_unconsumed_grant',"
                                 "grant_id=NULL WHERE action_id=?"): ("op", ("release",)),
    ("regrant_recovered_action", "UPDATE actions SET status='denied',reason=? WHERE action_id=?"): ("op", ("deny",)),
    ("regrant_recovered_action", "UPDATE actions SET status='allowed',reason='recovery_regranted',grant_id=? "
                                 "WHERE action_id=?"): ("op", ("issue",)),
    ("regrant_expanded_action", "UPDATE actions SET status='allowed',reason='expansion_granted',grant_id=? "
                                "WHERE action_id=?"): ("op", ("issue",)),
    ("reissue_expanded_manager_grant", "UPDATE manager_calls SET status='allowed',reason='expansion_granted',"
                                       "grant_id=? WHERE call_id=?"): ("op", ("issue",)),
    ("reissue_recovered_manager_grant", "UPDATE manager_calls SET grant_id=? WHERE call_id=?"): ("op", ("rotate",)),
    ("reissue_recovered_manager_grant", "UPDATE manager_calls SET status='denied',reason=?,grant_id=NULL WHERE call_id=?"):
        ("op", ("deny",)),
    ("_append_resolution_locked", "UPDATE actions SET status='not_dispatched',reason='operator_resolved_not_dispatched',"
                                  "grant_id=NULL WHERE action_id=?"):
        ("op", ("release",)),  # unreachable for v8: resolve_unknown refuses protocol 8
    ("_append_resolution_locked", "UPDATE actions SET status='completed',result_json=?,"
                                  "reason='operator_resolved_completed' WHERE action_id=?"):
        ("exempt", "not a grant change: only from started or unknown (resolve_observed_v8)"),
    ("_claim_recovery_locked", "UPDATE actions SET status='unknown',reason='recovery_after_dispatch' WHERE action_id=?"):
        ("exempt", "not a grant change: only from started"),
    ("_claim_recovery_locked", "UPDATE manager_calls SET status='unknown',reason='recovery_after_dispatch' "
                               "WHERE call_id=?"): ("exempt", "not a grant change: only from started"),
    ("complete", "UPDATE actions SET status=?,result_json=? WHERE action_id=?"):
        ("exempt", "not a grant change: only from started or unknown"),
    ("mark_unknown", "UPDATE actions SET status='unknown',reason=? WHERE action_id=?"):
        ("exempt", "not a grant change: only from started"),
    ("mark_manager_unknown", "UPDATE manager_calls SET status='unknown',reason=? WHERE call_id=?"):
        ("exempt", "not a grant change: only from started"),
    ("observe_manager_response", "UPDATE manager_calls SET status='completed',result_json=?,observed_at=? "
                                 "WHERE call_id=?"): ("exempt", "not a grant change: only from started or unknown"),
    ("regrant_not_dispatched", "UPDATE actions SET status='allowed',reason='regranted_after_no_dispatch',grant_id=? "
                               "WHERE action_id=?"): ("exempt", "v8-unreachable: refuses protocol 8"),
    ("v9_send_fence", "INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,result_json,kind,"
                      "sequence,proposal_digest) VALUES(?,?,?,?,?,?,?,?,?,?)"):
        ("exempt", "v9 uses the selection/send fence instead of v8 grants"),
    ("_refuse_v9_budget_locked",
     "INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,result_json,kind,"
     "sequence,proposal_digest) VALUES(?,?,?,?,?,?,?,?,?,?)"):
        ("exempt", "v9 budget refusal records a proven no-I/O closure; it issues no v8 grant"),
    ("record_v9_terminal_pre_send_action",
     "INSERT INTO actions(action_id,attempt_id,request_json,status,reason,grant_id,result_json,kind,"
     "sequence,proposal_digest) VALUES(?,?,?,?,?,?,?,?,?,?)"):
        ("exempt", "v9 records a no-I/O terminal selection closure instead of a v8 grant"),
    ("v9_send_fence", "UPDATE actions SET status='unknown',reason='v9_provider_send_uncertain' "
                      "WHERE action_id=? AND status='started'"):
        ("exempt", "v9 send outcome became uncertain"),
    ("v9_send_fence", "UPDATE actions SET status='unknown',reason='v9_provider_result_unrecorded' "
                      "WHERE action_id=? AND status='started'"):
        ("exempt", "v9 send result was not durably closed"),
    ("_complete_v9_send_locked", "UPDATE actions SET status='completed',result_json=?,reason='' WHERE action_id=?"):
        ("exempt", "v9 result closure occurs only after the durable send claim"),
    ("_close_v9_observed_not_executed_locked",
     "UPDATE actions SET status='observed_not_executed',result_json=?,reason=? "
     "WHERE action_id=? AND status='started'"):
        ("exempt", "v9 provider positively refused execution after the durable send claim"),
}


def _static(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(part.value if isinstance(part, ast.Constant) else "{}" for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _static(node.left), _static(node.right)
        return None if left is None or right is None else left + right
    return None


def enumerate_writes(source):
    """Every (function, normalised SQL) write site, the grant_changed ops per function, and non-static SQL."""
    writes, ops, unresolved = Counter(), {}, []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.functions = []

        def visit_FunctionDef(self, node):
            self.functions.append(node.name)
            self.generic_visit(node)
            self.functions.pop()

        def visit_Call(self, node):
            function = self.functions[-1] if self.functions else "<module>"
            if isinstance(node.func, ast.Attribute) and node.func.attr in EXECUTE and node.args:
                text = _static(node.args[0])
                if text is None:
                    unresolved.append(function)
                elif WRITE.search(text):
                    writes[(function, " ".join(text.split()))] += 1
            if isinstance(node.func, ast.Attribute) and node.func.attr == "_grant_changed":
                op = node.args[4] if len(node.args) > 4 else None
                values = ([op.value] if isinstance(op, ast.Constant)
                          else [v.value for v in (op.body, op.orelse) if isinstance(v, ast.Constant)]
                          if isinstance(op, ast.IfExp) else ["<dynamic>"])
                ops.setdefault(function, Counter()).update(values)
            self.generic_visit(node)

    Visitor().visit(ast.parse(source))
    return writes, ops, unresolved


class StructuralTests(unittest.TestCase):
    def setUp(self):
        self.writes, self.ops, self.unresolved = enumerate_writes(LEDGER.read_text())

    def test_every_write_site_is_classified_exactly(self):
        expected = Counter({key: 1 for key in SITES})
        self.assertEqual(self.writes, expected, "an unclassified or removed write to actions/manager_calls")

    def test_only_allowlisted_sql_is_built_at_run_time(self):
        self.assertEqual(set(self.unresolved) - set(NON_STATIC), set())

    def test_every_op_site_emits_its_op_in_the_same_function(self):
        needed = {}
        for (function, _), (kind, detail) in SITES.items():
            if kind == "op":
                needed.setdefault(function, Counter()).update(detail)
        for function, ops in needed.items():
            with self.subTest(function=function):
                found = self.ops.get(function, Counter())
                for op, count in ops.items():
                    self.assertGreaterEqual(found[op], count, f"{function} lacks grant_changed op={op}")

    def test_a_new_site_would_fail_the_check(self):
        source = LEDGER.read_text() + ("\n\ndef _probe(db):\n"
                                       "    db.execute(\"update actions set status='allowed' where action_id=?\", ('x',))\n")
        writes, _, _ = enumerate_writes(source)
        self.assertNotEqual(writes, Counter({key: 1 for key in SITES}))

    def test_v8_unreachable_sites_stay_refused(self):
        text = LEDGER.read_text()
        for function in ("resolve_unknown", "regrant_not_dispatched"):
            body = text[text.index(f"def {function}("):]
            body = body[:body.index("\n    def ", 10)]
            self.assertRegex(body, r"8", f"{function} no longer names protocol 8")


class GrantEventTests(unittest.TestCase):
    """Runtime scenarios on a v8 ledger: one grant_changed per change, before the legacy event."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = ExecutionLedger(Path(self.temporary.name) / "ledger.sqlite")
        self.env = v8({"max_paid_worker_calls": 2, "max_delegations": 3})
        self.ledger.create_attempt(self.env)

    def events(self):
        with sqlite3.connect(self.ledger.path) as db:
            return db.execute("SELECT seq,action_id,event,detail FROM events ORDER BY seq").fetchall()

    def changes(self, row_id=None):
        return [json.loads(detail) for _, action_id, event, detail in self.events()
                if event == "grant_changed" and (row_id is None or action_id == row_id)]

    def producer(self, sequence=1):
        return _action(self.env, sequence, self.env["roster"][1], f"Produce change {sequence}.")

    def test_decide_issue_then_consume(self):
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        self.assertTrue(self.ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        history = self.changes(action["action_id"])
        self.assertEqual([(item["op"], item["grant_id"]) for item in history],
                         [("issue", decision["grant_id"]), ("consume", decision["grant_id"])])
        self.assertEqual(history[0], {"grant_id": decision["grant_id"], "kind": "action", "op": "issue",
                                      "owner_generation": 1, "reason": "allowed", "row_id": action["action_id"]})
        names = [event for _, _, event, _ in self.events()]
        self.assertEqual(names[names.index("grant_changed") + 1], "policy_allowed", "written just before the legacy event")

    def test_decide_deny_has_no_grant(self):
        env = v8({"max_paid_worker_calls": 1, "max_delegations": 3}, attempt="deny-attempt")
        self.ledger.create_attempt(env)
        first = _action(env, 1, env["roster"][1], "Produce.")
        grant = self.ledger.decide(env, first, generation=1)
        self.assertTrue(self.ledger.consume_grant(first["action_id"], grant["grant_id"], generation=1))
        self.ledger.mark_unknown(first["action_id"], "lost", generation=1)
        with sqlite3.connect(self.ledger.path) as db:  # settle the row so the cap, not reconciliation, decides
            db.execute("UPDATE actions SET status='failed' WHERE action_id=?", (first["action_id"],))
        second = _action(env, 2, env["roster"][1], "Produce again.")
        decision = self.ledger.decide(env, second, generation=1)
        self.assertFalse(decision["allowed"])
        self.assertEqual(self.changes(second["action_id"]),
                         [{"grant_id": None, "kind": "action", "op": "deny", "owner_generation": 1,
                           "reason": decision["reason"], "row_id": second["action_id"]}])

    def test_expired_grant_records_expire(self):
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        later = datetime.now(timezone.utc) + timedelta(seconds=120)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return later

        with mock.patch.object(execution_ledger, "datetime", Clock):
            self.assertFalse(self.ledger.consume_grant(action["action_id"], decision["grant_id"], generation=1))
        self.assertEqual([item["op"] for item in self.changes(action["action_id"])], ["issue", "expire"])
        self.assertEqual(self.changes(action["action_id"])[-1]["grant_id"], decision["grant_id"])

    def test_pre_send_failure_records_release_with_the_dropped_grant(self):
        action = self.producer()
        decision = self.ledger.decide(self.env, action, generation=1)
        self.ledger.close_pre_send_failure(action["action_id"], decision["grant_id"], generation=1)
        history = self.changes(action["action_id"])
        self.assertEqual([(item["op"], item["grant_id"]) for item in history],
                         [("issue", decision["grant_id"]), ("release", decision["grant_id"])])

    def test_manager_issue_consume_and_expire(self):
        env = v8(manager="claude", attempt="manager-attempt")
        self.ledger.create_attempt(env)
        first = manager_request(env, 1)
        decision = self.ledger.decide_manager_call(env, first, generation=1)
        self.assertTrue(self.ledger.consume_manager_grant(first["call_id"], decision["grant_id"], generation=1))
        self.assertEqual([item["op"] for item in self.changes(first["call_id"])], ["issue", "consume"])
        self.assertEqual(self.changes(first["call_id"])[0]["kind"], "manager_call")
        self.ledger.observe_manager_response(first["call_id"], {"status": "completed", "output": "x",
                                             "output_sha256": execution_ledger.hashlib.sha256(b'"x"').hexdigest()},
                                             generation=1)
        second = manager_request(env, 2)
        grant = self.ledger.decide_manager_call(env, second, generation=1)
        later = datetime.now(timezone.utc) + timedelta(seconds=120)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return later

        with mock.patch.object(execution_ledger, "datetime", Clock):
            self.assertFalse(self.ledger.consume_manager_grant(second["call_id"], grant["grant_id"], generation=1))
        self.assertEqual([item["op"] for item in self.changes(second["call_id"])], ["issue", "expire"])

    def test_verifier_consume_is_recorded(self):
        producer = self.producer(1)
        grant = self.ledger.decide(self.env, producer, generation=1)
        self.ledger.consume_grant(producer["action_id"], grant["grant_id"], generation=1)
        from tests.test_structured_verifier_ledger import _result
        result = {**_result(producer, "done"), "provider": "claude", "physical_call": True,
                  "evidence_level": "flow_observed_claude_cli_completed_turn", "session_id": "s", "usage": None}
        self.ledger.observe_response(producer["action_id"], result, generation=1)
        self.ledger.complete(producer["action_id"], result, generation=1)
        verifier = _action(self.env, 2, self.env["roster"][0], "Verify change.")
        decision = self.ledger.decide(self.env, verifier, generation=1)
        self.ledger.prepare_verifier_send(verifier["action_id"], decision["grant_id"], {"task": "verify"},
                                          "d" * 64, "e" * 64, generation=1)
        self.assertEqual([item["op"] for item in self.changes(verifier["action_id"])], ["issue", "consume"])

    def test_v5_to_v7_streams_carry_no_grant_changed(self):
        from tests.test_chartered_execution_contract import chartered
        env = chartered()
        env["attempt_id"], env["work_id"] = "v7-attempt", "work-v7"
        self.assertNotEqual(env["execution_protocol_version"], 8)
        ledger = ExecutionLedger(Path(self.temporary.name) / "legacy.sqlite")
        ledger.create_attempt(env)
        action = _action(env, 1, env["roster"][1], "Produce.")
        decision = ledger.decide(env, action)
        self.assertIn("reason", decision)
        with sqlite3.connect(ledger.path) as db:
            names = [row[0] for row in db.execute("SELECT event FROM events ORDER BY seq")]
        self.assertIn(names[-1], {"policy_allowed", "policy_denied"})
        self.assertNotIn("grant_changed", names)


if __name__ == "__main__":
    unittest.main()
