"""Verifier system instructions and constrained-decoding schema for local v8 verifiers."""

import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from delivery_gateway import _default_worker_adapter  # noqa: E402
from execution_gateway import _effective_specialist_for  # noqa: E402
from verifier_contracts import (MAX_FINDINGS, MAX_SUMMARY_BYTES, VALID_DECISIONS, VALID_SEVERITIES,  # noqa: E402
                                VERIFIER_CONTRACT_INSTRUCTION, VERIFIER_OUTPUT_SCHEMA, VERIFIER_SYSTEM_PREAMBLE,
                                evaluate_candidate, verifier_instructions)

AGENTS = Path(__file__).resolve().parents[1] / "scaffolds" / "default" / "agents"
ROLE = ("# Reviewer\n\n## Review Framework\n\nJudge correctness.\n\n## Output Format\n\n```md\n## Review Summary\n"
        "**Verdict:** APPROVE\n### Critical Issues\n```\n\n## Rules\n\n1. Be specific.\n")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class VerifierInstructionTests(unittest.TestCase):
    def test_output_format_section_and_its_fenced_template_are_removed(self):
        text = verifier_instructions(ROLE)
        self.assertTrue(text.startswith(VERIFIER_SYSTEM_PREAMBLE))
        self.assertTrue(text.endswith(VERIFIER_CONTRACT_INSTRUCTION))
        for gone in ("## Output Format", "## Review Summary", "**Verdict:**", "### Critical Issues"):
            self.assertNotIn(gone, text)
        for kept in ("## Review Framework", "Judge correctness.", "## Rules", "1. Be specific."):
            self.assertIn(kept, text)

    def test_a_role_without_an_output_format_is_kept_whole(self):
        role = "# Role\n\n## Rules\n\nBe careful.\n"
        self.assertEqual(verifier_instructions(role), VERIFIER_SYSTEM_PREAMBLE + role.rstrip() + VERIFIER_CONTRACT_INSTRUCTION)

    def test_every_shipped_role_loses_only_its_output_format(self):
        roles = sorted(path.stem for path in AGENTS.glob("*.md"))
        self.assertIn("quality-reviewer", roles)
        for role in roles:
            with self.subTest(role=role):
                body = _effective_specialist_for(role)
                text = verifier_instructions(body)
                self.assertNotIn("\n## Output Format", text)
                sections = [line for line in body.splitlines() if line.startswith("## ") and line != "## Output Format"]
                kept = [line for line in text.splitlines() if line.startswith("## ")]
                # Fenced "## " lines inside the removed template are gone; every real section survives.
                self.assertTrue(set(kept) <= set(sections))
                if "\n## Rules\n" in body:
                    self.assertIn("## Rules", kept)
                self.assertEqual(verifier_instructions(body), text)


class VerifierSchemaTests(unittest.TestCase):
    def test_schema_mirrors_the_contract_constants(self):
        props = VERIFIER_OUTPUT_SCHEMA["properties"]
        self.assertEqual(set(VERIFIER_OUTPUT_SCHEMA["required"]), set(props))
        self.assertEqual(set(props["decision"]["enum"]), VALID_DECISIONS)
        self.assertEqual(props["findings"]["maxItems"], MAX_FINDINGS)
        self.assertEqual(set(props["findings"]["items"]["properties"]["severity"]["enum"]), VALID_SEVERITIES)
        self.assertIs(VERIFIER_OUTPUT_SCHEMA["additionalProperties"], False)
        json.dumps(VERIFIER_OUTPUT_SCHEMA)

    def evaluate(self, candidate):
        return evaluate_candidate(action_id="a", verifier_input_digest=sha("i"), raw_output=json.dumps(candidate),
                                  diff_digest=sha("d"), test_evidence_digest=sha("t"))

    def test_a_schema_shaped_reply_is_judged_by_the_evaluator_not_the_schema(self):
        finding = {"severity": "blocking", "summary": "wrong string", "evidence": "returns Goodbye"}
        self.assertEqual(self.evaluate({"schema_version": 1, "decision": "fail", "summary": "s", "findings": [finding]})["disposition"],
                         "valid_fail")
        # Each of these satisfies the schema but breaks a contract rule it cannot express.
        for candidate in ({"schema_version": 1, "decision": "pass", "summary": "x" * (MAX_SUMMARY_BYTES + 1), "findings": []},
                          {"schema_version": 1, "decision": "pass", "summary": "s", "findings": [finding]},
                          {"schema_version": 1, "decision": "fail", "summary": "s", "findings": []}):
            with self.subTest(candidate=candidate["decision"]):
                self.assertEqual(self.evaluate(candidate)["disposition"], "unusable")


class VerifierDispatchTests(unittest.TestCase):
    def dispatch(self, instance_id, protocol=8):
        roster = [{"assignment_id": name, "instance_id": name, "role": "quality-reviewer", "provider": "ollama",
                   "model": "m", "instructions": ROLE, "definition_digest": "sealed", "capabilities": ["read"]}
                  for name in ("producer", "verifier")]
        envelope = {"execution_protocol_version": protocol, "attempt_id": "att", "roster": roster, "limits": {},
                    "job_contract": {"verifier_instance_ids": ["verifier"]}}
        action = {"assignment_id": instance_id, "instance_id": instance_id, "provider": "ollama", "task": "t",
                  "provider_task": "pt", "action_id": "act"}
        with patch("delivery_gateway.call_local", return_value={"ok": True}) as call:
            _default_worker_adapter(action, envelope=envelope, workspace=Path("."))
        return call.call_args

    def test_a_v8_verifier_is_sent_derived_instructions_with_the_sealed_body_untouched(self):
        args = self.dispatch("verifier")
        self.assertEqual(args.args[0]["instructions"], verifier_instructions(ROLE))
        self.assertEqual(args.args[0]["definition_digest"], "sealed")
        self.assertIs(args.kwargs["structured_verifier"], True)

    def test_a_producer_and_a_pre_v8_verifier_keep_the_role_body(self):
        for instance_id, protocol in (("producer", 8), ("verifier", 7)):
            with self.subTest(instance_id=instance_id, protocol=protocol):
                args = self.dispatch(instance_id, protocol)
                self.assertEqual(args.args[0]["instructions"], ROLE)
                self.assertIs(args.kwargs["structured_verifier"], False)


if __name__ == "__main__":
    unittest.main()
