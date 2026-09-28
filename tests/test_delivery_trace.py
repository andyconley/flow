"""``flow run trace`` (ADR 0020, AC7): rows in seq order, correlation fields, timings, read-only."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from tests.manager_stub import manager_reply  # noqa: E402

import flow  # noqa: E402
from delivery_trace import TRACE_SCHEMA_VERSION, TraceError, render_text, trace  # noqa: E402
from execution_contracts import digest, envelope_digest, expected_manager_call_id  # noqa: E402
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402

ROW_KEYS = {"type", "row_id", "seq", "provider", "model", "status", "reason", "grant_history", "grant_id",
            "session_id", "input_sha256", "request_file", "pgids", "checkpoint", "timing", "usage"}
ATTEMPT_KEYS = {"attempt_id", "execution_protocol_version", "supported", "status", "owner_generation", "owner_actor",
                "banner", "contract", "control_records", "entries", "token_cap", "totals"}


def tree_digest(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file()}


class TraceFixture(ExpansionGatewayFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 4}

    def completed_run(self):
        sends: list[str] = []
        worker_supervisor, worker = self.worker_plan(sends)

        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            messages = [{"role": "user", "contents": [{"type": "text", "text": "facts"}]}]
            request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                       "envelope_digest": envelope_digest(envelope), "sequence": 1, "phase": "facts",
                       "manager_round": 1, "prompt_digest": digest(messages)}
            on_manager({**request, "call_id": expected_manager_call_id(request), "messages": messages})
            return worker_supervisor(envelope, task, on_manager, on_action, **kwargs)

        manager = lambda message, **_: manager_reply(message, "Fixture facts",
                                                      usage={"input_tokens": 5, "output_tokens": 7})
        return self.execute(supervisor, worker=worker, manager=manager)

    def trace(self, *args, **kwargs):
        return trace("sample", *args, root=self.root, **kwargs)


class TraceRowTests(TraceFixture):
    def test_rows_follow_seq_order_with_every_correlation_field(self):
        result = self.completed_run()
        view = self.trace()
        self.assertEqual(view["schema_version"], TRACE_SCHEMA_VERSION)
        [attempt] = view["attempts"]
        self.assertEqual(set(attempt), ATTEMPT_KEYS)
        snapshot = self.ledger().snapshot(result["attempt_id"])
        rows = [entry for entry in attempt["entries"] if entry["type"] != "expansion"]
        self.assertEqual(len(rows), len(snapshot["actions"]) + len(snapshot["manager_calls"]))
        seqs = [entry["seq"] for entry in attempt["entries"]]
        self.assertEqual(seqs, sorted(seqs))
        for row in rows:
            with self.subTest(row=row["row_id"]):
                self.assertTrue(ROW_KEYS <= set(row))
                self.assertTrue(row["grant_history"], "every v8 row has grant history")
                self.assertIn(row["grant_history"][0]["op"], {"issue", "deny"})
        [manager] = [row for row in rows if row["type"] == "manager_call"]
        self.assertTrue(manager["session_id"].startswith("stub-session-"))
        self.assertEqual(manager["request_file"]["present"], True)
        self.assertEqual(manager["request_file"]["digest_matches"], True)
        self.assertEqual(manager["usage"], {"raw": {"input_tokens": 5, "output_tokens": 7}, "charged": 12,
                                            "cache_read": 0, "recognised": True})
        self.assertEqual(attempt["contract"], "handback")
        self.assertEqual(attempt["totals"]["charged_tokens"], sum(row["usage"]["charged"] for row in rows))

    def test_durations_are_the_event_differences(self):
        result = self.completed_run()
        events = self.ledger().snapshot(result["attempt_id"])["events"]
        for row in self.trace()["attempts"][0]["entries"]:
            if row["type"] == "expansion" or row["timing"]["send_started_at"] is None:
                continue
            with self.subTest(row=row["row_id"]):
                start = datetime.fromisoformat(row["timing"]["send_started_at"])
                end = datetime.fromisoformat(row["timing"]["observed_at"])
                self.assertAlmostEqual(row["timing"]["duration_seconds"], (end - start).total_seconds(), places=3)
                self.assertIn(row["timing"]["send_started_at"], {event["at"] for event in events})

    def test_totals_count_paid_and_verifier_sends(self):
        self.completed_run()
        attempt = self.trace()["attempts"][0]
        rows = [entry for entry in attempt["entries"] if entry["type"] != "expansion"]
        paid = [row for row in rows if row["provider"] in {"codex", "claude"} and row["status"] == "completed"]
        self.assertEqual(attempt["totals"]["paid_calls"], len(paid))
        self.assertEqual(attempt["totals"]["verifier_calls"],
                         sum(1 for row in rows if row.get("verifier") and row["status"] == "completed"))

    def test_a_paused_attempt_leads_with_why_and_the_next_command(self):
        result = self.completed_run()  # the third proposal exceeds base delegations and pauses
        banner = self.trace()["attempts"][0]["banner"]
        self.assertEqual((banner["state"], banner["reason"]), ("started", "expansion_paused: delegation_cap"))
        self.assertEqual(banner["row_id"], self.ledger().snapshot(result["attempt_id"])["actions"][2]["action_id"])
        self.assertTrue(banner["next_command"].startswith(f"flow run decide-expansion sample {result['attempt_id']} "))
        first = render_text(self.trace()).splitlines()[0]
        self.assertTrue(first.startswith(f"STUCK {result['attempt_id']}: expansion_paused: delegation_cap on "))

    def test_trace_writes_nothing(self):
        self.completed_run()
        before = tree_digest(self.run)
        self.trace()
        render_text(self.trace())
        self.assertEqual(tree_digest(self.run), before)

    def test_json_through_the_cli_and_refusals(self):
        self.completed_run()
        out = io.StringIO()
        with patch.object(sys, "argv", ["flow", "run", "trace", "sample", "--json", "--project-root", str(self.root)]), \
             contextlib.redirect_stdout(out):
            self.assertEqual(flow.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["schema_version"], TRACE_SCHEMA_VERSION)
        for argv in (["missing-work"], ["sample", "--attempt", "not-an-attempt"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with patch.object(sys, "argv", ["flow", "run", "trace", *argv, "--project-root", str(self.root)]), \
                     contextlib.redirect_stdout(out):
                    self.assertEqual(flow.main(), 2)
                self.assertIn("trace refused", out.getvalue())
        with self.assertRaises(TraceError):
            trace("missing-work", root=self.root)


class CompletedTraceTests(TraceFixture):
    headroom = {"delegations": 1}

    def test_the_terminal_banner_names_the_receipt(self):
        result = self.completed_run()
        self.assertEqual(result["status"], "completed", result)
        banner = self.trace()["attempts"][0]["banner"]
        snapshot = self.ledger().snapshot(result["attempt_id"])
        self.assertEqual(banner, {"state": "completed", "cause": snapshot["reason"],
                                  "receipt_sha256": snapshot["sealed_receipt_sha256"]})
        self.assertTrue(render_text(self.trace()).startswith("COMPLETED "))
        kinds = [entry["event"] for entry in self.trace()["attempts"][0]["entries"] if entry["type"] == "expansion"]
        self.assertEqual(kinds, ["expansion_requested", "expansion_granted"], "expansions are interleaved")


class UnsupportedProtocolTraceTests(TraceFixture):
    def test_a_pre_v8_attempt_is_reported_not_traced(self):
        self.completed_run()
        import sqlite3
        ledger = self.run / "execution" / "ledger.sqlite"
        with sqlite3.connect(ledger) as db:
            db.execute("UPDATE attempts SET execution_protocol_version=7")
        [attempt] = self.trace()["attempts"]
        self.assertEqual((attempt["supported"], attempt["detail"]), (False, "unsupported_protocol"))
        self.assertIn("unsupported_protocol", render_text(self.trace()))


if __name__ == "__main__":
    import unittest

    unittest.main()


import tests.test_token_gate as token_gate_tests  # noqa: E402  (module import: its tests are not re-collected)


class TokenPauseBannerTests(token_gate_tests.TokenEscalationRecoveryTests):
    """AC7 banner golden for a token_cap pause, with absolute token numbers (P-F3, P-F6)."""

    test_a_token_pause_resumes_in_answer_mode_and_sends_the_call_once = None

    def test_the_paused_banner_and_cap_state(self):
        def supervisor(envelope, task, on_manager, on_action, **kwargs):
            self.run_manager(envelope, on_manager, (1,))
            proposal = self._proposal(envelope, "editor", 1)
            self.checkpoint(envelope, proposal)
            on_action(proposal)
            self.run_manager(envelope, on_manager, (2,))
            return {"attempt_id": envelope["attempt_id"]}

        manager = lambda message, **_: manager_reply(message, "facts", usage={"input_tokens": 8_000, "output_tokens": 0})

        def worker(action, *, envelope, workspace):
            (workspace / "target.py").write_text("new\n")
            return self._result("codex", "editor-model", "Edited target")

        paused = self.execute(supervisor, worker=worker, manager=manager)
        view = trace("sample", root=self.root)
        attempt = view["attempts"][-1]
        banner = dict(attempt["banner"], since_seq="<seq>", since_at="<at>")
        denied = self.ledger().snapshot(paused["attempt_id"])["manager_calls"][-1]["call_id"]
        self.assertEqual(banner, {
            "state": "started", "reason": "expansion_paused: token_cap", "row_id": denied,
            "since_seq": "<seq>", "since_at": "<at>",
            "next_command": f"flow run decide-expansion sample {paused['attempt_id']} {paused['request_id']} "
                            "--approve|--deny --expected-generation 1 --actor NAME --explanation TEXT"})
        self.assertEqual(attempt["token_cap"], {"charged": 10_000, "maximum": 10_000, "remaining": 0,
                                                "tranches_granted": 0, "token_tranche": 5_000,
                                                "headroom_tokens_remaining": 0, "headroom_tranches_remaining": 0})
        text = render_text(view).splitlines()
        self.assertTrue(text[0].startswith(f"STUCK {paused['attempt_id']}: expansion_paused: token_cap on {denied[:12]}"))
        self.assertIn("  token cap: charged 10,000 of 10,000 (0 remaining; headroom 0 tokens = 0 x 5,000; "
                      "0 tranche(s) granted)", text)


class PreReleaseTraceTests(TraceFixture):
    """I6/A18: a pre-release v8 attempt is traced without token totals."""

    def test_a_pre_release_attempt_is_traced_as_unsupported_contract(self):
        import sqlite3
        from tests.legacy_v8_rows import legacy_envelope
        self.completed_run()
        with sqlite3.connect(self.run / "execution" / "ledger.sqlite") as db:
            envelope = json.loads(db.execute("SELECT envelope_json FROM attempts").fetchone()[0])
            db.execute("UPDATE attempts SET envelope_json=?", (json.dumps(legacy_envelope(envelope), sort_keys=True),))
        [attempt] = self.trace()["attempts"]
        self.assertEqual((attempt["supported"], attempt["contract"], attempt["totals"]["charged_tokens"], attempt["token_cap"]),
                         (True, "unsupported_contract", None, None))
        self.assertIn("unsupported_contract", render_text(self.trace()))
