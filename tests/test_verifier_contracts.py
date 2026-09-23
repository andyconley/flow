import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
from verifier_contracts import (  # noqa: E402
    MAX_FINDINGS,
    MAX_FINDING_EVIDENCE_BYTES,
    MAX_FINDING_SUMMARY_BYTES,
    MAX_RAW_OUTPUT_BYTES,
    MAX_SUMMARY_BYTES,
    VerifierContractError,
    evaluate_candidate,
    validate_candidate,
    validate_evaluation,
)


class VerifierContractTests(unittest.TestCase):
    bindings = {
        "action_id": "verifier-1",
        "verifier_input_digest": "a" * 64,
        "diff_digest": "b" * 64,
        "test_evidence_digest": "c" * 64,
    }

    def evaluate(self, candidate: str):
        return evaluate_candidate(raw_output=candidate, **self.bindings)

    @staticmethod
    def candidate(*, decision="pass", summary="ok", findings=None, schema_version=1):
        import json
        return json.dumps({"schema_version": schema_version, "decision": decision, "summary": summary,
                           "findings": [] if findings is None else findings})

    def test_valid_pass_is_bound_and_sealed(self):
        evaluation = self.evaluate('{"schema_version":1,"decision":"pass","summary":"looks good","findings":[]}')
        self.assertEqual(evaluation["disposition"], "valid_pass")
        self.assertEqual(evaluation["reason"], "accepted_pass")
        validate_evaluation(evaluation)

    def test_valid_fail_requires_blocking_finding(self):
        evaluation = self.evaluate('{"schema_version":1,"decision":"fail","summary":"needs repair","findings":[{"severity":"blocking","summary":"test fails","evidence":"test output"}]}')
        self.assertEqual(evaluation["disposition"], "valid_fail")
        validate_evaluation(evaluation)

    def test_malformed_and_contradictory_candidates_are_known_unusable(self):
        cases = (
            ("malformed JSON", "not json", "candidate_json_invalid"),
            ("non-object root", "[]", "candidate_root_invalid"),
            ("extra field", '{"schema_version":1,"decision":"pass","summary":"ok","findings":[],"extra":true}', "candidate_fields_invalid"),
            ("missing field", '{"schema_version":1,"decision":"pass","summary":"ok"}', "candidate_fields_invalid"),
            ("unsupported schema", self.candidate(schema_version=2), "candidate_schema_version_unsupported"),
            ("unsupported decision", self.candidate(decision="maybe"), "candidate_decision_invalid"),
            ("non-string decision", self.candidate(decision=[]), "candidate_decision_invalid"),
            ("non-string severity", self.candidate(decision="fail", findings=[{"severity":{},"summary":"bad","evidence":"x"}]), "candidate_finding_severity_invalid"),
            ("pass blocking", self.candidate(findings=[{"severity":"blocking","summary":"bad","evidence":"x"}]), "pass_contains_blocking_finding"),
            ("fail no blocking", self.candidate(decision="fail"), "fail_requires_blocking_finding"),
        )
        for label, raw, reason in cases:
            with self.subTest(label=label):
                evaluation = self.evaluate(raw)
                self.assertEqual(evaluation["disposition"], "unusable")
                self.assertEqual(evaluation["reason"], reason)
                self.assertIsNone(evaluation["candidate"])
                validate_evaluation(evaluation)

    def test_all_candidate_size_bounds_become_stable_unusable_reasons(self):
        finding = {"severity": "non_blocking", "summary": "s", "evidence": "e"}
        cases = (
            ("raw", "x" * (MAX_RAW_OUTPUT_BYTES + 1), "raw_output_invalid"),
            ("summary", self.candidate(summary="x" * (MAX_SUMMARY_BYTES + 1)), "candidate_summary_invalid"),
            ("findings", self.candidate(findings=[finding] * (MAX_FINDINGS + 1)), "candidate_findings_invalid"),
            ("finding summary", self.candidate(findings=[{**finding, "summary": "x" * (MAX_FINDING_SUMMARY_BYTES + 1)}]), "candidate_finding_summary_invalid"),
            ("finding evidence", self.candidate(findings=[{**finding, "evidence": "x" * (MAX_FINDING_EVIDENCE_BYTES + 1)}]), "candidate_finding_evidence_invalid"),
        )
        for label, raw, reason in cases:
            with self.subTest(label=label):
                evaluation = self.evaluate(raw)
                self.assertEqual((evaluation["disposition"], evaluation["reason"]), ("unusable", reason))

    def test_invalid_binding_digests_and_non_string_raw_output_are_refused(self):
        for field in ("verifier_input_digest", "diff_digest", "test_evidence_digest"):
            with self.subTest(field=field):
                bindings = {**self.bindings, field: "not-a-digest"}
                with self.assertRaisesRegex(VerifierContractError, field):
                    evaluate_candidate(raw_output=self.candidate(), **bindings)
        with self.assertRaisesRegex(VerifierContractError, "raw output must be a string"):
            evaluate_candidate(raw_output=None, **self.bindings)

    def test_closed_candidate_schema_and_digest_tampering_are_rejected(self):
        with self.assertRaisesRegex(VerifierContractError, "fields"):
            validate_candidate({"schema_version": 1, "decision": "pass", "summary": "ok", "findings": [], "extra": True})
        evaluation = self.evaluate('{"schema_version":1,"decision":"pass","summary":"ok","findings":[]}')
        evaluation["diff_digest"] = "d" * 64
        with self.assertRaisesRegex(VerifierContractError, "digest mismatch"):
            validate_evaluation(evaluation)
