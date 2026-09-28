"""Manager identity, request files, call-tagged process groups, checkpoint parents and the recovery actor (ADR 0020).

AC1, AC2, AC4, AC5 and AC6 of step5-operational-handback.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from tests.manager_stub import manager_reply  # noqa: E402

import delivery_gateway  # noqa: E402
import manager_requests  # noqa: E402
import process_identity  # noqa: E402
from execution_contracts import (ContractError, canonical, digest, envelope_digest, expected_manager_call_id,  # noqa: E402
                                 validate_manager_identity, validate_receipt)
from manager_requests import (list_request_files, read_request_file, render_manager_prompt, request_bytes,  # noqa: E402
                              write_request_file)
from tests.test_expansion_gateway import ExpansionGatewayFixture  # noqa: E402

CALL = "a" * 64
MESSAGES = [{"role": "system", "contents": [{"type": "text", "text": "You are the manager."}]},
            {"role": "user", "contents": [{"type": "text", "text": "Gather facts."}]}]


class RequestFileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.attempt = Path(self.temporary.name)

    def test_the_file_is_canonical_owner_only_and_digest_bound(self):
        data = request_bytes(CALL, digest(MESSAGES), MESSAGES)
        path = write_request_file(self.attempt, CALL, data)
        self.assertEqual(path, self.attempt / "manager-requests" / f"{CALL}.json")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        stored = json.loads(path.read_bytes())
        self.assertEqual(set(stored), {"call_id", "messages", "prompt_digest"})
        self.assertEqual(path.read_bytes(), (canonical(stored) + "\n").encode())
        self.assertEqual(digest(stored["messages"]), stored["prompt_digest"])
        self.assertEqual(read_request_file(self.attempt, CALL), data)
        self.assertEqual(list_request_files(self.attempt), ([CALL], [], []))

    def test_a_digest_mismatch_is_refused_before_any_file(self):
        with self.assertRaises(ContractError):
            request_bytes(CALL, "0" * 64, MESSAGES)
        self.assertFalse((self.attempt / "manager-requests").exists())

    def test_identical_bytes_are_reused_and_different_bytes_refused(self):
        data = request_bytes(CALL, digest(MESSAGES), MESSAGES)
        write_request_file(self.attempt, CALL, data)
        write_request_file(self.attempt, CALL, data)  # a replay of a never-sent grant
        other = [{"role": "user", "contents": [{"type": "text", "text": "different"}]}]
        with self.assertRaises(ContractError):
            write_request_file(self.attempt, CALL, request_bytes(CALL, digest(other), other))
        self.assertEqual(read_request_file(self.attempt, CALL), data, "the conflicting write leaves the file unchanged")
        self.assertEqual(list_request_files(self.attempt)[1], [], "no temporary file is left behind")

    def test_a_fault_mid_write_leaves_no_file_at_the_final_path(self):
        data = request_bytes(CALL, digest(MESSAGES), MESSAGES)
        with patch("manager_requests.os.link", side_effect=OSError("disk full")), self.assertRaises(OSError):
            write_request_file(self.attempt, CALL, data)
        self.assertIsNone(read_request_file(self.attempt, CALL))
        self.assertEqual(list_request_files(self.attempt), ([], [], []))

    def test_a_kill_after_the_temporary_file_leaves_only_an_informational_leftover(self):
        directory = self.attempt / "manager-requests"
        directory.mkdir(mode=0o700)
        (directory / f".{CALL}.dead.tmp").write_bytes(b"partial")
        write_request_file(self.attempt, CALL, request_bytes(CALL, digest(MESSAGES), MESSAGES))
        self.assertEqual(list_request_files(self.attempt), ([CALL], [f".{CALL}.dead.tmp"], []))

    def test_a_fifo_at_the_final_path_is_refused_without_blocking(self):
        directory = self.attempt / "manager-requests"
        directory.mkdir(mode=0o700)
        os.mkfifo(directory / f"{CALL}.json")
        with self.assertRaises(ContractError):
            write_request_file(self.attempt, CALL, request_bytes(CALL, digest(MESSAGES), MESSAGES))
        with self.assertRaises(ContractError):
            read_request_file(self.attempt, CALL)
        with self.assertRaises(ContractError):
            read_request_file(self.attempt, "../escape")

    def test_a_group_or_world_readable_directory_is_refused(self):
        directory = self.attempt / "manager-requests"
        directory.mkdir(mode=0o755)
        os.chmod(directory, 0o755)
        with self.assertRaises(ContractError):
            write_request_file(self.attempt, CALL, request_bytes(CALL, digest(MESSAGES), MESSAGES))

    def test_a_symlinked_directory_is_refused(self):
        target = self.attempt / "elsewhere"
        target.mkdir()
        (self.attempt / "manager-requests").symlink_to(target)
        with self.assertRaises(ContractError):
            write_request_file(self.attempt, CALL, request_bytes(CALL, digest(MESSAGES), MESSAGES))

    def test_claude_input_sha256_is_the_rendered_prompt(self):
        sent = {}

        def fake_claude(**kwargs):
            sent.update(kwargs)
            prompt = kwargs["prompt_override"]
            return {"output": "ok", "output_sha256": hashlib.sha256(b"ok").hexdigest(), "usage": None,
                    "session_id": "s", "num_turns": 1, "input_sha256": hashlib.sha256(prompt.encode()).hexdigest()}

        envelope = {"manager": {"provider": "claude", "model": "sonnet"}, "limits": {}}
        with patch("delivery_gateway.call_claude", side_effect=fake_claude):
            result = delivery_gateway._default_manager_adapter({"messages": MESSAGES, "call_id": CALL},
                                                               envelope=envelope, workspace=self.attempt)
        self.assertEqual(result["input_sha256"], hashlib.sha256(render_manager_prompt(MESSAGES).encode()).hexdigest())


class ManagerIdentityContractTests(unittest.TestCase):
    def test_each_provider_requires_its_identity(self):
        validate_manager_identity("claude", {"session_id": "s", "input_sha256": "b" * 64, "num_turns": 1})
        validate_manager_identity("codex", {"thread_id": "t"})
        validate_manager_identity("ollama", {})
        for provider, result in (("claude", {"input_sha256": "b" * 64, "num_turns": 1}),
                                 ("claude", {"session_id": "s", "input_sha256": "nothex", "num_turns": 1}),
                                 ("claude", {"session_id": "s", "input_sha256": "b" * 64, "num_turns": 0}),
                                 ("codex", {"thread_id": ""}), ("codex", {})):
            with self.subTest(provider=provider, result=result), self.assertRaises(ContractError):
                validate_manager_identity(provider, result)


class GatewayCorrelationTests(ExpansionGatewayFixture):
    limits = {"max_concurrent": 1, "max_paid_worker_calls": 1, "max_manager_calls": 4}

    def supervisor(self, sequences=(1, 2)):
        def run(envelope, task, on_manager, on_action, **kwargs):
            for sequence in sequences:
                messages = [{"role": "user", "contents": [{"type": "text", "text": f"facts {sequence}"}]}]
                request = {"schema_version": 1, "attempt_id": envelope["attempt_id"],
                           "envelope_digest": envelope_digest(envelope), "sequence": sequence, "phase": "facts",
                           "manager_round": 1, "prompt_digest": digest(messages)}
                on_manager({**request, "call_id": expected_manager_call_id(request), "messages": messages})
            return {"attempt_id": envelope["attempt_id"]}
        return run

    def attempt_dir(self, result):
        return self.run / "execution" / result["attempt_id"]

    def test_completed_manager_rows_carry_identity_and_request_files(self):
        result = self.execute(self.supervisor(), manager=lambda message, **_: manager_reply(message, "Fixture facts"))
        snapshot = self.ledger().snapshot(result["attempt_id"])
        calls = snapshot["manager_calls"]
        self.assertEqual([item["status"] for item in calls], ["completed", "completed"])
        for item in calls:
            with self.subTest(call=item["call_id"]):
                self.assertTrue(item["result"]["session_id"].startswith("stub-session-"))
                self.assertEqual(item["result"]["num_turns"], 1)
                data = read_request_file(self.attempt_dir(result), item["call_id"])
                stored = json.loads(data)
                self.assertEqual((stored["call_id"], stored["prompt_digest"]), (item["call_id"], item["request"]["prompt_digest"]))
                self.assertEqual(item["result"]["input_sha256"],
                                 hashlib.sha256(render_manager_prompt(stored["messages"]).encode()).hexdigest())
        receipt = json.loads(Path(result["receipt_path"]).read_text())
        envelope = snapshot["envelope"]
        validate_receipt(envelope, receipt)
        broken = json.loads(json.dumps(receipt))
        del broken["manager_calls"][0]["result"]["session_id"]
        with self.assertRaises(ContractError):
            validate_receipt(envelope, broken)

    def test_a_reply_without_identity_stays_uncertain(self):
        result = self.execute(self.supervisor((1,)), manager=lambda message, **_: {"output": "Fixture facts"})
        [call] = self.ledger().snapshot(result["attempt_id"])["manager_calls"]
        self.assertEqual(call["status"], "unknown")

    def test_the_file_is_durable_before_the_grant_is_consumed(self):
        sends = []
        real = delivery_gateway.ExecutionLedger.consume_manager_grant

        def refuse(self_, call_id, grant_id, *, generation):
            raise ContractError("fault between the request file and consume")

        with patch.object(delivery_gateway.ExecutionLedger, "consume_manager_grant", refuse):
            result = self.execute(self.supervisor((1,)),
                                  manager=lambda message, **_: sends.append(1) or manager_reply(message, "x"))
        [call] = self.ledger().snapshot(result["attempt_id"])["manager_calls"]
        self.assertEqual((call["status"], sends), ("allowed", []))
        self.assertIsNotNone(read_request_file(self.attempt_dir(result), call["call_id"]))
        self.assertIs(delivery_gateway.ExecutionLedger.consume_manager_grant, real)


class ProcessGroupRowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.attempt = Path(self.temporary.name) / "attempt"
        self.attempt.mkdir(mode=0o700)

    def child(self):
        process = subprocess.Popen(["sleep", "30"], start_new_session=True)
        self.addCleanup(lambda: (process.kill(), process.wait()))
        return process.pid

    def test_provider_lines_name_their_call_and_others_carry_none(self):
        provider, maf = self.child(), self.child()
        with process_identity.control_scope(self.attempt, 1, attempt_id="a1") as scope:
            scope.register(provider, "provider", CALL)
            scope.register(maf, "maf")
            with self.assertRaises(ValueError):
                scope.register(maf, "maf", CALL)
        lines = [json.loads(line) for line in (self.attempt / "control-g1.groups.jsonl").read_text().splitlines()]
        self.assertEqual([(line["kind"], line["row_id"]) for line in lines], [("provider", CALL), ("maf", None)])

    def test_the_default_adapters_bind_the_row_id_per_call(self):
        seen = []

        def fake_claude(**kwargs):
            if kwargs.get("on_process_group") is not None:  # None outside a v8 control scope
                kwargs["on_process_group"](4242, "provider")
            return {"output": "ok", "session_id": "s", "num_turns": 1, "input_sha256": "c" * 64, "usage": None}

        envelope = {"manager": {"provider": "claude", "model": "sonnet"}, "limits": {}}
        with patch("delivery_gateway.call_claude", side_effect=fake_claude):
            delivery_gateway._default_manager_adapter(
                {"messages": MESSAGES, "call_id": CALL}, envelope=envelope, workspace=self.attempt,
                on_process_group=lambda pgid, kind, row_id=None: seen.append((pgid, kind, row_id)))
            delivery_gateway._default_manager_adapter({"messages": MESSAGES, "call_id": CALL},
                                                      envelope=envelope, workspace=self.attempt)
        self.assertEqual(seen, [(4242, "provider", CALL)])


class CheckpointParentTests(ExpansionGatewayFixture):
    def test_v8_links_record_the_checkpoint_parent(self):
        sends = []
        supervisor, worker = self.worker_plan(sends)

        def with_parent(envelope, task, on_manager, on_action, **kwargs):
            def action(proposal):
                path = Path(envelope["checkpoint_dir"]) / f"{proposal['checkpoint_id']}.json"
                value = json.loads(path.read_text())
                value["previous_checkpoint_id"] = "parent-" + proposal["checkpoint_id"]
                path.write_text(json.dumps(value))
                return on_action(proposal)
            return supervisor(envelope, task, on_manager, action, **kwargs)

        result = self.execute(with_parent, worker=worker)
        links = self.ledger().snapshot(result["attempt_id"])["magentic_checkpoints"]
        self.assertTrue(links)
        for link in links:
            self.assertEqual(link["previous_checkpoint_id"], "parent-" + link["checkpoint_id"])


class RecoveryActorCliTests(unittest.TestCase):
    def test_actor_is_required_and_passed_through(self):
        import flow
        with patch("sys.argv", ["flow", "run", "recover-delivery-lead", "work", "attempt"]), \
             patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            flow.main()
        self.assertNotEqual(raised.exception.code, 0)
        seen = {}

        def fake(work_id, attempt_id, *, actor, root=None):
            seen.update(work_id=work_id, attempt_id=attempt_id, actor=actor)
            return {"attempt_id": attempt_id, "status": "completed", "receipt_path": "r", "reason": ""}

        with patch("flow.recover_delivery", side_effect=fake), patch("sys.stdout"), \
             patch("sys.argv", ["flow", "run", "recover-delivery-lead", "work", "attempt", "--actor", "andy"]):
            code = flow.main()
        self.assertEqual((code, seen["actor"]), (0, "andy"))

    def test_the_hard_coded_default_is_gone(self):
        cli = Path(__file__).resolve().parents[1] / "cli"
        hits = [path.name for path in cli.rglob("*.py") if "codex-assisted-recovery" in path.read_text()]
        self.assertEqual(hits, [])
        with self.assertRaises(ContractError):
            delivery_gateway.recover_delivery("work", "attempt", actor=" ")


if __name__ == "__main__":
    unittest.main()
