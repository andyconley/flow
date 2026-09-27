"""Process identity records, liveness, and reaping for v8 delivery parents (ADR 0019)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import process_identity  # noqa: E402
from maf_supervisor import MafTransportError, run_maf_delivery  # noqa: E402
from tests.test_chartered_delivery_gateway import CharteredFixture  # noqa: E402
from tests.test_chartered_delivery_recovery import RecoveryHarness  # noqa: E402

READ_START = ("import sys; sys.path.insert(0, {cli!r}); import process_identity; "
              "print(process_identity.start_time(int(sys.argv[1])))")


def _wait_gone(pid, timeout=10.0):
    """Poll a condition (not a timing guess): the pid stops existing."""
    deadline = time.monotonic() + timeout
    while process_identity.pid_alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def _sleeper(**kwargs):
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True, **kwargs)


def _stop(process):
    if process.poll() is None:
        process.kill()
    process.wait()
    for stream in (process.stdin, process.stdout):
        if stream is not None and not stream.closed:
            stream.close()


class StartTimeTests(unittest.TestCase):
    def test_start_time_reads_self_and_a_child_and_none_for_a_dead_pid(self):
        own = process_identity.start_time(os.getpid())
        self.assertRegex(own, r"^(darwin:\d+\.\d{6}|linux:[0-9a-f-]+:\d+)$")
        child = _sleeper()
        self.addCleanup(_stop, child)
        child_start = process_identity.start_time(child.pid)
        self.assertIsNotNone(child_start)
        self.assertTrue(process_identity.started_at_or_after(child_start, own))
        self.assertFalse(process_identity.started_at_or_after(own, child_start))
        child.kill()
        child.wait()
        self.assertIsNone(process_identity.start_time(child.pid))
        self.assertIsNone(process_identity.start_time(0))

    def test_the_start_time_does_not_depend_on_the_timezone(self):
        child = _sleeper()
        self.addCleanup(_stop, child)
        cli = str(Path(process_identity.__file__).parent)
        readings = {tz: subprocess.run([sys.executable, "-c", READ_START.format(cli=cli), str(child.pid)],
                                       env={**os.environ, "TZ": tz, "LC_ALL": "C"}, capture_output=True,
                                       text=True, check=True).stdout.strip()
                    for tz in ("UTC", "America/Los_Angeles", "Asia/Kolkata")}
        self.assertEqual(len(set(readings.values())), 1, readings)
        self.assertEqual(readings["UTC"], process_identity.start_time(child.pid))

    def test_the_linux_reader_parses_field_22_after_a_hostile_command_name(self):
        # Parser-tested only: CI runs no delivery tests on Linux (per-check verdict).
        fields = ["S"] + [str(value) for value in range(4, 22)] + ["987654"] + ["0"] * 30
        text = "4242 (evil ) name (x) " + " ".join(fields)
        self.assertEqual(process_identity.linux_start_from_stat(text, "boot-1"), "linux:boot-1:987654")
        self.assertIsNone(process_identity.linux_start_from_stat("4242 (short) S 1 2", "boot-1"))
        self.assertIsNone(process_identity.linux_start_from_stat(text, ""))
        self.assertTrue(process_identity.started_at_or_after("linux:b:10", "linux:b:9"))
        self.assertFalse(process_identity.started_at_or_after("linux:other:10", "linux:b:9"))

    def test_the_machine_id_is_stable(self):
        self.assertEqual(process_identity.machine_id(), process_identity.machine_id())
        self.assertRegex(process_identity.machine_id(), r"^(darwin|linux|host):.+")


class ControlRecordTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.attempt_dir = Path(tmp.name) / "attempt"
        self.attempt_dir.mkdir()

    def test_a_scope_writes_once_registers_groups_and_closes(self):
        child = _sleeper()
        self.addCleanup(_stop, child)
        with process_identity.control_scope(self.attempt_dir, 3, attempt_id="a1") as scope:
            self.assertIs(process_identity.current(), scope)
            process_identity.register_group(child.pid, "provider")
            with self.assertRaises(RuntimeError):
                with process_identity.control_scope(self.attempt_dir, 4, attempt_id="a1"):
                    pass
            [record] = process_identity.records(self.attempt_dir)
            self.assertEqual(process_identity.parent_live(record), "live")
        self.assertIsNone(process_identity.current())
        process_identity.register_group(child.pid, "provider")  # outside a scope: no-op
        [record] = process_identity.records(self.attempt_dir)
        self.assertEqual({key: record[key] for key in ("attempt_id", "owner_generation", "pid", "cancel_supported",
                                                       "closed")},
                         {"attempt_id": "a1", "owner_generation": 3, "pid": os.getpid(), "cancel_supported": False,
                          "closed": True})
        self.assertEqual(record["start_time"], process_identity.start_time(os.getpid()))
        self.assertEqual(record["machine_id"], process_identity.machine_id())
        self.assertEqual([(item["pgid"], item["kind"], item["leader_start"]) for item in record["groups"]],
                         [(child.pid, "provider", process_identity.start_time(child.pid))])
        self.assertEqual(process_identity.parent_live(record), "closed")
        with self.assertRaises(FileExistsError):
            with process_identity.control_scope(self.attempt_dir, 3, attempt_id="a1"):
                pass

    def test_liveness_verdicts(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        base = {"pid": os.getpid(), "start_time": process_identity.start_time(os.getpid()),
                "machine_id": process_identity.machine_id(), "closed": False}
        cases = {"live": base, "closed": {**base, "closed": True},
                 "dead": {**base, "pid": dead.pid, "start_time": "darwin:1.000000"},
                 "mismatch": {**base, "start_time": "darwin:1.000000"},
                 "foreign": {**base, "machine_id": "darwin:00000000-0000-0000-0000-000000000000"}}
        for verdict, record in cases.items():
            with self.subTest(verdict=verdict):
                self.assertEqual(process_identity.parent_live(record), verdict)

    def test_a_symlinked_attempt_directory_is_refused(self):
        link = self.attempt_dir.parent / "link"
        link.symlink_to(self.attempt_dir)
        with self.assertRaises(OSError):
            with process_identity.control_scope(link, 1, attempt_id="a1"):
                pass
        self.assertEqual(process_identity.records(link), [])


class ReapTests(ControlRecordTests):
    """AC4 groundwork: reap recorded groups by identity only."""

    def _record(self, generation, groups):
        with process_identity.control_scope(self.attempt_dir, generation, attempt_id="a1") as scope:
            for pid, kind in groups:
                scope.register(pid, kind)

    def test_a_group_whose_leader_is_alive_is_killed_whole(self):
        leader = _sleeper()
        self.addCleanup(_stop, leader)
        self._record(1, [(leader.pid, "provider")])
        report = process_identity.reap(self.attempt_dir)
        self.assertEqual(report, [{"owner_generation": 1, "pgid": leader.pid, "kind": "provider", "action": "killed_group"}])
        leader.wait(timeout=10)
        self.assertFalse(process_identity.group_alive({"pgid": leader.pid, "leader_start": "darwin:1.0"}))

    def test_members_of_a_group_whose_leader_exited_are_killed(self):
        leader = subprocess.Popen(
            [sys.executable, "-c", "import subprocess, sys, time\n"
             "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
             "print(child.pid, flush=True)\nsys.stdin.readline()\n"],
            start_new_session=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        member = int(leader.stdout.readline())
        self.addCleanup(_stop, leader)
        self.addCleanup(lambda: process_identity.pid_alive(member) and os.kill(member, 9))
        # Recorded while the leader lives, then the leader exits and orphans its member.
        self._record(2, [(leader.pid, "maf")])
        leader.stdin.write("exit\n")
        leader.stdin.close()
        leader.wait(timeout=10)
        self.assertTrue(process_identity.pid_alive(member))
        self.assertTrue(process_identity.group_alive(process_identity.records(self.attempt_dir)[0]["groups"][0]))
        report = process_identity.reap(self.attempt_dir)
        self.assertEqual(report, [{"owner_generation": 2, "pgid": leader.pid, "kind": "maf",
                                   "action": "killed_members", "members": [member]}])
        self.assertTrue(_wait_gone(member))

    def test_a_reused_leader_pid_is_reported_and_never_signalled(self):
        leader = _sleeper()
        self.addCleanup(_stop, leader)
        self._record(1, [(leader.pid, "test")])
        groups = self.attempt_dir / "control-g1.groups.jsonl"
        entry = json.loads(groups.read_text())
        entry["leader_start"] = "darwin:1.000000" if entry["leader_start"].startswith("darwin:") else "linux:x:1"
        groups.write_text(json.dumps(entry) + "\n")
        report = process_identity.reap(self.attempt_dir)
        self.assertEqual(report[0]["action"], "skipped_identity_mismatch")
        self.assertIsNone(leader.poll(), "a mismatched leader must not be signalled")

    def test_every_generation_is_considered(self):
        first, second = _sleeper(), _sleeper()
        self.addCleanup(_stop, first)
        self.addCleanup(_stop, second)
        self._record(1, [(first.pid, "maf")])
        self._record(2, [(second.pid, "maf")])
        report = process_identity.reap(self.attempt_dir)
        self.assertEqual([(item["owner_generation"], item["action"]) for item in report],
                         [(1, "killed_group"), (2, "killed_group")])


class MafLauncherGroupTests(unittest.TestCase):
    """The real launcher registers its child and kills the whole group on exit (F11)."""

    def test_the_maf_child_group_is_registered_and_killed_whole(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        marker = Path(tmp.name) / "grandchild.pid"
        fake = Path(tmp.name) / "fake-maf"
        fake.write_text(f"#!{sys.executable}\nimport subprocess, sys, time\n"
                        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                        f"open({str(marker)!r}, 'w').write(str(child.pid))\n"
                        "sys.stdin.readline()\ntime.sleep(120)\n")
        fake.chmod(0o700)
        envelope = {"execution_protocol_version": 8, "attempt_id": "a1", "manager": {"provider": "claude"},
                    "limits": {"max_manager_calls": 1, "max_delegations": 1}}
        registered = []
        with self.assertRaises(MafTransportError):
            run_maf_delivery(envelope, "task", lambda m: "x", lambda m: {}, timeout_s=2, python_path=str(fake),
                             on_process_group=lambda pgid, kind: registered.append((pgid, kind)))
        self.assertEqual([kind for _, kind in registered], ["maf"])
        grandchild = int(marker.read_text())
        self.assertTrue(_wait_gone(grandchild), "killpg must reach the MAF child's own subprocess")


class GatewayControlRecordTests(CharteredFixture):
    """R1: a live v8 run and a dispatching recovery each write their own record."""

    def test_a_live_run_records_its_identity_and_the_targeted_test_group(self):
        result, _, _, captured = self._run_v8([self.PASS])
        self.assertEqual(result["status"], "completed")
        attempt_dir = self.run / "execution" / result["attempt_id"]
        [record] = process_identity.records(attempt_dir)
        self.assertEqual((record["owner_generation"], record["pid"], record["closed"], record["cancel_supported"]),
                         (1, os.getpid(), True, False))
        self.assertEqual([item["kind"] for item in record["groups"]], ["test"],
                         "the default targeted test runs in its own recorded group")
        self.assertIsNone(process_identity.current())


class RecoveryControlRecordTests(RecoveryHarness):
    def test_a_dispatching_recovery_writes_a_record_for_its_new_generation(self):
        with self._kill_once("consume_grant"):
            attempt_id = self._killed(("editor", "verifier"), [self.PASS])
        result = self._recover(attempt_id, ("editor", "verifier"))
        self.assertEqual(result["status"], "completed")
        records = process_identity.records(self.run / "execution" / attempt_id)
        self.assertEqual([(item["owner_generation"], item["closed"]) for item in records], [(1, True), (2, True)])


if __name__ == "__main__":
    unittest.main()
