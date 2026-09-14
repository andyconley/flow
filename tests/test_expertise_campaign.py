"""Candidate scoring and fixed-selector proofs for expertise campaigns."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

import expertise_campaign as campaign


TARGET = "flow:entry/support-lead/method"


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
            "disposition_record": {
                "state": "observed",
                "entries": [{"entry_id": TARGET, "disposition": "ignored"}],
            },
            "behavior_evaluation": {
                "entry_id": TARGET, "behavior_pass": True, "oracle_digest": "a" * 64,
            },
        }
        row = campaign.score_fixture(item, outcome(admitted=True), evidence)
        self.assertTrue(row["passed"])

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
