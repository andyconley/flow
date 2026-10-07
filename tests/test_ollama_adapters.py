from __future__ import annotations

import copy
import base64
import hashlib
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from execution_contracts import ContractError  # noqa: E402
from ollama_edit_worker import _extract_json_object, source_bundle, validate_and_apply  # noqa: E402
from ollama_manager import MANAGER_RESPONSE_SCHEMA, call_ollama_manager  # noqa: E402


PROGRESS = {
    "is_request_satisfied": {"answer": False},
    "is_in_loop": {"answer": False},
    "is_progress_being_made": {"answer": True},
    "next_speaker": {"answer": "lead-developer", "reason": "implementation remains"},
    "instruction_or_question": {"answer": "Implement the scoped change."},
}


def transport(content: str, model: str = "local-model"):
    return lambda _envelope: {"model": model, "message": {"content": content}}


class OllamaManagerTests(unittest.TestCase):
    def test_exact_progress_is_accepted_and_canonicalized(self) -> None:
        result = call_ollama_manager(
            [{"role": "user", "content": "coordinate"}], model="local-model",
            attempt_id="a", transport=transport(json.dumps(PROGRESS)),
        )
        self.assertEqual(result["manager_response"], PROGRESS)
        self.assertEqual(json.loads(result["output"]), PROGRESS)

    @patch("ollama_manager.call_local")
    def test_live_call_constrains_ollama_to_exact_progress_schema(self, local) -> None:
        local.return_value = {"output": json.dumps(PROGRESS)}
        call_ollama_manager([{"role": "user", "content": "coordinate"}],
                            model="local-model", attempt_id="a")
        self.assertEqual(local.call_args.kwargs["response_schema"], MANAGER_RESPONSE_SCHEMA)
        self.assertFalse(MANAGER_RESPONSE_SCHEMA["additionalProperties"])
        self.assertEqual(
            set(MANAGER_RESPONSE_SCHEMA["required"]),
            {"is_request_satisfied", "is_in_loop", "is_progress_being_made",
             "next_speaker", "instruction_or_question"},
        )

    @patch("ollama_manager.call_local")
    def test_live_call_constrains_next_speaker_to_flow_frontier(self, local) -> None:
        local.return_value = {"output": json.dumps(PROGRESS)}
        call_ollama_manager([{"role": "user", "content": "coordinate"}],
                            model="local-model", attempt_id="a",
                            allowed_speakers=["logical-editor"])
        schema = local.call_args.kwargs["response_schema"]
        self.assertEqual(schema["properties"]["next_speaker"]["properties"]["answer"]["enum"],
                         ["logical-editor"])
        self.assertNotIn("enum", MANAGER_RESPONSE_SCHEMA["properties"]["next_speaker"]["properties"]["answer"])

    @patch("ollama_manager.call_local")
    def test_native_progress_forwards_actual_roles_with_same_schema(self, local) -> None:
        from runner_limits import resolve_local_agent_budget
        messages=[{'role':'user','content':'task'}, {'role':'assistant','content':'observed result'},
                  {'role':'user','content':'current stock progress request'}]
        local.return_value={'output':json.dumps(PROGRESS)}
        call_ollama_manager(messages, model='local-model', attempt_id='a',
                            native_messages=messages, local_agent_profile=resolve_local_agent_budget())
        self.assertEqual(local.call_args.kwargs['chat_messages'],messages)
        self.assertEqual(local.call_args.kwargs['response_schema'],MANAGER_RESPONSE_SCHEMA)

    @patch("ollama_manager.call_local")
    def test_native_nonprogress_does_not_inject_progress_instructions(self, local) -> None:
        from runner_limits import resolve_local_agent_budget
        messages=[{'role':'user','content':'Final stock phase request'}]
        local.return_value={'output':'Actual final narrative'}
        result=call_ollama_manager(messages,model='local-model',attempt_id='a', phase='final',
            native_messages=messages, local_agent_profile=resolve_local_agent_budget())
        self.assertEqual(result['output'],'Actual final narrative')
        self.assertIsNone(local.call_args.kwargs['response_schema'])
        self.assertNotIn('Return exactly one JSON',local.call_args.args[0]['instructions'])

    def test_malformed_or_wrong_model_response_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "not exact Magentic progress"):
            call_ollama_manager([{"role": "user", "content": "x"}], model="local-model",
                                attempt_id="a", transport=transport("not json"))
        with self.assertRaisesRegex(RuntimeError, "different model"):
            call_ollama_manager([{"role": "user", "content": "x"}], model="local-model",
                                attempt_id="a", transport=transport(json.dumps(PROGRESS), "other"))

    def test_observed_invalid_progress_can_be_preserved_for_durable_failure(self) -> None:
        result = call_ollama_manager(
            [{"role": "user", "content": "x"}], model="local-model", attempt_id="a",
            transport=transport("not json"), preserve_observed_invalid=True,
        )
        self.assertEqual(result["output"], "not json")
        self.assertIsNone(result["manager_response"])
        self.assertTrue(result["observed_invalid"])


class OllamaEditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "src").mkdir()
        (self.root / "src" / "value.txt").write_text("before\n")
        self.bundle = source_bundle(self.root, ["src/value.txt"])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def proposal(self, *, path: str = "src/value.txt", base: str | None = None,
                 content: str = "after\n", model: str = "local-model") -> dict:
        return {
            "schema_version": 1,
            "model": model,
            "bundle_digest": self.bundle["bundle_digest"],
            "edits": [{
                "path": path,
                "base_sha256": base or self.bundle["files"][0]["sha256"],
                "content": content,
            }],
        }

    def apply(self, proposal: dict) -> dict:
        return validate_and_apply(
            self.root, self.bundle, proposal,
            write_scopes=["src"], expected_model="local-model",
        )

    def test_valid_digest_bound_edit_is_applied_by_flow(self) -> None:
        result = self.apply(self.proposal())
        self.assertEqual((self.root / "src/value.txt").read_text(), "after\n")
        self.assertEqual(result["changed_paths"], ["src/value.txt"])
        self.assertEqual(result["result_digests"]["src/value.txt"],
                         hashlib.sha256(b"after\n").hexdigest())

    def test_hostile_paths_stale_hash_model_and_bundle_fail_without_mutation(self) -> None:
        cases = []
        outside = self.root / "outside.txt"
        outside.write_text("outside\n")
        cases.append(self.proposal(path="../outside.txt"))
        cases.append(self.proposal(base="0" * 64))
        cases.append(self.proposal(model="other"))
        wrong_bundle = self.proposal()
        wrong_bundle["bundle_digest"] = "0" * 64
        cases.append(wrong_bundle)
        for proposal in cases:
            with self.subTest(proposal=proposal):
                before = (self.root / "src/value.txt").read_bytes()
                with self.assertRaises(ContractError):
                    self.apply(copy.deepcopy(proposal))
                self.assertEqual((self.root / "src/value.txt").read_bytes(), before)
                self.assertEqual(outside.read_text(), "outside\n")

    def test_symlink_target_is_refused_without_touching_referent(self) -> None:
        referent = self.root / "referent.txt"
        referent.write_text("secret\n")
        link = self.root / "src" / "link.txt"
        link.symlink_to(referent)
        with self.assertRaisesRegex(ContractError, "symlink"):
            source_bundle(self.root, ["src/link.txt"])
        self.assertEqual(referent.read_text(), "secret\n")

    def test_surrounding_text_is_not_treated_as_a_structured_proposal(self) -> None:
        with self.assertRaisesRegex(ContractError, "exactly one JSON object"):
            _extract_json_object('commentary {"schema_version": 1}')
        with self.assertRaisesRegex(ContractError, "exactly one JSON object"):
            _extract_json_object('{"schema_version": 1} trailing')

    def test_multi_file_validation_happens_before_any_workspace_mutation(self) -> None:
        second = self.root / "src" / "second.txt"
        second.write_text("second-before\n")
        bundle = source_bundle(self.root, ["src/value.txt", "src/second.txt"])
        proposal = {
            "schema_version": 1,
            "model": "local-model",
            "bundle_digest": bundle["bundle_digest"],
            "edits": [
                {"path": "src/value.txt", "base_sha256": bundle["files"][1]["sha256"],
                 "content": "after\n"},
                {"path": "src/second.txt", "base_sha256": "0" * 64,
                 "content": "second-after\n"},
            ],
        }
        with self.assertRaisesRegex(ContractError, "stale"):
            validate_and_apply(self.root, bundle, proposal, write_scopes=["src"],
                               expected_model="local-model")
        self.assertEqual((self.root / "src" / "value.txt").read_text(), "before\n")
        self.assertEqual(second.read_text(), "second-before\n")

    def test_durable_journal_is_recovered_before_next_edit(self) -> None:
        target = self.root / "src" / "value.txt"
        target.write_text("partially-applied\n")
        journal = {
            "schema_version": 1, "state": "prepared",
            "files": [{"path": "src/value.txt",
                       "old_base64": base64.b64encode(b"before\n").decode("ascii")}],
        }
        journal_path = Path(tempfile.gettempdir()) / (
            "flow-ollama-edit-" + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest() + ".journal")
        journal_path.write_text(json.dumps(journal))
        result = self.apply(self.proposal())
        self.assertEqual(target.read_text(), "after\n")
        self.assertEqual(result["changed_paths"], ["src/value.txt"])
        self.assertFalse(journal_path.exists())

    def test_recovery_journal_cannot_escape_current_bundle_and_scope(self) -> None:
        protected = self.root / "protected.txt"
        protected.write_text("protected\n")
        journal_path = Path(tempfile.gettempdir()) / (
            "flow-ollama-edit-" + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest() + ".journal")
        journal_path.write_text(json.dumps({
            "schema_version": 1, "state": "prepared",
            "files": [{"path": "protected.txt",
                       "old_base64": base64.b64encode(b"forged\n").decode("ascii")}],
        }))
        self.addCleanup(journal_path.unlink, missing_ok=True)
        with self.assertRaisesRegex(ContractError, "exceeds the current grant"):
            self.apply(self.proposal())
        self.assertEqual(protected.read_text(), "protected\n")

    def test_parent_swap_during_commit_rolls_back_through_held_directory(self) -> None:
        original_parent = self.root / "src-original"
        escaped_parent = self.root / "escaped"
        real_replace = __import__("os").replace
        swapped = False

        def swap_then_replace(source, destination, *args, **kwargs):
            nonlocal swapped
            if not swapped and kwargs.get("src_dir_fd") is not None:
                swapped = True
                (self.root / "src").rename(original_parent)
                escaped_parent.mkdir()
                (self.root / "src").symlink_to(escaped_parent, target_is_directory=True)
            return real_replace(source, destination, *args, **kwargs)

        with patch("ollama_edit_worker.os.replace", side_effect=swap_then_replace):
            with self.assertRaisesRegex(ContractError, "parent changed"):
                self.apply(self.proposal())
        self.assertEqual((original_parent / "value.txt").read_text(), "before\n")
        self.assertFalse((escaped_parent / "value.txt").exists())


if __name__ == "__main__":
    unittest.main()
