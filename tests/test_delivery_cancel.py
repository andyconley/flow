"""Cooperative cancel of a live v8 parent, through real processes and signals (ADR 0019)."""

from __future__ import annotations

import contextlib
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import delivery_cancel  # noqa: E402
import delivery_termination  # noqa: E402
import process_identity  # noqa: E402
from delivery_control import change_lead_claim  # noqa: E402
from delivery_termination import CANCEL_REQUEST, cancel_delivery  # noqa: E402
from execution_contracts import validate_receipt  # noqa: E402
from execution_ledger import ExecutionLedger  # noqa: E402
from delivery_recovery import RecoveryRefused  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture  # noqa: E402
from tests.test_chartered_delivery_recovery import RecoveryHarness  # noqa: E402

HARNESS = Path(__file__).resolve().parent / "delivery_cancel_harness.py"


class ControllerTests(unittest.TestCase):
    """R2, A6: the handler only sets a flag, and raises once, only inside a wait."""

    def setUp(self):
        self.controller = delivery_cancel.CancelController()
        self.assertTrue(self.controller.install(), "the test runner's main thread installs the handler")
        self.addCleanup(self.controller.restore)

    def test_a_signal_outside_a_wait_only_sets_the_flag(self):
        os.kill(os.getpid(), signal.SIGTERM)
        self.assertTrue(self.controller.requested)
        self.assertFalse(self.controller.raised)
        with self.assertRaises(delivery_cancel.DeliveryCancelled):
            self.controller.check()

    def test_a_signal_inside_a_wait_raises_once(self):
        with self.assertRaises(delivery_cancel.DeliveryCancelled):
            with self.controller.interruptible():
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(5)
        with self.controller.interruptible():
            os.kill(os.getpid(), signal.SIGTERM)  # a second signal never raises again
        self.assertTrue(self.controller.raised)

    def test_a_pending_cancel_breaks_a_wait_on_entry_once(self):
        os.kill(os.getpid(), signal.SIGTERM)
        with self.assertRaises(delivery_cancel.DeliveryCancelled):
            with self.controller.interruptible():
                self.fail("the wait must not start")
        with self.controller.interruptible():
            pass

    def test_disarm_stops_raising_and_boundary_checks(self):
        self.controller.disarm()
        with self.controller.interruptible():
            os.kill(os.getpid(), signal.SIGTERM)
        self.assertTrue(self.controller.requested)
        self.controller.check()

    def test_restore_puts_the_previous_handler_back(self):
        self.controller.restore()
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_DFL)


class CancelFixture(CharteredFixture):
    def setUp(self):
        super().setUp()
        self.fifo = self.root / "sync.fifo"
        os.mkfifo(self.fifo)
        # Held open read-write so select waits for data instead of reporting EOF.
        self.fifo_fd = os.open(self.fifo, os.O_RDWR | os.O_NONBLOCK)
        self.addCleanup(os.close, self.fifo_fd)
        self.buffer = b""

    def ledger(self):
        return ExecutionLedger(self.run / "execution" / "ledger.sqlite", read_only=True)

    def start(self, scenario, env=None):
        process = subprocess.Popen([sys.executable, str(HARNESS), scenario, str(self.root), str(self.worktree),
                                    self.commit, str(self.fifo)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, env={**os.environ, **(env or {})})
        self.addCleanup(lambda: process.poll() is None and process.kill())
        return process

    def wait_line(self, process, timeout=30):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or process.poll() is not None and not select.select([self.fifo_fd], [], [], 0)[0]:
                out, err = process.communicate(timeout=10) if process.poll() is not None else ("", "")
                self.fail(f"no sync line from the harness: {out} {err}")
            if select.select([self.fifo_fd], [], [], min(remaining, 0.5))[0]:
                self.buffer += os.read(self.fifo_fd, 4096)
        line, _, self.buffer = self.buffer.partition(b"\n")
        return line.decode()

    def finish(self, process):
        out, err = process.communicate(timeout=60)
        self.assertEqual(process.returncode, 0, out + err)
        return json.loads(out)

    def attempt_id(self):
        """The newest attempt: the one the harness is running."""
        return max((self.run / "execution").glob("*/envelope.json"), key=lambda path: path.stat().st_mtime_ns).parent.name

    def cancel(self, *, actor="andy", generation=1, wait=45):
        return cancel_delivery("sample", self.attempt_id(), actor=actor, explanation="stop this run",
                               expected_generation=generation, root=self.root, wait_seconds=wait)

    def assert_no_recorded_group_alive(self, attempt_id):
        groups = [group for record in process_identity.records(self.run / "execution" / attempt_id)
                  for group in record["groups"]]
        self.assertTrue(groups)
        self.assertEqual([group for group in groups if process_identity.group_alive(group)], [])

    def assert_cancelled(self, reply, outcome, *, actor="andy", unknown_rows=1, generation=1):
        attempt_id = reply["attempt_id"]
        self.assertEqual(reply["status"], "cancelled")
        self.assertEqual(outcome["result"]["status"], "cancelled")
        snapshot = self.ledger().snapshot(attempt_id)
        receipt = json.loads(Path(reply["receipt_path"]).read_text())
        self.assertEqual((snapshot["status"], snapshot["owner_generation"], receipt["termination"]["actor"],
                          receipt["termination"]["cause"], receipt["termination"]["explanation"]),
                         ("cancelled", generation + 1, actor, "cancel_request", "stop this run"))
        rows = receipt["actions"] + receipt["manager_calls"]
        self.assertEqual(sum(item["status"] == "unknown" for item in rows), unknown_rows)
        validate_receipt(snapshot["envelope"], receipt)
        self.assert_no_recorded_group_alive(attempt_id)
        return snapshot, receipt


class LiveCancelTests(CancelFixture):
    """AC1, AC1b, AC1c, A3: cancel a parent blocked in each kind of wait."""

    def test_cancel_during_a_blocked_provider_call(self):
        # The parent holds the run lock through a guarded send, so the lead
        # cannot change here; the lead variants below cancel between callbacks.
        process = self.start("worker")
        self.assertTrue(self.wait_line(process).startswith("blocked "))
        started = time.monotonic()
        reply = self.cancel(actor="shaper")
        self.assertLess(time.monotonic() - started, 45)
        outcome = self.finish(process)
        self.assertEqual(outcome["sends"], ["editor"], "the uncertain send is never resent")
        _, receipt = self.assert_cancelled(reply, outcome, actor="shaper")
        self.assertEqual([(item["status"], item["reason"]) for item in receipt["actions"]],
                         [("unknown", "specialist_send_outcome_uncertain")])

    def _blocking_child(self):
        fake = self.root / "blocking-maf"
        fake.write_text(f"#!{sys.executable}\nimport os, sys, time\nsys.stdin.readline()\n"
                        f"fd = os.open({str(self.fifo)!r}, os.O_WRONLY); os.write(fd, b'blocked\\n'); os.close(fd)\n"
                        "time.sleep(300)\n")
        fake.chmod(0o700)
        return self.start("child", env={"FLOW_MAF_PYTHON": str(fake)})

    def test_cancel_on_the_real_maf_child_under_each_lead_status(self):
        for lead_status in ("active", "attention_required", "released"):
            with self.subTest(lead=lead_status):
                process = self._blocking_child()
                self.assertEqual(self.wait_line(process), "blocked")
                if lead_status != "active":
                    self.assertTrue(change_lead_claim("sample", "attention", root=self.root)[0])
                if lead_status == "released":
                    self.assertTrue(change_lead_claim("sample", "release", root=self.root)[0])
                generation = self.ledger().snapshot(self.attempt_id())["owner_generation"]
                reply = self.cancel(generation=generation)
                outcome = self.finish(process)
                self.assert_cancelled(reply, outcome, unknown_rows=0, generation=generation)
                [record] = process_identity.records(self.run / "execution" / reply["attempt_id"])
                self.assertEqual(([group["kind"] for group in record["groups"]], record["cancel_supported"],
                                  record["closed"]), (["maf"], True, True))
                if lead_status != "active":
                    changed, run, errors = change_lead_claim("sample", "resume", root=self.root,
                                                             owner=f"next-{lead_status}")
                    self.assertTrue(changed, errors)
                    self.state = run

    def test_cancel_while_blocked_in_a_manager_call(self):
        process = self.start("manager")
        self.wait_line(process)
        reply = self.cancel()
        outcome = self.finish(process)
        _, receipt = self.assert_cancelled(reply, outcome)
        self.assertEqual([item["status"] for item in receipt["manager_calls"]], ["unknown"])

    def test_cancel_during_the_real_claude_edit_worker(self):
        self.manifest["assignments"][1]["execution"] = {"provider": "claude", "model": "editor-model"}
        self._write_inputs()
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "claude").write_text(
            f"#!{sys.executable}\nimport os, time\n"
            f"fd = os.open({str(self.fifo)!r}, os.O_WRONLY); os.write(fd, b'claude blocked\\n'); os.close(fd)\n"
            "time.sleep(300)\n")
        (bin_dir / "claude").chmod(0o700)
        process = self.start("claude", env={"PATH": f"{bin_dir}:{os.environ['PATH']}"})
        self.assertEqual(self.wait_line(process), "claude blocked")
        reply = self.cancel()
        outcome = self.finish(process)
        self.assert_cancelled(reply, outcome)
        [record] = process_identity.records(self.run / "execution" / reply["attempt_id"])
        self.assertEqual([group["kind"] for group in record["groups"]], ["provider"],
                         "the real edit worker registered its own session")

    def test_a_successor_completes_after_a_cancel(self):
        process = self.start("worker")
        self.wait_line(process)
        reply = self.cancel()
        self.finish(process)
        result, sends, _, captured = self._run_v8([self.PASS])
        self.assertEqual((result["status"], sends), ("completed", ["editor", "verifier"]))
        self.assertEqual(captured["envelope"]["predecessors"][0]["terminal_status"], "cancelled")
        self.assertEqual(json.loads(Path(result["receipt_path"]).read_text())["lineage_usage"]["predecessor_paid_calls"], 1)
        self.assertEqual(reply["status"], "cancelled")


class SignalWithoutRequestTests(CancelFixture):
    """AC2b, AC2c: a stray SIGTERM or a stale request interrupts; a late cancel finds the real receipt."""

    _blocking_child = LiveCancelTests._blocking_child

    def _assert_interrupted(self, outcome):
        attempt_id = outcome["result"]["attempt_id"]
        self.assertEqual((outcome["result"]["status"], outcome["result"]["reason"]), ("interrupted", "cancel_signal"))
        snapshot = self.ledger().snapshot(attempt_id)
        self.assertEqual((snapshot["status"], [item["cause"] for item in snapshot["interruptions"]]),
                         ("started", ["cancel_signal"]))
        self.assertFalse((self.run / "execution" / attempt_id / "receipt.json").exists())
        self.assertIsNone(snapshot["sealed_receipt_sha256"])

    def test_a_bare_sigterm_leaves_the_attempt_started_with_an_interruption(self):
        process = self._blocking_child()
        self.wait_line(process)
        os.kill(process.pid, signal.SIGTERM)
        self._assert_interrupted(self.finish(process))

    def test_a_request_for_another_generation_is_not_a_cancel(self):
        process = self.start("worker")
        self.wait_line(process)
        (self.run / "execution" / self.attempt_id() / CANCEL_REQUEST).write_text(json.dumps(
            {"schema_version": 1, "attempt_id": self.attempt_id(), "owner_generation": 99, "actor": "andy",
             "explanation": "stale", "nonce": "0" * 32}))
        os.kill(process.pid, signal.SIGTERM)
        outcome = self.finish(process)
        self._assert_interrupted(outcome)
        self.assertEqual(outcome["sends"], ["editor"])
        self.assertEqual([item["status"] for item in self.ledger().snapshot(self.attempt_id())["actions"]], ["unknown"])

    def test_a_cancel_after_the_runtime_outcome_reports_the_real_receipt(self):
        process = self.start("outcome")
        self.assertEqual(self.wait_line(process), "outcome")
        reply = self.cancel()
        outcome = self.finish(process)
        self.assertEqual((reply["status"], reply["terminal_status"]), ("attempt_finished", "completed"))
        self.assertEqual(outcome["result"]["status"], "completed")
        self.assertEqual(reply["receipt_path"], outcome["result"]["receipt_path"])
        self.assertEqual(self.ledger().snapshot(self.attempt_id())["status"], "completed")


class ReviewRefinementTests(unittest.TestCase):
    """Acceptance-review fixes: a leftover request and a failed reap."""

    def test_a_request_left_before_the_parent_recorded_itself_is_cleared(self):
        # A cancel CLI that died after writing its request must not let a later
        # stray SIGTERM seal cancelled under that request's actor.
        with tempfile.TemporaryDirectory() as tmp:
            attempt_dir = Path(tmp)
            (attempt_dir / CANCEL_REQUEST).write_text(json.dumps(
                {"schema_version": 1, "attempt_id": "a1", "owner_generation": 1, "actor": "andy",
                 "explanation": "left over", "nonce": "0" * 32}))
            with delivery_cancel.parent_scope(attempt_dir, 1, attempt_id="a1"):
                self.assertFalse(os.path.lexists(attempt_dir / CANCEL_REQUEST))
                self.assertIsNone(delivery_termination.valid_cancel_request(attempt_dir, "a1", 1))

    def test_a_failed_reap_still_records_the_interruption(self):
        ledger = unittest.mock.Mock()
        ledger.record_interruption.return_value = {"interruption_id": "i1"}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(process_identity, "reap", side_effect=OSError("ps unavailable")), \
                patch.object(delivery_termination, "parent_fences", lambda *_: contextlib.nullcontext()):
            outcome = delivery_termination.stop_on_cancel({"attempt_id": "a1"}, Path(tmp), ledger,
                                                          generation=1, detail="sigterm")
        self.assertEqual((outcome["status"], outcome["interruption_id"]), ("interrupted", "i1"))
        self.assertEqual(outcome["reaped"][0]["action"], "reap_failed")
        ledger.record_interruption.assert_called_once()


class CancelRefusalTests(CancelFixture):
    """AC2: each refusal mutates nothing and signals nothing."""

    def _parent(self, *, supported=True, **overrides):
        """A started attempt whose recorded parent is a real sleeping process."""
        envelope, _, attempt_dir, _ = self.prepare()
        parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.addCleanup(lambda: (parent.kill(), parent.wait()))
        with process_identity.control_scope(attempt_dir, 1, attempt_id=envelope["attempt_id"],
                                            cancel_supported=supported):
            pass
        (attempt_dir / "control-g1.closed").unlink()
        record_path = attempt_dir / "control-g1.json"
        record = json.loads(record_path.read_text())
        record.update(pid=parent.pid, start_time=process_identity.start_time(parent.pid), **overrides)
        record_path.write_text(json.dumps(record))
        return envelope["attempt_id"], attempt_dir, parent

    def _assert_refused(self, reason, attempt_dir, parent, **kwargs):
        before = self.ledger().snapshot(attempt_dir.name)
        with self.assertRaises(RecoveryRefused) as raised:
            self.cancel(**kwargs)
        self.assertEqual(raised.exception.reason, reason)
        self.assertEqual(self.ledger().snapshot(attempt_dir.name), before)
        self.assertFalse((attempt_dir / CANCEL_REQUEST).exists())
        self.assertIsNone(parent.poll(), "a refused cancel signals nothing")

    def test_each_refusal(self):
        _, attempt_dir, parent = self._parent()
        record_path = attempt_dir / "control-g1.json"
        good = json.loads(record_path.read_text())
        cases = {
            "attempt_not_live": {"pid": 2 ** 22 + 7, "start_time": good["start_time"]},
            "process_identity_mismatch": {"start_time": "darwin:1.000000"},
            "foreign_machine": {"machine_id": "darwin:00000000-0000-0000-0000-000000000000"},
            "cancel_unsupported": {"cancel_supported": False},
        }
        for reason, change in cases.items():
            with self.subTest(reason=reason):
                record_path.write_text(json.dumps({**good, **change}))
                self._assert_refused(reason, attempt_dir, parent)
        record_path.write_text(json.dumps(good))
        with self.subTest(reason="owner_generation_stale"):
            self._assert_refused("owner_generation_stale", attempt_dir, parent, generation=2)
        (attempt_dir / "control-g1.closed").write_text("{}")
        with self.subTest(reason="closed record"):
            self._assert_refused("attempt_not_live", attempt_dir, parent)

    def test_a_record_naming_flow_itself_is_never_signalled(self):
        _, attempt_dir, parent = self._parent()
        record_path = attempt_dir / "control-g1.json"
        record = json.loads(record_path.read_text())
        record.update(pid=os.getpid(), start_time=process_identity.start_time(os.getpid()))
        record_path.write_text(json.dumps(record))
        self._assert_refused("process_identity_mismatch", attempt_dir, parent)

    def test_a_cancel_that_does_not_seal_leaves_no_request_behind(self):
        # The recorded parent dies on SIGTERM without sealing: cancel_timeout,
        # and the request is removed so a later stray SIGTERM is not a cancel.
        _, attempt_dir, parent = self._parent()
        with self.assertRaises(RecoveryRefused) as raised:
            self.cancel(wait=10)
        self.assertEqual(raised.exception.reason, "cancel_timeout")
        parent.wait(timeout=10)
        self.assertFalse((attempt_dir / CANCEL_REQUEST).exists())
        self.assertEqual(self.ledger().snapshot(attempt_dir.name)["status"], "started")

    def test_a_terminal_attempt_refuses(self):
        attempt_id, attempt_dir, parent = self._parent()
        with sqlite3_connect(self.run / "execution" / "ledger.sqlite") as db:
            db.execute("UPDATE attempts SET status='completed' WHERE attempt_id=?", (attempt_id,))
        self._assert_refused("attempt_not_started", attempt_dir, parent)


class RecoveryCancelTests(RecoveryHarness):
    """F13: a recovering parent is cancellable too, even inside its evidence rebuild's targeted test."""

    def test_a_cancel_during_the_recovery_test_seals_the_attempt_cancelled(self):
        with self._kill_once("complete", after=True):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        attempt_dir = self.run / "execution" / attempt_id

        def cancelled_test(worktree, job, **kwargs):
            (attempt_dir / CANCEL_REQUEST).write_text(json.dumps(
                {"schema_version": 1, "attempt_id": attempt_id, "owner_generation": 2, "actor": "shaper",
                 "explanation": "stop the recovery", "nonce": "1" * 32}))
            with delivery_cancel.interruptible():
                os.kill(os.getpid(), signal.SIGTERM)
                time.sleep(5)
            raise AssertionError("the test wait was not interrupted")

        with patch("delivery_gateway._run_chartered_test", side_effect=cancelled_test):
            result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual((result["status"], result["owner_generation"]), ("cancelled", 3))
        self.assertEqual(self.sends, ["editor"], "nothing is sent after the cancel")
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        self.assertEqual((receipt["termination"]["actor"], receipt["termination"]["owner_generation"]), ("shaper", 2))
        self.assertEqual([item["generation"] for item in receipt["recovery"]["recoveries"]], [2])
        self.assertEqual([record["owner_generation"] for record in process_identity.records(attempt_dir)], [1, 2])
        self.assertIs(signal.getsignal(signal.SIGTERM), signal.SIG_DFL, "the handler is restored")


def sqlite3_connect(path):
    import sqlite3
    return sqlite3.connect(path)


if __name__ == "__main__":
    unittest.main()
