"""Production Gate 1 tests for feasibility and fixture-preparation commands."""

from __future__ import annotations

import contextlib
import copy
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

import expertise_commands as commands
import expertise_campaign as campaign
import expertise_service as service
import expertise
from expertise_model import (
    ExpertiseContractError, SCHEMA_VERSION, digest, identity, validate_admission_decision,
    validate_admission_input, validate_delivery_result, validate_disposition_record,
    validate_identity, validate_outcome, validate_trigger_rule,
)


class HeldoutDispositionFinalizationTests(unittest.TestCase):
    def test_pending_applicable_delivery_cannot_qualify_or_disappear_from_decision(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            target = "entry-a"
            fixture = {
                "id": "applicable-one", "primary_class": "applicable",
                "acceptable_entry_ids": [target], "prohibited_entry_ids": [],
                "expected": {"disposition": "applied"},
            }
            manifest = {"split": "evaluation-v2", "fixtures": [fixture],
                        "selected_configuration_digest": "selected-v1"}
            manifest_path = run / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            outcome = {
                "request_id": "request-1", "role": "support-lead", "state": "admitted",
                "cause": "candidates_delivered",
                "eligibility": {"state": "eligible", "eligible_ids": [target], "excluded": [], "identity": "eligibility"},
                "ranking": {"state": "ranked", "reason": "ranked", "provider_calls": 1,
                            "candidates": [{"entry_id": target, "ordinal": 1, "provider_score": 0.9}], "identity": "ranking"},
                "admission": {"state": "admitted", "strategy": "similarity", "admitted_ids": [target],
                              "candidate_decisions": [{"entry_id": target, "admitted": True, "reason": "similarity_threshold_met"}],
                              "identity": "admission"},
                "delivery": {"state": "delivered", "reason": "delivered", "delivered_ids": [target],
                             "withheld_ids": [], "actual_bytes": 100, "limits": {}, "identity": "delivery",
                             "entries": [{"@id": target}]},
            }
            retained = campaign.score_candidate(manifest, "similarity:0.70", lambda _fixture: outcome)
            scoring = run / "evidence" / "evaluation-v2" / "scoring"
            scoring.mkdir(parents=True)
            (scoring / "retrieval-results.json").write_text(json.dumps({
                "manifest_digest": digest(manifest), "freeze_receipt_digest": "freeze-v1",
                "candidate_id": "similarity:0.70",
                "repeats": [{"repeat": index, "scorecard": retained} for index in (1, 2)],
            }))
            with (
                patch.object(commands, "verify_campaign_freeze", return_value={"state": "valid", "freeze_receipt_digest": "freeze-v1"}),
                patch.object(commands, "_frozen_paths", return_value=(manifest_path, run / "receipt.json")),
                patch.object(commands, "_heldout_strategy", return_value=("similarity:0.70", None, {})),
                patch.object(commands, "_environment_evidence", return_value={"state": "passed"}),
            ):
                result = commands.finalize_heldout(run)
            decision = result["decision"]
            self.assertEqual(decision["state"], "stop")
            self.assertFalse(decision["all_fixture_oracles_passed"])
            self.assertEqual(decision["missing_disposition_fixture_ids"], [fixture["id"]])


ROLES = ("support-lead", "product-manager", "quality-reviewer", "lead-developer", "sre", "architect")


def framework_at(root: Path) -> Path:
    framework = root / "framework"
    expertise = framework / "expertise"
    expertise.mkdir(parents=True)
    for role in ROLES:
        (expertise / f"{role}.jsonld").write_text(json.dumps({"@graph": [{
            "@id": f"flow:entry/{role}/method", "audience": {"audienceType": role},
        }]}))
    return framework


def feasible_plan(entry_ids: list[str]) -> dict:
    classes = (["applicable"] * 10 + ["plausible-inapplicable"] * 10 + ["true-no-match"] * 6 + ["integrity"] * 4)
    slots = []
    for split in commands.SPLITS:
        author_ids = [f"{split}-author-{number}" for number in range(3)]
        labeler = f"{split}-labeler"
        reviewer = f"{split}-reviewer"
        for index, primary in enumerate(classes):
            role = ROLES[index % len(ROLES)]
            if 10 <= index < 14:
                role = ROLES[index - 10]
            slot = {
                "id": f"{split}-{index:02d}", "split": split, "role": role,
                "primary_class": primary,
                "target_entry_id": entry_ids[index % len(entry_ids)],
                "query_author": author_ids[index % len(author_ids)],
                "labeler": labeler, "reviewer": reviewer,
            }
            if primary == "plausible-inapplicable":
                slot["plausible_path"] = "admission-rejected" if index < 15 else "controlled-delivery"
            if primary == "applicable" and index < 3:
                slot["semantic_no_overlap"] = True
            if index < 4:
                slot.update({"trigger_pair": f"{split}-pair-{index}", "one_fact_difference": True})
            if 10 <= index < 14:
                slot.update({"trigger_pair": f"{split}-pair-{index - 10}", "one_fact_difference": True})
            slot["task_slot_digest"] = commands.digest(slot)
            slots.append(slot)
    staffing = {}
    for split in commands.SPLITS:
        staffing[split] = {
            "query_authors": [f"{split}-author-{number}" for number in range(3)],
            "labelers": [f"{split}-labeler"], "freeze_reviewers": [f"{split}-reviewer"], "status": "available",
            "evidence": f"{split}-assignment", "calibration_score_access": False,
        }
    environments = [
        {"id": environment, "status": "available", "runner": f"runner:{environment}",
         "validation_command": "flow expertise evaluate held-out", "availability_evidence": "reserved"}
        for environment in sorted(commands.REQUIRED_ENVIRONMENTS)
    ]
    return {"schema_version": SCHEMA_VERSION, "staffing": staffing, "slots": slots, "environments": environments}


def fixture_manifest(split: str, entry_ids: list[str]) -> dict:
    plan = feasible_plan(entry_ids)
    rows = [row for row in plan["slots"] if row["split"] == split]
    integrity_kinds = iter(("role_mismatch", "lifecycle_not_current", "lifecycle_withdrawn", "invalid_graph"))
    for row in rows:
        task = f"synthetic protocol fixture {row['id']} with trigger evidence"
        start = task.index("trigger evidence")
        primary = row["primary_class"]
        path = row.get("plausible_path")
        integrity_kind = next(integrity_kinds) if primary == "integrity" else None
        if primary == "integrity" and integrity_kind == "invalid_graph":
            expected = {"outer_state": "invalid_corpus", "cause": "invalid_canonical_corpus",
                        "admission_state": "not_run", "candidate_decision": "not_run", "disposition": None}
        elif primary in {"applicable", "integrity"}:
            expected = {"outer_state": "admitted", "cause": "candidates_delivered", "admission_state": "admitted",
                        "candidate_decision": "admitted", "disposition": "applied"}
        elif primary == "plausible-inapplicable" and path == "controlled-delivery":
            expected = {"outer_state": "admitted", "cause": "candidates_delivered", "admission_state": "admitted",
                        "candidate_decision": "controlled_delivery", "disposition": "ignored"}
        else:
            expected = {"outer_state": "no_match", "cause": "no_candidate_admitted",
                        "admission_state": "no_candidate_admitted", "candidate_decision": "rejected", "disposition": None}
        row.update({
            "task": task,
            "acceptable_entry_ids": [entry_ids[0]], "prohibited_entry_ids": [],
            "query_author": f"author-{row['id']}", "labeler": f"labeler-{row['id']}",
            "reviewer": f"reviewer-{row['id']}", "identifiers": [],
            "trigger_fact": {"code": "protocol_fact", "value": (
                "absent" if primary == "plausible-inapplicable" and row.get("trigger_pair") else "present"
            ),
                             "evidence_span": {"start": start, "end": start + len("trigger evidence"), "text": "trigger evidence"}},
            "behavior_oracle": {"must_include": ["expected action"], "must_avoid": ["wrong action"]},
            "expected": expected,
        })
        if primary == "integrity":
            row["prohibited_entry_ids"] = [entry_ids[-1]]
            row["integrity_mutation"] = {"entry_id": entry_ids[-1], "kind": integrity_kind,
                                         "expected_eligibility": (
                                             "invalid_corpus" if integrity_kind == "invalid_graph" else "excluded_before_ranking"
                                         )}
            if integrity_kind == "invalid_graph":
                row["integrity_mutation"]["mutation"] = "duplicate_entry_id"
                row["acceptable_entry_ids"] = []
            row["stage_assertions"] = (
                {"eligibility_state": "invalid", "ranking_state": "not_run"}
                if integrity_kind == "invalid_graph"
                else {"eligibility_state": "filtered", "ranking_state": "completed_without_prohibited_id"}
            )
    trigger_pairs = []
    by_id = {row["id"]: row for row in rows}
    for number in range(4):
        applicable = by_id[f"{split}-{number:02d}"]
        plausible_row = by_id[f"{split}-{number + 10:02d}"]
        trigger_pairs.append({
            "id": f"{split}-pair-{number}", "applicable_id": applicable["id"],
            "plausible_id": plausible_row["id"], "roles": [applicable["role"]],
            "one_fact_difference": True, "shared_facts": ["same synthetic task family"],
            "discriminating_fact": {"code": "protocol_fact", "applicable_value": "present", "plausible_value": "absent"},
        })
    result = {
        "schema_version": SCHEMA_VERSION, "split": split, "status": "candidate_unfrozen",
        "scoring_state": "not_started", "freeze_authorization": "pending_test",
        "evaluation_v1_digests": commands.EVALUATION_V1_DIGESTS,
        "candidate_rule_family": ["calibrated_similarity", "deterministic_trigger_rules"],
        "preregistered_similarity_grid": commands.SIMILARITY_GRID, "eligible_roles": list(ROLES),
        "fixtures": rows, "trigger_pairs": trigger_pairs,
        "provenance": {"feasibility_plan_digest": "a" * 64, "review_revisions_digest": "b" * 64,
                       "draft_sha256": {"draft.json": "c" * 64}},
    }
    if split == "evaluation-v2":
        result.update({
            "selected_candidate_id": "similarity:0.70",
            "selected_configuration_digest": "d" * 64,
            "calibration_score_access": False,
        })
    return result


class ExpertiseCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.framework = framework_at(self.root)
        self.work_id = "gate-one"
        (self.root / ".flow" / "runs" / self.work_id).mkdir(parents=True)
        self.corpus = commands._corpus_inventory(self.framework)
        self.plan = feasible_plan(self.corpus["entry_ids"])

    def test_feasibility_emits_exact_inventory_digests_and_private_durable_evidence(self):
        plan_path = self.root / "plan.json"
        plan_path.write_text(json.dumps(self.plan))
        args = SimpleNamespace(work_id=self.work_id, plan=str(plan_path), framework_dir=str(self.framework), json=True)
        with patch.object(commands, "repo_root", return_value=self.root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.feasibility_command(args)

        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "feasible")
        self.assertEqual(result["corpus_digest"], self.corpus["digest"])
        self.assertEqual(result["assignment_digest"], commands.digest(result["assignments"]))
        self.assertEqual(result["distinct_task_slots"], 60)
        self.assertEqual([row["id"] for row in result["environments"]], sorted(commands.REQUIRED_ENVIRONMENTS))
        self.assertEqual(result["assignments"], self.plan["staffing"])
        evidence = self.root / ".flow" / "runs" / self.work_id / "evidence"
        durable = evidence / "feasibility-v1.json"
        decision = evidence / "feasibility-decision.md"
        self.assertEqual(json.loads(durable.read_text())["plan_digest"], commands.digest(self.plan))
        self.assertEqual(durable.stat().st_mode & 0o777, 0o600)
        self.assertEqual(decision.stat().st_mode & 0o777, 0o600)

    def test_duplicate_task_slot_digest_pauses_before_fixture_work(self):
        self.plan["slots"][1]["task_slot_digest"] = self.plan["slots"][0]["task_slot_digest"]
        result = commands.assess_feasibility(self.plan, self.corpus)
        self.assertEqual(result["state"], "paused_for_engineer_decision")
        self.assertIn("fixture_authoring", result["prohibited_next_actions"])
        self.assertIn("scoring", result["prohibited_next_actions"])
        self.assertTrue(any("task_slot_digest" in value for value in result["blocking_checks"]))

    def test_missing_required_environment_pauses_and_returns_exact_gap(self):
        self.plan["environments"].pop()
        result = commands.assess_feasibility(self.plan, self.corpus)
        self.assertEqual(result["state"], "paused_for_engineer_decision")
        self.assertEqual(result["reason"], "environment_gap")
        missing = sorted(commands.REQUIRED_ENVIRONMENTS - {row["id"] for row in self.plan["environments"]})[0]
        self.assertIn(f"required environment is not available: {missing}", result["blocking_checks"])

    def test_manifest_rejects_each_fixture_with_shared_author_label_or_reviewer(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        manifest["fixtures"][0]["labeler"] = manifest["fixtures"][0]["query_author"]
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("query author, labeler, and reviewer must differ", " ".join(result["problems"]))

    def test_manifest_rejects_structured_span_and_expected_state_drift(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        manifest["fixtures"][0]["trigger_fact"]["evidence_span"]["text"] = "other text"
        manifest["fixtures"][1]["expected"]["outer_state"] = "no_match"
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        rendered = " ".join(result["problems"])
        self.assertIn("does not bind exact task text", rendered)
        self.assertIn("applicable expected result is inconsistent", rendered)

    def test_manifest_rejects_pair_metadata_that_does_not_bind_fixture_facts(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        manifest["trigger_pairs"][0]["discriminating_fact"]["code"] = "invented_fact"
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("discriminating fact code does not match", " ".join(result["problems"]))

    def test_manifest_rejects_pair_values_that_do_not_bind_the_two_fixture_facts(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        manifest["trigger_pairs"][0]["discriminating_fact"]["applicable_value"] = "absent"
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("discriminating fact values do not match", " ".join(result["problems"]))

    def test_manifest_rejects_invalid_graph_expected_tuple_that_claims_an_admission(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        integrity = next(row for row in manifest["fixtures"] if row.get("integrity_mutation", {}).get("kind") == "invalid_graph")
        integrity["expected"]["candidate_decision"] = "admitted"
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("integrity expected result is inconsistent", " ".join(result["problems"]))

    def test_manifest_rejects_role_mutation_that_claims_invalid_corpus(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        integrity = next(row for row in manifest["fixtures"] if row.get("integrity_mutation", {}).get("kind") == "role_mismatch")
        integrity["expected"] = {"outer_state": "invalid_corpus", "cause": "invalid_canonical_corpus",
                                 "admission_state": "not_run", "candidate_decision": "not_run", "disposition": None}
        result = commands.validate_fixture_manifest(manifest, self.corpus)
        self.assertEqual(result["state"], "invalid")
        self.assertIn("integrity expected result is inconsistent", " ".join(result["problems"]))

    def test_campaign_freeze_requires_exact_approval_and_writes_new_private_files(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        source = self.root / "candidate.json"
        source.write_text(json.dumps(manifest, indent=2))
        args = SimpleNamespace(
            work_id=self.work_id, campaign_action="freeze", manifest=str(source),
            approved_digest=commands.digest(manifest), approved_by="Test Engineer",
            framework_dir=str(self.framework), json=True,
        )
        with (
            patch.object(commands, "repo_root", return_value=self.root),
            patch.object(commands, "_campaign_identity", return_value={"identity": "fixed"}),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            code = commands.campaign_command(args)
        self.assertEqual(code, 0, output.getvalue())
        root = self.root / ".flow" / "runs" / self.work_id / "evidence" / "calibration-v1" / "frozen"
        frozen = root / "candidate-manifest.json"
        receipt = root / "freeze-receipt.json"
        self.assertEqual(frozen.read_bytes(), source.read_bytes())
        self.assertEqual(frozen.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        value = json.loads(receipt.read_text())
        self.assertEqual(value["candidate_manifest_digest"], commands.digest(manifest))
        self.assertEqual(len(value["fixture_digests"]), 30)
        with (
            patch.object(commands, "repo_root", return_value=self.root),
            patch.object(commands, "_campaign_identity", return_value={"identity": "fixed"}),
            contextlib.redirect_stdout(io.StringIO()) as duplicate,
        ):
            duplicate_code = commands.campaign_command(args)
        self.assertEqual(duplicate_code, 2)
        self.assertIn("already frozen", duplicate.getvalue())

    def test_freeze_receipt_rejects_approval_for_a_different_digest(self):
        manifest = fixture_manifest("calibration-v1", self.corpus["entry_ids"])
        with self.assertRaisesRegex(commands.ExpertiseCommandError, "approved digest"):
            commands.build_freeze_receipt(
                manifest, json.dumps(manifest).encode(), {"identity": "fixed"},
                approved_digest="0" * 64, approved_by="Test Engineer",
                approved_at="2026-09-11T00:00:00+00:00",
            )

    def test_evaluation_v2_freeze_binds_independence_selection_and_source_hashes(self):
        manifest = fixture_manifest("evaluation-v2", self.corpus["entry_ids"])
        selected_payload = {
            "state": "selected", "candidate_id": "similarity:0.70",
            "strategy_config": {"strategy": "similarity", "threshold": 0.7},
        }
        selected = dict(
            selected_payload,
            executable_configuration_digest=commands.digest(selected_payload),
        )
        manifest["selected_configuration_digest"] = selected["executable_configuration_digest"]
        selection_path = (
            self.root / ".flow" / "runs" / self.work_id / "evidence" /
            "calibration-v1" / "scoring" / "selected-configuration.json"
        )
        selection_path.parent.mkdir(parents=True)
        selection_path.write_text(json.dumps(selected))
        source = self.root / "v2-candidate.json"
        source.write_text(json.dumps(manifest, indent=2))
        deterministic = {
            "candidate_manifest_digest": commands.digest(manifest),
            "reference_manifest_digests": ["1" * 64, "2" * 64],
            "flags": [{
                "candidate_id": "v2-slot-01", "reference_split": "calibration-v1",
                "reference_id": "cal-slot-01", "kinds": ["lexical"],
            }],
        }
        review = {
            "schema_version": 1, "state": "resolved",
            "candidate_manifest_digest": commands.digest(manifest),
            "reference_manifest_digests": ["1" * 64, "2" * 64],
            "deterministic_receipt_digest": commands.digest(deterministic),
            "flag_count": 1,
            "reviewed_flags": [{
                "candidate_id": "v2-slot-01", "reference_split": "calibration-v1",
                "reference_id": "cal-slot-01", "kinds": ["lexical"],
                "disposition": "distinct", "rationale": "Different task and decision.",
            }],
            "unresolved_flags": [], "reviewer": "blind-reviewer",
            "reviewed_at": "2026-09-12T00:00:00+00:00", "blinded_to_fixture_labels": True,
        }
        review_path = self.root / "independence-review.json"
        review_path.write_text(json.dumps(review))
        (self.root / "deterministic-receipt.json").write_text(json.dumps(deterministic))
        args = SimpleNamespace(
            work_id=self.work_id, campaign_action="freeze", manifest=str(source),
            approved_digest=commands.digest(manifest), approved_by="Test Engineer",
            independence_review=str(review_path), framework_dir=str(self.framework), json=True,
        )
        source_hashes = {name: "4" * 64 for name in commands.CAMPAIGN_SOURCE_FILES}
        with (
            patch.object(commands, "repo_root", return_value=self.root),
            patch.object(commands, "_campaign_identity", return_value={"identity": "fixed"}),
            patch.object(commands, "_campaign_source_sha256", return_value=source_hashes),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            code = commands.campaign_command(args)
        self.assertEqual(code, 0, output.getvalue())
        receipt_path = (
            self.root / ".flow" / "runs" / self.work_id / "evidence" /
            "evaluation-v2" / "frozen" / "freeze-receipt.json"
        )
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt["independence_review_digest"], commands.digest(review))
        self.assertEqual(receipt["source_sha256"], source_hashes)
        self.assertEqual(receipt["selected_configuration"]["candidate_id"], "similarity:0.70")

    def test_campaign_source_identity_tracks_scorer_and_finalizer_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in commands.CAMPAIGN_SOURCE_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"original")
            baseline = commands._campaign_source_sha256(root)
            for relative in ("cli/expertise_campaign.py", "cli/expertise_commands.py"):
                with self.subTest(relative=relative):
                    path = root / relative
                    path.write_bytes(b"changed")
                    self.assertNotEqual(commands._campaign_source_sha256(root), baseline)
                    path.write_bytes(b"original")

    def test_evaluation_v2_freeze_requires_resolved_independence_review(self):
        manifest = fixture_manifest("evaluation-v2", self.corpus["entry_ids"])
        selected_payload = {"state": "selected", "candidate_id": "similarity:0.70"}
        selected = dict(selected_payload, executable_configuration_digest=commands.digest(selected_payload))
        manifest["selected_configuration_digest"] = selected["executable_configuration_digest"]
        selection_path = (
            self.root / ".flow" / "runs" / self.work_id / "evidence" /
            "calibration-v1" / "scoring" / "selected-configuration.json"
        )
        selection_path.parent.mkdir(parents=True)
        selection_path.write_text(json.dumps(selected))
        source = self.root / "v2-candidate.json"
        source.write_text(json.dumps(manifest))
        args = SimpleNamespace(
            work_id=self.work_id, campaign_action="freeze", manifest=str(source),
            approved_digest=commands.digest(manifest), approved_by="Test Engineer",
            independence_review=None, framework_dir=str(self.framework), json=True,
        )
        with patch.object(commands, "repo_root", return_value=self.root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.campaign_command(args)
        self.assertEqual(code, 2)
        self.assertIn("requires --independence-review", output.getvalue())

    def test_heldout_environment_evidence_requires_every_exact_supported_cell(self):
        manifest_digest = "a" * 64
        configuration_digest = "b" * 64
        one_cell = {
            "schema_version": 1, "manifest_digest": manifest_digest,
            "selected_configuration_digest": configuration_digest,
            "cells": [{
                "id": sorted(commands.REQUIRED_ENVIRONMENTS)[0], "status": "passed",
                "repeatability": "identical", "fixture_oracles": "passed",
                "warm_p95_seconds": 0.5, "cold_p95_seconds": 10.0,
                "persistent_bytes": 1000, "evidence_digest": "c" * 64,
            }],
        }
        path = self.root / "environment.json"
        path.write_text(json.dumps(one_cell))
        result = commands._environment_evidence(
            str(path), manifest_digest=manifest_digest,
            configuration_digest=configuration_digest,
        )
        self.assertEqual(result["state"], "unverified")
        self.assertEqual(len(result["missing_environment_ids"]), 4)

        one_cell["cells"] = [
            dict(one_cell["cells"][0], id=environment_id)
            for environment_id in sorted(commands.REQUIRED_ENVIRONMENTS)
        ]
        path.write_text(json.dumps(one_cell))
        result = commands._environment_evidence(
            str(path), manifest_digest=manifest_digest,
            configuration_digest=configuration_digest,
        )
        self.assertEqual(result["state"], "passed")

    def test_cli_fixture_validator_uses_hyphenated_class_and_path_vocabulary(self):
        manifest = fixture_manifest("evaluation-v2", self.corpus["entry_ids"])
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        args = SimpleNamespace(manifest=str(path), framework_dir=str(self.framework), json=True)
        with patch.object(commands, "repo_root", return_value=self.root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.fixture_validate_command(args)
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0, result)
        self.assertEqual(result["primary_classes"], {
            "applicable": 10, "integrity": 4, "plausible-inapplicable": 10, "true-no-match": 6,
        })
        self.assertEqual(result["plausible_paths"], {"admission-rejected": 5, "controlled-delivery": 5})

    def test_independence_command_flags_exact_identifier_and_lexical_overlap_without_labels(self):
        candidate = {"split": "evaluation-v2", "fixtures": [
            {"id": "candidate-exact", "task": "Investigate AE-743 before changing production", "identifiers": ["AE-743"]},
            {"id": "candidate-identifier", "task": "Perform a distinct task with AE-744", "identifiers": ["AE-744"]},
            {"id": "candidate-lexical", "task": "Restore service after planned migration failed"},
        ]}
        reference = {"split": "calibration-v1", "fixtures": [
            {"id": "reference-exact", "task": "Investigate AE-743 before changing production", "identifiers": ["AE-743"]},
            {"id": "reference-identifier", "task": "A different alert references AE-744", "identifiers": ["AE-744"]},
            {"id": "reference-lexical", "task": "Restore the service after a planned migration has failed"},
        ]}
        result = commands.independence(candidate, [reference], 0.6)
        by_candidate = {row["candidate_id"]: set(row["kinds"]) for row in result["flags"]}
        self.assertIn("exact", by_candidate["candidate-exact"])
        self.assertIn("identifier", by_candidate["candidate-identifier"])
        self.assertIn("lexical", by_candidate["candidate-lexical"])
        rendered = json.dumps(result)
        self.assertNotIn("primary_class", rendered)
        self.assertNotIn("acceptable_entry_ids", rendered)

    def test_identifier_overlap_uses_declared_locators_without_treating_hyphenated_words_as_ids(self):
        candidate = {"split": "evaluation-v2", "fixtures": [
            {"id": "candidate", "task": "Review the month-end export for CSV output", "identifiers": ["CSV"]},
        ]}
        reference = {"split": "calibration-v1", "fixtures": [
            {"id": "reference", "task": "Check CSV formatting in a different workflow", "identifiers": ["CSV"]},
            {"id": "hyphen", "task": "A month-end close uses another format", "identifiers": []},
        ]}
        result = commands.independence(candidate, [reference], 1.0)
        flags = {(row["reference_id"], tuple(row["kinds"])) for row in result["flags"]}
        self.assertIn(("reference", ("identifier",)), flags)
        self.assertFalse(any(row["reference_id"] == "hyphen" and "identifier" in row["kinds"] for row in result["flags"]))


class RuntimeCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_register_exposes_runtime_query_disposition_and_receipt_help(self):
        parser = argparse.ArgumentParser()
        commands.register(parser.add_subparsers(dest="command", required=True))
        with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as exited:
            parser.parse_args(["expertise", "--help"])
        self.assertEqual(exited.exception.code, 0)
        help_text = output.getvalue()
        for action in ("model", "index", "query", "brief", "disposition", "feedback", "receipts", "campaign"):
            self.assertIn(action, help_text)

    def test_dispatch_routes_model_action_to_the_runtime_command(self):
        args = SimpleNamespace(expertise_action="model")
        with patch.object(commands, "model_command", return_value=17) as handler:
            self.assertEqual(commands.dispatch(args), 17)
        handler.assert_called_once_with(args)

    def test_model_status_uses_the_patched_private_runtime_root_and_keeps_remedy(self):
        args = SimpleNamespace(model_action="status", json=True)
        expected = {"state": "unavailable", "reason": "model_missing", "remedy": "install", "environment_id": "test"}
        with patch.object(commands, "FLOW_HOME", self.root / "flow-home"), patch.object(commands, "runtime_status", return_value=expected), contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.model_command(args)
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.getvalue()), expected)

    def test_query_receipt_command_never_emits_raw_query_text(self):
        raw_query = "private incident detail AE-743"
        query_file = self.root / "query.txt"
        query_file.write_text(raw_query)
        args = SimpleNamespace(role="support-lead", query_file=str(query_file), strategy="similarity",
                               threshold=0.7, framework_dir=None, user_dir=None, json=True)
        outcome = {
            "schema_version": 1, "request_id": "request-1", "role": "support-lead",
            "state": "no_match", "cause": "no_eligible_entries",
            "eligibility": {"state": "empty", "identity": "eligibility-v1", "eligible_ids": [], "excluded": []},
            "ranking": {"state": "not_run", "reason": "not_run_empty_eligibility", "provider_calls": 0, "identity": "ranking-v1", "candidates": []},
            "admission": {"state": "not_run", "strategy": "not-run", "admitted_ids": [], "candidate_decisions": [], "identity": "admission-v1"},
            "delivery": {"state": "not_run", "reason": "not_run", "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0,
                         "limits": {"delivery_entry_cap": 1, "delivery_byte_cap": 256}, "identity": "delivery-v1"},
        }
        facts = {"schema_version": 1, "revision": "facts-v1", "normalizer_revision": "normalizer-v1", "facts": []}
        model = {"provider": {"revision": "fake"}, "model": {}}
        with patch.object(commands, "FLOW_HOME", self.root / "flow-home"), patch.object(commands, "_runtime_paths", return_value=(self.root, None)), patch.object(commands, "runtime_status", return_value={"state": "unavailable", "reason": "model_missing", "remedy": "install", "environment_id": "test"}), patch.object(commands, "_read_object", side_effect=[model, facts]), patch.object(commands, "execute", return_value=outcome) as execute, patch.object(commands, "receipt_root", return_value=self.root / "receipts"), patch.object(commands, "write_pre", return_value={"digest": "receipt-v1"}) as write_pre, contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.query_command(args)
        self.assertEqual(code, 0)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[1], raw_query)
        self.assertEqual(write_pre.call_args.args[3], commands.normalized_task(raw_query))
        rendered = output.getvalue()
        self.assertNotIn(raw_query, rendered)
        self.assertEqual(json.loads(rendered)["pre_receipt"], {"digest": "receipt-v1"})

    def test_brief_reads_bounded_stdin_and_rejects_cross_role_result(self):
        outcome = {
            "schema_version": 1, "request_id": "request-1", "role": "support-lead",
            "state": "no_match", "cause": "no_eligible_entries",
            "eligibility": {"schema_version": 1, "state": "empty", "role": "support-lead", "identity": "eligible", "eligible_ids": [], "excluded": []},
            "ranking": {"schema_version": 1, "state": "not_run", "reason": "not_run_empty_eligibility", "provider_calls": 0, "identity": "ranked", "candidates": []},
            "admission": {"schema_version": 1, "state": "not_run", "strategy": "not-run", "admitted_ids": [], "candidate_decisions": [], "identity": "admitted"},
            "delivery": {"schema_version": 1, "state": "not_run", "reason": "not_run", "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0,
                         "limits": {"delivery_entry_cap": 3, "delivery_byte_cap": 16384}, "identity": "delivered", "entries": []},
            "pre_receipt": {"digest": "receipt-v1"},
        }
        args = SimpleNamespace(role="support-lead", json=True)
        stdin = io.TextIOWrapper(io.BytesIO(b"private task"), encoding="utf-8")
        with patch.object(commands.sys, "stdin", stdin), patch.object(commands, "_query_result", return_value=outcome) as query, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.brief_command(args), 0, output.getvalue())
        self.assertEqual(query.call_args.kwargs["task_override"], "private task")
        brief = json.loads(output.getvalue())
        self.assertEqual(brief["state"], "no_match")
        self.assertEqual(brief["advisory_entries"], [])
        self.assertNotIn("private task", output.getvalue())
        wrong = dict(outcome, role="architect")
        stdin = io.TextIOWrapper(io.BytesIO(b"private task"), encoding="utf-8")
        with patch.object(commands.sys, "stdin", stdin), patch.object(commands, "_query_result", return_value=wrong), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.brief_command(args), 2)
        self.assertEqual(json.loads(output.getvalue())["advisory_entries"], [])
        oversized = io.TextIOWrapper(io.BytesIO(b"x" * 32769), encoding="utf-8")
        with patch.object(commands.sys, "stdin", oversized), patch.object(commands, "_query_result") as query, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.brief_command(args), 2)
        query.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["advisory_entries"], [])
        empty = io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8")
        with patch.object(commands.sys, "stdin", empty), patch.object(commands, "_query_result") as query, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.brief_command(args), 2)
        query.assert_not_called()
        self.assertIn("non-empty", json.loads(output.getvalue())["reason"])

    def test_brief_rejects_cross_role_or_incomplete_delivered_entry(self):
        entry = {"@id": "entry-a", "name": "Example", "abstract": "A useful principle",
                 "flow:trigger": "When triaging", "flow:requiredBehavior": "Check scope",
                 "flow:failureMode": "Wrong scope", "role": "architect",
                 "source_layer": "framework", "method_layer": "method", "lifecycle_state": "current",
                 "owner": "flow", "entry_digest": "digest-a"}
        outcome = {"schema_version": 1, "eligibility": {}, "ranking": {}, "admission": {},
                   "role": "support-lead", "state": "admitted", "request_id": "request-1",
                   "cause": "delivered", "pre_receipt": {"digest": "receipt-v1"},
                   "delivery": {"state": "delivered", "identity": "delivery-v1",
                                "delivered_ids": ["entry-a"], "entries": [entry],
                                "limits": {"delivery_entry_cap": 3, "delivery_byte_cap": 16384}}}
        args = SimpleNamespace(role="support-lead", json=True)
        for candidate in (entry, dict(entry, role="support-lead", abstract="")):
            outcome["delivery"]["entries"] = [candidate]
            stdin = io.TextIOWrapper(io.BytesIO(b"private task"), encoding="utf-8")
            with patch.object(commands.sys, "stdin", stdin), patch.object(commands, "_query_result", return_value=outcome), patch.object(commands, "validate_outcome"), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(commands.brief_command(args), 2)
            self.assertEqual(json.loads(output.getvalue())["advisory_entries"], [])

    def test_disposition_requires_linked_pre_receipt_and_writes_only_validated_handback(self):
        root = self.root / "receipts"
        root.mkdir()
        pre = {"delivery": {"delivered_ids": [], "identity": "delivery-v1"}}
        pre_bytes = json.dumps(pre, sort_keys=True).encode()
        request_id = "request-1"
        (root / f"{request_id}.pre.json").write_bytes(pre_bytes)
        handback = {"schema_version": 1, "state": "observed", "request_id": request_id,
                    "pre_receipt_digest": hashlib.sha256(pre_bytes).hexdigest(), "identity": "delivery-v1", "entries": []}
        handback_path = self.root / "handback.json"
        handback_path.write_text(json.dumps(handback))
        args = SimpleNamespace(request_id=request_id, handback=str(handback_path), json=True)
        with patch.object(commands, "FLOW_HOME", self.root / "flow-home"), patch.object(commands, "receipt_root", return_value=root), contextlib.redirect_stdout(io.StringIO()) as output:
            code = commands.disposition_command(args)
        self.assertEqual(code, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "complete")
        post = json.loads((root / f"{request_id}.post.json").read_text())
        self.assertIn("created_at", post)
        self.assertNotIn("query", json.dumps(post))

    def test_disposition_accepts_bounded_stdin_without_a_handback_file(self):
        root = self.root / "receipts"
        root.mkdir()
        request_id = "request-stdin"
        pre = {"delivery": {"delivered_ids": [], "identity": "delivery-v1"}}
        pre_bytes = json.dumps(pre).encode()
        (root / f"{request_id}.pre.json").write_bytes(pre_bytes)
        handback = {"schema_version": 1, "state": "observed", "request_id": request_id,
                    "pre_receipt_digest": hashlib.sha256(pre_bytes).hexdigest(),
                    "identity": "delivery-v1", "entries": []}
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(handback).encode()), encoding="utf-8")
        args = SimpleNamespace(request_id=request_id, handback=None, handback_stdin=True, json=True)
        with patch.object(commands.sys, "stdin", stdin), patch.object(commands, "FLOW_HOME", self.root / "flow-home"), patch.object(commands, "receipt_root", return_value=root), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(commands.disposition_command(args), 0, output.getvalue())
        self.assertEqual(json.loads(output.getvalue())["state"], "complete")

    def test_feedback_links_delivered_entry_without_retaining_task_text(self):
        root = self.root / "receipts"
        root.mkdir()
        request_id = "request-feedback-1"
        (root / f"{request_id}.pre.json").write_text(json.dumps({
            "kind": "pre-agent", "request_id": request_id, "role": "support-lead",
            "delivery": {"delivered_ids": ["entry-a"]},
        }))
        args = SimpleNamespace(request_id=request_id, lane="review", category="inapplicable",
                               entry_id="entry-a", role=None, json=True)
        with (patch.object(commands, "repo_root", return_value=self.root),
              patch.object(commands, "FLOW_HOME", self.root / "flow-home"),
              patch.object(commands, "receipt_root", return_value=root),
              contextlib.redirect_stdout(io.StringIO()) as output):
            self.assertEqual(commands.feedback_command(args), 0)
            args.entry_id = "not-delivered"
            self.assertEqual(commands.feedback_command(args), 2)
        records = list(root.glob("feedback-*.json"))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())
        self.assertEqual(record["category"], "inapplicable")
        self.assertEqual(record["role"], "support-lead")
        self.assertNotIn("query", record)
        self.assertNotIn("task", record)

    def test_feedback_can_record_pre_receipt_failure_without_query_text(self):
        root = self.root / "receipts"
        args = SimpleNamespace(request_id=None, role="support-lead", lane="plan",
                               category="failure", entry_id=None, json=True)
        with (patch.object(commands, "repo_root", return_value=self.root),
              patch.object(commands, "FLOW_HOME", self.root / "flow-home"),
              patch.object(commands, "receipt_root", return_value=root),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(commands.feedback_command(args), 0)
        record = json.loads(next(root.glob("feedback-*.json")).read_text())
        self.assertIsNone(record["request_id"])
        self.assertEqual(record["category"], "failure")


class AdmissionInputDomainTests(unittest.TestCase):
    def input(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION, "role": "support-lead", "admission_contract_revision": "admission-v1",
            "query_view": {"normalizer_revision": "nfkc-v1", "normalized_text": "inspect incident", "tokens": ["inspect", "incident"], "identifiers": []},
            "task_facts": {"derivation_revision": "facts-v1", "facts": [{"code": "customer-impact", "value": "present", "evidence_span": [0, 7]}]},
            "eligibility": {"corpus_digest": "corpus-v1", "eligibility_revision": "eligibility-v1"},
            "ranking": {"ranker_revision": "ranker-v1", "provider_model_revision": "provider-v1", "candidates": [{
                "entry_id": "flow:entry/support-lead/method", "ordinal": 1, "provider_score": 0.9,
                "entry_digest": "entry-v1", "score_semantics": "cosine", "structured_exact_match": False,
                "trigger_view": "trigger-v1", "failure_mode_view": "failure-v1",
            }]},
            "limits": {"ranked_candidate_window": 3, "maximum_admitted_ids": 2,
                       "delivery_entry_cap": 2, "delivery_byte_cap": 256},
        }

    def test_admission_input_is_valid_only_as_an_ordered_bounded_pre_adapter_value(self):
        self.assertEqual(validate_admission_input(self.input())["role"], "support-lead")
        invalid = self.input()
        invalid["ranking"]["candidates"][0]["ordinal"] = 2
        with self.assertRaisesRegex(ExpertiseContractError, "rank ordered"):
            validate_admission_input(invalid)

    def test_delivery_caps_are_independent_from_admission_caps(self):
        invalid = self.input()
        invalid["limits"]["delivery_entry_cap"] = 3
        with self.assertRaisesRegex(ExpertiseContractError, "delivery_entry_cap"):
            validate_admission_input(invalid)
        invalid = self.input()
        invalid["limits"]["delivery_byte_cap"] = 255
        with self.assertRaisesRegex(ExpertiseContractError, "delivery_byte_cap"):
            validate_admission_input(invalid)

    def test_identity_mutation_invalidates_only_its_dependent_identity(self):
        projection = identity("projection", {
            "corpus_digest": "corpus-v1", "lifecycle_revision": "lifecycle-v1",
            "entry_serializer_revision": "serializer-v1", "provider_revision": "provider-v1",
            "model_artifact_digest": "model-v1", "embedding_runtime_revision": "runtime-v1",
            "index_schema_revision": "index-v1",
        })
        admission_components = {
            "projection_identity": projection["digest"], "admission_input_revision": "input-v1",
            "fact_derivation_revision": "facts-v1", "strategy_revision": "strategy-v1",
            "strategy_config_digest": "config-v1", "ranked_candidate_window": 3,
        }
        admission = identity("admission", admission_components)
        delivery = identity("delivery", {
            "admission_identity": admission["digest"], "packing_revision": "packing-v1",
            "envelope_revision": "envelope-v1", "disposition_contract_revision": "disposition-v1",
            "delivery_entry_cap": 2, "delivery_byte_cap": 256,
        })
        changed_components = dict(admission_components, strategy_config_digest="config-v2")
        changed_admission = identity("admission", changed_components)
        self.assertEqual(validate_identity(projection, "projection")["digest"], projection["digest"])
        self.assertNotEqual(admission["digest"], changed_admission["digest"])
        self.assertEqual(delivery["components"]["admission_identity"], admission["digest"])
        changed_delivery = identity("delivery", dict(delivery["components"], delivery_byte_cap=512))
        self.assertEqual(validate_identity(admission, "admission")["digest"], admission["digest"])
        self.assertNotEqual(delivery["digest"], changed_delivery["digest"])

    def test_trigger_rule_is_digest_bound_and_closed(self):
        rule = {"schema_version": SCHEMA_VERSION, "entry_id": "flow:entry/support-lead/method",
                "entry_digest": "a" * 64, "trigger_digest": "b" * 64,
                "failure_mode_digest": "c" * 64,
                "revision": "trigger-v1", "unknown_policy": "reject",
                "clauses": [{"fact": "customer_impact", "operator": "is", "value": "present"}]}
        rule["digest"] = digest(rule)
        self.assertEqual(validate_trigger_rule(rule, entry_id=rule["entry_id"])["revision"], "trigger-v1")
        for field, value in (("trigger_digest", "d" * 64), ("failure_mode_digest", "e" * 64)):
            with self.subTest(field=field):
                altered = copy.deepcopy(rule)
                altered[field] = value
                with self.assertRaisesRegex(ExpertiseContractError, "digest mismatch"):
                    validate_trigger_rule(altered)
        altered = copy.deepcopy(rule)
        altered["clauses"][0]["value"] = "absent"
        with self.assertRaisesRegex(ExpertiseContractError, "digest mismatch"):
            validate_trigger_rule(altered)

    def test_no_match_requires_empty_eligibility_and_no_provider_or_gate_work(self):
        outcome = {
            "schema_version": SCHEMA_VERSION, "request_id": "request-1", "role": "support-lead",
            "state": "no_match", "cause": "no_eligible_entries",
            "eligibility": {"schema_version": SCHEMA_VERSION, "state": "empty", "role": "support-lead",
                            "eligible_ids": [], "excluded": [], "identity": "eligibility-v1"},
            "ranking": {"schema_version": SCHEMA_VERSION, "state": "not_run", "reason": "not_run_empty_eligibility",
                        "provider_calls": 0, "candidates": [], "identity": "ranking-v1"},
            "admission": {"schema_version": SCHEMA_VERSION, "state": "not_run", "strategy": "similarity-grid",
                          "admitted_ids": [], "candidate_decisions": [], "identity": "admission-v1"},
            "delivery": {"schema_version": SCHEMA_VERSION, "state": "not_run", "reason": "not_run",
                         "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0,
                         "limits": {"delivery_entry_cap": 2, "delivery_byte_cap": 256}, "identity": "delivery-v1", "entries": []},
        }
        self.assertEqual(validate_outcome(outcome)["state"], "no_match")
        unavailable = copy.deepcopy(outcome)
        unavailable["ranking"] = {"schema_version": SCHEMA_VERSION, "state": "unavailable", "reason": "provider_load_failed",
                                    "provider_calls": 1, "candidates": [], "identity": "ranking-v1"}
        with self.assertRaisesRegex(ExpertiseContractError, "no_match"):
            validate_outcome(unavailable)

    def test_each_degraded_outer_state_requires_the_stage_that_failed(self):
        eligibility = {"schema_version": SCHEMA_VERSION, "state": "eligible", "role": "support-lead",
                       "eligible_ids": ["entry-a"], "excluded": [], "identity": "eligibility-v1"}
        delivery = {"schema_version": SCHEMA_VERSION, "state": "not_run", "reason": "not_run",
                    "delivered_ids": [], "withheld_ids": [], "actual_bytes": 0,
                    "limits": {"delivery_entry_cap": 2, "delivery_byte_cap": 256}, "identity": "delivery-v1", "entries": []}
        no_admission = {"schema_version": SCHEMA_VERSION, "state": "not_run", "strategy": "not-run",
                        "admitted_ids": [], "candidate_decisions": [], "identity": "admission-v1"}
        cases = [
            ("stale", "projection_stale", "stale", "projection_stale", no_admission),
            ("rebuilding", "projection_rebuilding", "rebuilding", "projection_rebuilding", no_admission),
            ("unavailable", "provider_unavailable", "unavailable", "provider_load_failed", no_admission),
        ]
        for outer, cause, ranking_state, reason, admission in cases:
            with self.subTest(cause=cause):
                outcome = {"schema_version": SCHEMA_VERSION, "request_id": "request-1", "role": "support-lead",
                           "state": outer, "cause": cause, "eligibility": eligibility,
                           "ranking": {"schema_version": SCHEMA_VERSION, "state": ranking_state, "reason": reason,
                                       "provider_calls": 0, "candidates": [], "identity": "ranking-v1"},
                           "admission": admission, "delivery": delivery}
                self.assertEqual(validate_outcome(outcome)["cause"], cause)
                wrong = copy.deepcopy(outcome)
                wrong["state"] = "no_match"
                wrong["cause"] = "no_eligible_entries"
                with self.assertRaisesRegex(ExpertiseContractError, "no_match"):
                    validate_outcome(wrong)

    def test_service_normalizes_invalid_corpus_as_invalid_corpus_not_no_match(self):
        invalid = expertise.ExpertiseError("invalid-expertise-json", "broken", source="fixture", remediation="repair")
        provider = SimpleNamespace()
        strategy = SimpleNamespace(revision="strategy-v1")
        definitions = {"schema_version": 1, "revision": "facts-v1", "normalizer_revision": "nfkc-v1", "facts": []}
        with patch.object(service, "canonical_snapshot", side_effect=invalid):
            result = service.execute("support-lead", "task", framework_dir=Path("fixture"), user_dir=None,
                                     flow_home=Path("fixture"), provider=provider, strategy=strategy,
                                     strategy_config={}, fact_definitions=definitions, request_id="request-1")
        self.assertEqual((result["state"], result["cause"]), ("invalid_corpus", "invalid_canonical_corpus"))
        self.assertEqual(result["ranking"]["state"], "not_run")

    def test_admission_cannot_restore_or_reorder_ranked_ids(self):
        decision = {"schema_version": SCHEMA_VERSION, "state": "admitted", "strategy": "trigger-rule",
                    "admitted_ids": ["entry-b", "entry-a"], "candidate_decisions": [], "identity": "admission-v1"}
        with self.assertRaisesRegex(ExpertiseContractError, "rank order"):
            validate_admission_decision(decision, ["entry-a", "entry-b"])
        decision["admitted_ids"] = ["entry-a", "entry-c"]
        with self.assertRaisesRegex(ExpertiseContractError, "unranked"):
            validate_admission_decision(decision, ["entry-a", "entry-b"])

    def test_delivery_partitions_admitted_ids_and_disposition_is_complete(self):
        delivery = {"schema_version": SCHEMA_VERSION, "state": "delivered", "reason": "delivered",
                    "delivered_ids": ["entry-a"], "withheld_ids": ["entry-b"], "actual_bytes": 200,
                    "limits": {"delivery_entry_cap": 1, "delivery_byte_cap": 256}, "identity": "delivery-v1",
                    "entries": [{"@id": "entry-a"}]}
        self.assertEqual(validate_delivery_result(delivery, ["entry-a", "entry-b"])["delivered_ids"], ["entry-a"])
        over_cap = copy.deepcopy(delivery)
        over_cap["actual_bytes"] = 257
        with self.assertRaisesRegex(ExpertiseContractError, "exceeds"):
            validate_delivery_result(over_cap, ["entry-a", "entry-b"])
        disposition = {"schema_version": SCHEMA_VERSION, "state": "observed",
                       "created_at": "2026-09-11T00:00:00+00:00", "request_id": "request-1",
                       "pre_receipt_digest": "receipt-v1", "identity": "disposition-v1",
                       "entries": [{"entry_id": "entry-a", "disposition": "applied", "reason": "trigger_satisfied", "evidence_codes": ["customer_impact"]}]}
        self.assertEqual(validate_disposition_record(disposition, ["entry-a"])["state"], "observed")
        with self.assertRaisesRegex(ExpertiseContractError, "every delivered ID"):
            validate_disposition_record(dict(disposition, entries=[]), ["entry-a"])


if __name__ == "__main__":
    unittest.main()
