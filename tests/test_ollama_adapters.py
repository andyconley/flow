from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from execution_contracts import ContractError  # noqa: E402
from ollama_edit_worker import _extract_json_object, source_bundle, validate_and_apply  # noqa: E402
from ollama_manager import call_ollama_manager  # noqa: E402


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

    def test_malformed_or_wrong_model_response_fails_closed(self) -> None:
        with self.assertRaisesRegex(ContractError, "not exact Magentic progress"):
            call_ollama_manager([{"role": "user", "content": "x"}], model="local-model",
                                attempt_id="a", transport=transport("not json"))
        with self.assertRaisesRegex(RuntimeError, "different model"):
            call_ollama_manager([{"role": "user", "content": "x"}], model="local-model",
                                attempt_id="a", transport=transport(json.dumps(PROGRESS), "other"))


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


if __name__ == "__main__":
    unittest.main()
