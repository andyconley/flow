"""Gate 0/1 test oracles for the expertise applicability campaign."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from expertise_feasibility_eval import (
    PROHIBITED_ON_PAUSE, ProtocolError, split_independence, validate_feasibility,
    validate_fixture_manifest, validate_no_v1_reuse, verify_immutable_v1,
)


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / ".flow/runs/agent-expertise-rag-retrieval/evidence/evaluation-v1"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fixture_manifest() -> dict:
    roles = ["support-lead", "product-manager", "quality-reviewer", "lead-developer", "sre", "architect"]
    classes = (["applicable"] * 10 + ["plausible-inapplicable"] * 10 + ["true-no-match"] * 6 + ["integrity"] * 4)
    fixtures = []
    for index, primary in enumerate(classes):
        row = {"id": f"fixture-{index:02d}", "primary_class": primary, "role": roles[index % len(roles)], "query_author": f"author-{index % 5}"}
        if primary == "applicable" and index < 3:
            row["semantic_no_overlap"] = True
            row["query_author"] = f"independent-{index}"
        if primary == "plausible-inapplicable":
            row["plausible_path"] = "admission-rejected" if index < 15 else "controlled-delivery"
        fixtures.append(row)
    return {
        "eligible_roles": roles,
        "fixtures": fixtures,
        "trigger_pairs": [
            {"applicable_id": "fixture-00", "plausible_id": "fixture-10", "roles": ["support-lead", "product-manager"], "one_fact_difference": True},
            {"applicable_id": "fixture-01", "plausible_id": "fixture-11", "roles": ["support-lead", "quality-reviewer"], "one_fact_difference": True},
            {"applicable_id": "fixture-02", "plausible_id": "fixture-12", "roles": ["support-lead", "lead-developer"], "one_fact_difference": True},
            {"applicable_id": "fixture-03", "plausible_id": "fixture-13", "roles": ["support-lead", "sre"], "one_fact_difference": True},
        ],
    }


class ImmutableV1Tests(unittest.TestCase):
    def test_retained_v1_digests_match_the_approved_evidence(self):
        result = verify_immutable_v1(V1)
        self.assertEqual(result["manifest_sha256"], "d2f42382c7c52bc51227596ceb37e58dc5a5f45e77b1edb026441270afa978b0")
        self.assertEqual(result["results_sha256"], "9101f9c2902ffb34b5077f19c126c736e37e6227896e9438a5b3b9e68d2dee57")

    def test_copied_digest_mutation_fails_without_touching_retained_v1(self):
        before = (V1 / "manifest.json").read_bytes()
        with tempfile.TemporaryDirectory() as raw:
            copied = Path(raw)
            (copied / "manifest.json").write_bytes(before)
            (copied / "results.json").write_bytes((V1 / "results.json").read_bytes() + b" ")
            with self.assertRaises(ProtocolError):
                verify_immutable_v1(copied)
        self.assertEqual((V1 / "manifest.json").read_bytes(), before)

    def test_candidate_manifest_cannot_reuse_v1_ids_or_normalized_task_digests(self):
        original = json.loads((V1 / "manifest.json").read_text())
        copied_id = {"fixtures": [{"id": original["fixtures"][0]["id"], "task": "new independent task"}]}
        with self.assertRaisesRegex(ProtocolError, "fixture id"):
            validate_no_v1_reuse(copied_id, original)
        copied_task = {"fixtures": [{"id": "new-id", "task": original["fixtures"][0]["query"]}]}
        with self.assertRaisesRegex(ProtocolError, "task digest"):
            validate_no_v1_reuse(copied_task, original)


class FeasibilityTests(unittest.TestCase):
    def test_paused_result_blocks_all_downstream_campaign_actions(self):
        record = {"state": "paused_for_engineer_decision", "reason": "staffing_gap", "blocking_checks": ["independent_labeler"], "prohibited_next_actions": list(PROHIBITED_ON_PAUSE), "automatic_retrieval": "disabled", "gap": "no independent labeler", "remedies": ["assign a labeler"], "corpus_digest": digest("corpus"), "assignment_digest": digest("assignments")}
        validate_feasibility(record)

    def test_paused_result_that_allows_scoring_fails(self):
        record = {"state": "paused_for_engineer_decision", "reason": "corpus_gap", "blocking_checks": ["slots"], "prohibited_next_actions": ["fixture_authoring"], "automatic_retrieval": "disabled", "gap": "short", "remedies": ["expand corpus"], "corpus_digest": digest("corpus"), "assignment_digest": digest("assignments")}
        with self.assertRaisesRegex(ProtocolError, "prohibit"):
            validate_feasibility(record)

    def test_feasible_result_keeps_automatic_retrieval_disabled(self):
        record = {"state": "feasible", "automatic_retrieval": "disabled", "distinct_task_slots": 60, "eligible_roles": ["a", "b", "c", "d", "e", "f"], "assignments": {"author": "one"}, "environments": [{"os": "macOS"}], "corpus_digest": digest("corpus"), "assignment_digest": digest("assignments")}
        validate_feasibility(record)


class FixtureManifestTests(unittest.TestCase):
    def test_manifest_with_frozen_class_role_and_pair_floors_is_valid(self):
        validate_fixture_manifest(fixture_manifest())

    def test_missing_controlled_delivery_cohort_fails(self):
        manifest = fixture_manifest()
        for row in manifest["fixtures"]:
            if row.get("plausible_path") == "controlled-delivery":
                row["plausible_path"] = "admission-rejected"
        with self.assertRaisesRegex(ProtocolError, "five rejected"):
            validate_fixture_manifest(manifest)

    def test_pair_without_one_fact_attestation_fails(self):
        manifest = fixture_manifest()
        manifest["trigger_pairs"][0]["one_fact_difference"] = False
        with self.assertRaisesRegex(ProtocolError, "one fact"):
            validate_fixture_manifest(manifest)


class SplitIndependenceTests(unittest.TestCase):
    def test_exact_copy_identifier_copy_and_close_paraphrase_are_flagged(self):
        references = [
            {"id": "v1-copy", "task": "Restore the database after the scheduled migration fails", "identifiers": ["METHOD-1"]},
            {"id": "v1-identifier", "task": "Diagnose an unrelated alert", "identifiers": ["METHOD-2"]},
            {"id": "v1-paraphrase", "task": "Restore database service when a planned migration has failed", "identifiers": []},
        ]
        candidate = [
            {"id": "v2-copy", "task": "Restore the database after the scheduled migration fails", "identifiers": []},
            {"id": "v2-identifier", "task": "Perform another operational task", "identifiers": ["METHOD-2"]},
            {"id": "v2-paraphrase", "task": "Restore database service when planned migration failed", "identifiers": []},
        ]
        receipt = split_independence(candidate, references, threshold=0.6)
        categories = {row["candidate_id"]: set(row["categories"]) for row in receipt["flags"]}
        self.assertIn("exact_task", categories["v2-copy"])
        self.assertIn("identifier_overlap", categories["v2-identifier"])
        self.assertIn("lexical_similarity", categories["v2-paraphrase"])

    def test_unrelated_task_remains_unflagged_and_receipt_hides_labels_and_targets(self):
        receipt = split_independence(
            [{"id": "v2-independent", "task": "Prepare an incident communication update", "identifiers": []}],
            [{"id": "v1-other", "task": "Renew a certificate before it expires", "identifiers": []}],
        )
        self.assertEqual(receipt["flags"], [])
        self.assertNotIn("label", json.dumps(receipt))
        self.assertNotIn("target", json.dumps(receipt))


if __name__ == "__main__":
    unittest.main()
