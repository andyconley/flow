"""Candidate scoring and fixed-selector proofs for expertise campaigns."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

import expertise_campaign as campaign


TARGET = "flow:entry/support-lead/method"
SECOND = "flow:entry/support-lead/second-method"


def fixture(primary: str, *, path: str | None = None) -> dict:
    if primary == "applicable":
        expected = {"outer_state": "admitted", "cause": "candidates_delivered", "admission_state": "admitted",
                    "candidate_decision": "admitted", "disposition": "applied"}
        acceptable, prohibited = [TARGET], []
    elif primary == "plausible-inapplicable" and path == "controlled-delivery":
        expected = {"outer_state": "admitted", "cause": "candidates_delivered", "admission_state": "admitted",
                    "candidate_decision": "controlled_delivery", "disposition": "ignored"}
        acceptable, prohibited = [TARGET], []
    elif primary == "integrity":
        expected = {"outer_state": "invalid_corpus", "cause": "invalid_canonical_corpus", "admission_state": "not_run",
                    "candidate_decision": "not_run", "disposition": None}
        acceptable, prohibited = [], [TARGET]
    else:
        expected = {"outer_state": "no_match", "cause": "no_candidate_admitted",
                    "admission_state": "no_candidate_admitted", "candidate_decision": "rejected", "disposition": None}
        acceptable, prohibited = [], [TARGET]
    return {
        "id": f"fixture-{primary}-{path}", "primary_class": primary,
        "plausible_path": path, "acceptable_entry_ids": acceptable,
        "prohibited_entry_ids": prohibited, "expected": expected,
    }


def outcome(*, admitted: bool, state: str | None = None, cause: str | None = None,
            candidate_reason: str = "traceable", invalid_corpus: bool = False) -> dict:
    if invalid_corpus:
        return {
            "request_id": "request-a", "role": "support-lead", "state": "invalid_corpus",
            "cause": "invalid_canonical_corpus",
            "eligibility": {"state": "invalid", "eligible_ids": [], "excluded": [], "identity": "invalid"},
            "ranking": {"state": "not_run", "reason": "not_run_invalid_corpus", "provider_calls": 0,
                        "candidates": [], "identity": "not-run"},
            "admission": {"state": "not_run", "strategy": "not-run", "admitted_ids": [],
                          "candidate_decisions": [], "identity": "not-run"},
            "delivery": {"state": "not_run", "reason": "not_run", "delivered_ids": [],
                         "withheld_ids": [], "actual_bytes": 0, "limits": {}, "identity": "not-run", "entries": []},
        }
    outer = state or ("admitted" if admitted else "no_match")
    outer_cause = cause or ("candidates_delivered" if admitted else "no_candidate_admitted")
    return {
        "request_id": "request-a", "role": "support-lead", "state": outer, "cause": outer_cause,
        "eligibility": {"state": "eligible", "eligible_ids": [TARGET], "excluded": [], "identity": "eligibility"},
        "ranking": {"state": "ranked", "reason": "ranked", "provider_calls": 1,
                    "candidates": [{"entry_id": TARGET, "ordinal": 1, "provider_score": 0.9}], "identity": "ranking"},
        "admission": {"state": "admitted" if admitted else "no_candidate_admitted", "strategy": "candidate",
                      "admitted_ids": [TARGET] if admitted else [],
                      "candidate_decisions": [{"entry_id": TARGET, "admitted": admitted, "reason": candidate_reason}],
                      "identity": "admission"},
        "delivery": {"state": "delivered" if admitted else "not_run", "reason": "delivered" if admitted else "not_run",
                     "delivered_ids": [TARGET] if admitted else [], "withheld_ids": [], "actual_bytes": 100,
                     "limits": {}, "identity": "delivery", "entries": [{"private": "entry prose"}] if admitted else []},
    }


def second_delivery() -> dict:
    result = outcome(admitted=True)
    result["eligibility"]["eligible_ids"].append(SECOND)
    result["ranking"]["candidates"].append({"entry_id": SECOND, "ordinal": 2, "provider_score": 0.8})
    result["admission"]["admitted_ids"].append(SECOND)
    result["admission"]["candidate_decisions"].append({"entry_id": SECOND, "admitted": True, "reason": "traceable"})
    result["delivery"]["delivered_ids"].append(SECOND)
    result["delivery"]["entries"].append({"private": "second entry prose"})
    return result


def two_entry_evidence() -> dict:
    return {
        "evaluator_record": {
            "revision": campaign.EVALUATOR_RECORD_REVISION,
            "fixture_id": fixture("applicable")["id"],
            "request_id": "request-a",
            "reviewer_id": "reviewer-test",
            "entries": [
                {"entry_id": TARGET, "disposition": "applied", "reason": "trigger_satisfied", "evidence_codes": ["fact_a"]},
                {"entry_id": SECOND, "disposition": "ignored", "reason": "trigger_absent", "evidence_codes": ["fact_b"]},
            ],
        },
        "behavior_evaluations": [
            {"entry_id": TARGET, "behavior_pass": True, "oracle_digest": "a" * 64, "evidence_digest": "c" * 64},
            {"entry_id": SECOND, "behavior_pass": True, "oracle_digest": "b" * 64, "evidence_digest": "d" * 64},
        ],
    }


class CampaignScoringTests(unittest.TestCase):
    def test_true_no_match_may_rank_role_entries_but_must_not_deliver_them(self):
        row = campaign.score_fixture(fixture("true-no-match"), outcome(admitted=False))
        self.assertTrue(row["passed"])
        self.assertEqual(row["leaked_prohibited_ids"], [])
        self.assertNotIn("entry prose", str(row["safe_result"]))

    def test_admission_rejected_plausible_case_requires_the_named_candidate_rejection(self):
        row = campaign.score_fixture(
            fixture("plausible-inapplicable", path="admission-rejected"),
            outcome(admitted=False),
        )
        self.assertTrue(row["passed"])

    def test_controlled_delivery_remains_incomplete_until_behavior_disposition_exists(self):
        item = fixture("plausible-inapplicable", path="controlled-delivery")
        pending = campaign.score_fixture(item, outcome(admitted=True))
        self.assertFalse(pending["complete"])
        self.assertFalse(pending["passed"])
        observed = campaign.score_fixture(
            item, outcome(admitted=True),
            {"entry_id": TARGET, "disposition": "ignored", "behavior_pass": True},
        )
        self.assertTrue(observed["complete"])
        self.assertTrue(observed["passed"])

    def test_controlled_delivery_miss_fails_without_waiting_for_impossible_disposition(self):
        item = fixture("plausible-inapplicable", path="controlled-delivery")
        row = campaign.score_fixture(item, outcome(admitted=False))
        self.assertTrue(row["complete"])
        self.assertFalse(row["passed"])

    def test_controlled_delivery_accepts_durable_disposition_with_separate_behavior_verdict(self):
        item = fixture("plausible-inapplicable", path="controlled-delivery")
        evidence = {
            "evaluator_record": {
                "revision": campaign.EVALUATOR_RECORD_REVISION,
                "fixture_id": item["id"], "request_id": "request-a", "reviewer_id": "reviewer-test",
                "entries": [{"entry_id": TARGET, "disposition": "ignored", "reason": "trigger_absent", "evidence_codes": []}],
            },
            "behavior_evaluation": {
                "entry_id": TARGET, "behavior_pass": True, "oracle_digest": "a" * 64, "evidence_digest": "c" * 64,
            },
        }
        row = campaign.score_fixture(item, outcome(admitted=True), evidence)
        self.assertTrue(row["passed"])

    def test_applicable_delivery_is_incomplete_without_a_disposition_for_each_delivered_id(self):
        row = campaign.score_fixture(fixture("applicable"), second_delivery())
        self.assertTrue(row["retrieval_pass"])
        self.assertTrue(row["disposition_required"])
        self.assertFalse(row["complete"])
        self.assertFalse(row["passed"])

    def test_integrity_delivery_is_incomplete_without_disposition(self):
        item = fixture("integrity")
        item["expected"] = {"outer_state": "admitted", "cause": "candidates_delivered",
                            "admission_state": "admitted", "disposition": "applied"}
        item["acceptable_entry_ids"] = [TARGET]
        item["prohibited_entry_ids"] = []
        row = campaign.score_fixture(item, outcome(admitted=True))
        self.assertTrue(row["retrieval_pass"])
        self.assertFalse(row["complete"])
        self.assertFalse(row["passed"])

    def test_multi_entry_delivery_rejects_single_compact_disposition(self):
        row = campaign.score_fixture(
            fixture("applicable"), second_delivery(),
            {"entry_id": TARGET, "disposition": "applied", "behavior_pass": True},
        )
        self.assertFalse(row["complete"])
        self.assertFalse(row["passed"])

    def test_multi_entry_delivery_requires_exact_behavior_evidence(self):
        item = fixture("applicable")
        delivered = second_delivery()
        valid = two_entry_evidence()
        passing = campaign.score_fixture(item, delivered, valid)
        self.assertTrue(passing["complete"])
        self.assertTrue(passing["passed"])

        for bad in (
            {**valid, "evaluator_record": {**valid["evaluator_record"], "entries": valid["evaluator_record"]["entries"][:1]}},
            {**valid, "evaluator_record": {**valid["evaluator_record"], "entries": [valid["evaluator_record"]["entries"][0]] * 2}},
            {**valid, "behavior_evaluations": valid["behavior_evaluations"][:1]},
            {**valid, "behavior_evaluations": [valid["behavior_evaluations"][0]] * 2},
        ):
            with self.subTest(bad=bad):
                row = campaign.score_fixture(item, delivered, bad)
                self.assertFalse(row["complete"])
                self.assertFalse(row["passed"])

        contradicted = two_entry_evidence()
        contradicted["behavior_evaluations"][1]["behavior_pass"] = False
        row = campaign.score_fixture(item, delivered, contradicted)
        self.assertTrue(row["complete"])
        self.assertFalse(row["passed"])

    def test_behavior_verdict_must_bind_frozen_oracle(self):
        item = fixture("applicable")
        item["behavior_oracle"] = {"must_include": ["compare options"], "must_avoid": ["defer blindly"]}
        evidence = two_entry_evidence()
        mismatch = campaign.score_fixture(item, second_delivery(), evidence)
        self.assertFalse(mismatch["complete"])
        self.assertFalse(mismatch["passed"])
        bound = campaign.digest(item["behavior_oracle"])
        for verdict in evidence["behavior_evaluations"]:
            verdict["oracle_digest"] = bound
        passing = campaign.score_fixture(item, second_delivery(), evidence)
        self.assertTrue(passing["complete"])
        self.assertTrue(passing["passed"])

    def test_campaign_evaluator_record_rejects_missing_or_inconsistent_fields(self):
        import copy
        item = fixture("applicable")
        item["behavior_oracle"] = {"must_include": ["decide"], "must_avoid": ["defer"]}
        valid = two_entry_evidence()
        for verdict in valid["behavior_evaluations"]:
            verdict["oracle_digest"] = campaign.digest(item["behavior_oracle"])
        mutations = []
        for key in ("revision", "fixture_id", "request_id", "reviewer_id"):
            changed = copy.deepcopy(valid)
            del changed["evaluator_record"][key]
            mutations.append(changed)
        for field, value in (("reason", "trigger_absent"), ("evidence_codes", ["bad-code"]),
                             ("disposition", "ignored")):
            changed = copy.deepcopy(valid)
            changed["evaluator_record"]["entries"][0][field] = value
            mutations.append(changed)
        changed = copy.deepcopy(valid)
        del changed["behavior_evaluations"][0]["evidence_digest"]
        mutations.append(changed)
        for changed in mutations:
            with self.subTest(changed=changed):
                row = campaign.score_fixture(item, second_delivery(), changed)
                self.assertFalse(row["complete"])
                self.assertFalse(row["passed"])
        passing = campaign.score_fixture(item, second_delivery(), valid)
        self.assertTrue(passing["complete"])
        self.assertTrue(passing["passed"])

    def test_scorecard_cannot_survive_pending_applicable_disposition(self):
        item = fixture("applicable")
        score = campaign.score_candidate(
            {"split": "evaluation-v2", "fixtures": [item]},
            "similarity:0.7", lambda _fixture: outcome(admitted=True),
        )
        self.assertFalse(score["complete"])
        self.assertFalse(score["survives_hard_rules"])
        self.assertEqual(score["score"]["applicable_admission_recall"], 1.0)

    def test_selector_prioritizes_admission_recall_over_behavior_disposition(self):
        import copy
        first = fixture("applicable")
        second = copy.deepcopy(first)
        second["id"] = "fixture-applicable-second"
        manifest = {"split": "calibration-v1", "fixtures": [first, second]}
        evidence = {}
        for item in (first, second):
            record = two_entry_evidence()
            record["evaluator_record"]["fixture_id"] = item["id"]
            evidence[item["id"]] = record
        trigger_evidence = copy.deepcopy(evidence)
        trigger_evidence[second["id"]]["behavior_evaluations"][0]["behavior_pass"] = False
        trigger = campaign.score_candidate(
            manifest, "trigger-rules", lambda _fixture: second_delivery(), trigger_evidence,
        )
        similarity = campaign.score_candidate(
            manifest, "similarity:0.7",
            lambda item: second_delivery() if item["id"] == first["id"] else outcome(admitted=False),
            evidence,
        )
        self.assertTrue(trigger["survives_hard_rules"])
        self.assertTrue(similarity["survives_hard_rules"])
        self.assertEqual(trigger["score"]["applicable_admission_recall"], 1.0)
        self.assertEqual(similarity["score"]["applicable_admission_recall"], 0.5)
        self.assertEqual(campaign.select_candidate([similarity, trigger])["winner"], "trigger-rules")

    def test_integrity_invalid_graph_passes_only_as_invalid_corpus_before_ranking(self):
        row = campaign.score_fixture(fixture("integrity"), outcome(admitted=False, invalid_corpus=True))
        self.assertTrue(row["passed"])
        wrong = campaign.score_fixture(fixture("integrity"), outcome(admitted=False))
        self.assertFalse(wrong["passed"])

    def test_expected_invalid_graph_is_not_misclassified_as_a_degraded_hard_failure(self):
        item = fixture("integrity")
        score = campaign.score_candidate(
            {"split": "calibration-v1", "fixtures": [item]}, "similarity:0.7",
            lambda _fixture: outcome(admitted=False, invalid_corpus=True),
        )
        self.assertTrue(score["survives_hard_rules"])
        self.assertEqual(score["hard_failures"], [])

    def test_untraceable_candidate_decision_is_a_hard_failure(self):
        item = fixture("applicable")
        manifest = {"split": "calibration-v1", "fixtures": [item]}
        score = campaign.score_candidate(
            manifest, "similarity:0.7", lambda _fixture: outcome(admitted=True, candidate_reason="")
        )
        self.assertFalse(score["survives_hard_rules"])
        self.assertIn("untraceable_decision", " ".join(score["hard_failures"]))

    def test_integrity_ranking_leak_is_hard_failure_even_without_delivery(self):
        item = fixture("integrity")
        leaked = outcome(admitted=False)
        leaked["state"] = "unavailable"
        leaked["cause"] = "projection_missing"
        leaked["ranking"] = {
            "state": "unavailable", "reason": "projection_missing", "provider_calls": 0,
            "candidates": [{"entry_id": TARGET, "ordinal": 1, "provider_score": 0.9}], "identity": "ranking",
        }
        leaked["admission"] = {"state": "not_run", "strategy": "not-run", "admitted_ids": [],
                                "candidate_decisions": [], "identity": "not-run"}
        score = campaign.score_candidate({"split": "calibration-v1", "fixtures": [item]}, "trigger-rules", lambda _fixture: leaked)
        self.assertFalse(score["survives_hard_rules"])
        self.assertIn("integrity_leak", " ".join(score["hard_failures"]))

    def test_exact_selector_tie_favors_similarity_and_reports_thin_margin(self):
        base = {
            "survives_hard_rules": True, "result_digest": "a",
            "score": {"applicable_admission_recall": 1.0, "applicable_passed": 10,
                      "plausible_path_passed": 10, "delivery_displacement": 5},
        }
        trigger = dict(base, candidate_id="trigger-rules", result_digest="trigger")
        similarity = dict(base, candidate_id="similarity:0.7", result_digest="similarity")
        selected = campaign.select_candidate([trigger, similarity])
        self.assertEqual(selected["winner"], "similarity:0.7")
        self.assertTrue(selected["thin_margin"])

    def test_selector_uses_frozen_displacement_before_similarity_tie_break(self):
        base = {
            "survives_hard_rules": True,
            "score": {"applicable_admission_recall": 1.0, "applicable_passed": 10,
                      "plausible_path_passed": 10, "delivery_displacement": 5},
        }
        low_displacement = dict(base, candidate_id="trigger-rules", result_digest="trigger",
                                score=dict(base["score"], delivery_displacement=4))
        similarity = dict(base, candidate_id="similarity:0.7", result_digest="similarity")
        selected = campaign.select_candidate([similarity, low_displacement])
        self.assertEqual(selected["winner"], "trigger-rules")

    def test_repeatability_ignores_request_ids_without_mutating_evidence(self):
        left = campaign.score_candidate(
            {"split": "calibration-v1", "fixtures": [fixture("applicable")]},
            "similarity:0.7", lambda _fixture: outcome(admitted=True),
        )
        right = campaign.json_clone(left)
        right["rows"][0]["safe_result"]["request_id"] = "request-b"
        original = left["rows"][0]["safe_result"]["request_id"]
        self.assertEqual(campaign.repeatable(left, right)["state"], "identical")
        self.assertEqual(left["rows"][0]["safe_result"]["request_id"], original)


if __name__ == "__main__":
    unittest.main()
