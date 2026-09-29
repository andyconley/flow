import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))

from delivery_contracts import build_delivery_charter, build_shaper_contract, canonical  # noqa: E402
from runstate import apply_transition, handoff_to_review, history  # noqa: E402
from orchestration import validate_manifest  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402


class AutomaticReviewHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".git").mkdir()
        self.work_id = "demo"
        self.run_dir = self.root / ".flow" / "runs" / self.work_id
        self.run_dir.mkdir(parents=True)
        for name in ("requirements.md", "acceptance.md", "plan.md", "validation.md", "output.md", "reconciliation.md", "verification.md"):
            (self.run_dir / name).write_text(name + "\n")
        sources = {
            "requirements": {"path": ".flow/runs/demo/requirements.md", "sha256": "a" * 64},
            "acceptance_criteria": {"path": ".flow/runs/demo/acceptance.md", "sha256": "b" * 64},
        }
        shaper = build_shaper_contract(
            self.work_id, sources,
            shaper_intent(allowed_lifecycle_operations=["handoff_to_review"]),
        )
        charter = build_delivery_charter(shaper)
        self.charter = charter
        delivery_relative = f"delivery/{charter['digest']}"
        delivery_dir = self.run_dir / delivery_relative
        delivery_dir.mkdir(parents=True)
        (delivery_dir / "delivery-charter.json").write_text(canonical(charter) + "\n")
        self.attempt_id = "attempt-1"
        attempt_dir = self.run_dir / "execution" / self.attempt_id
        attempt_dir.mkdir(parents=True)
        self.claim_digest = "c" * 64
        envelope = {
            "delivery_charter_digest": charter["digest"],
            "delivery_lead_claim_digest": self.claim_digest,
            "delivery_lead_claim": {"generation": 1},
        }
        (attempt_dir / "envelope.json").write_text(json.dumps(envelope) + "\n")
        (attempt_dir / "receipt.json").write_text(json.dumps({
            "actions": [{"status": "completed", "request": {"assignment_id": "producer", "instance_id": "producer"}}],
            "manager_calls": [],
        }) + "\n")
        manifest = {
            "schema_version": 1, "work_id": self.work_id, "mode": "single",
            "risk": {"hard_triggers": [], "aggravating_factors": [], "classification": "standard", "rationale": "test"},
            "assignments": [{
                "id": "producer", "lane": "implement", "role": "lead-developer",
                "provider": {"kind": "agent", "id": "producer"},
                "brief_path": ".flow/runs/demo/plan.md", "input_evidence": [".flow/runs/demo/requirements.md"],
                "read_scopes": [".flow/runs/demo"], "write_scopes": [".flow/runs/demo"], "read_only": False,
                "required_capabilities": [], "output": {"path": ".flow/runs/demo/output.md", "format": "markdown"},
                "success_criteria": ["output"], "claim_statuses": ["observed"],
                "coordination": {"mode": "serialized", "group": "test"},
            }],
            "shared_state": [],
            "reconciliation": {"artifact_path": ".flow/runs/demo/reconciliation.md", "status": "resolved", "claims": []},
            "verification": {"producer_assignments": ["producer"], "evidence_collector_assignment": "producer", "verifier_assignment": "producer", "independent": False, "artifact_path": ".flow/runs/demo/verification.md"},
        }
        (self.run_dir / "orchestration.json").write_text(json.dumps(manifest) + "\n")
        run = {
            "schema_version": 1, "protocol_revision": 2, "work_id": self.work_id,
            "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
            "state": "implementing", "phase": "implementing", "lane": "implement",
            "last_event": "start-implementation", "gates": {"start-implementation": "2026-01-01T00:00:00Z"},
            "artifacts": {
                "requirements": ".flow/runs/demo/requirements.md", "acceptance_criteria": ".flow/runs/demo/acceptance.md",
                "plan": ".flow/runs/demo/plan.md", "validation_plan": ".flow/runs/demo/validation.md",
                "orchestration_manifest": ".flow/runs/demo/orchestration.json",
            },
            "dispositions": {},
            "delivery": {"charter_digest": charter["digest"], "delivery_artifact_dir": delivery_relative,
                         "owner_status": "active", "owner_generation": 1, "lead_claim_digest": self.claim_digest},
        }
        (self.run_dir / "run.json").write_text(json.dumps(run) + "\n")
        (self.run_dir / "events.jsonl").write_text(json.dumps({"event": "start-implementation", "from": "plan_approved", "to": "implementing"}) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    @unittest.mock.patch("receipt_verify.verify_receipt")
    def test_authorized_handoff_preserves_both_events_and_is_idempotent(self, verify):
        verify.return_value = {"attempt_id": self.attempt_id, "exit_code": 0, "status": "completed", "checks": []}
        ok, payload, errors = handoff_to_review(self.work_id, self.attempt_id, 1, root=self.root)
        self.assertTrue(ok, errors)
        self.assertEqual(payload["state"], "reviewing")
        self.assertEqual([item["event"] for item in history(self.work_id, self.root)[-2:]],
                         ["mark-handback-ready", "start-review"])
        self.assertNotIn("review", payload["artifacts"])
        before = (self.run_dir / "events.jsonl").read_bytes()
        ok, payload, errors = handoff_to_review(self.work_id, self.attempt_id, 1, root=self.root)
        self.assertTrue(ok, errors)
        self.assertEqual(before, (self.run_dir / "events.jsonl").read_bytes())
        ok, _, errors = apply_transition(self.work_id, "request-refinement", root=self.root.resolve())
        self.assertTrue(ok, errors)
        (self.run_dir / "handoff" / "handback.json").unlink()
        ok, payload, errors = handoff_to_review(self.work_id, self.attempt_id, 1, root=self.root)
        self.assertFalse(ok)
        self.assertEqual(payload["state"], "implementing")
        self.assertIn("fresh execution attempt", errors[0])

    def test_missing_charter_authority_refuses_without_lifecycle_write(self):
        charter = dict(self.charter)
        charter["allowed_lifecycle_operations"] = []
        charter.pop("digest")
        from delivery_contracts import digest
        charter["digest"] = digest(charter)
        # Keep the active digest/path canonical while proving absence of permission.
        delivery_relative = f"delivery/{charter['digest']}"
        target = self.run_dir / delivery_relative
        target.mkdir(parents=True)
        (target / "delivery-charter.json").write_text(canonical(charter) + "\n")
        run_path = self.run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["delivery"]["charter_digest"] = charter["digest"]
        run["delivery"]["delivery_artifact_dir"] = delivery_relative
        run_path.write_text(json.dumps(run) + "\n")
        envelope_path = self.run_dir / "execution" / self.attempt_id / "envelope.json"
        envelope = json.loads(envelope_path.read_text())
        envelope["delivery_charter_digest"] = charter["digest"]
        envelope_path.write_text(json.dumps(envelope) + "\n")
        before = ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes())
        ok, _, errors = handoff_to_review(self.work_id, self.attempt_id, 1, root=self.root)
        self.assertFalse(ok)
        self.assertIn("does not authorize", errors[0])
        self.assertEqual(before, ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes()))

    @unittest.mock.patch("receipt_verify.verify_receipt")
    def test_older_successful_attempt_cannot_bypass_latest_attempt(self, verify):
        verify.return_value = {"attempt_id": "newer-failed-attempt", "exit_code": 1, "status": "failed", "checks": []}
        before = ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes())
        ok, _, errors = handoff_to_review(self.work_id, self.attempt_id, 1, root=self.root)
        self.assertFalse(ok)
        self.assertIn("latest sealed", errors[0])
        self.assertEqual(before, ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes()))

    @unittest.mock.patch("receipt_verify.verify_receipt")
    def test_receipt_backed_output_does_not_require_placeholder_file(self, verify):
        verify.return_value = {"attempt_id": self.attempt_id, "exit_code": 0, "status": "completed", "checks": []}
        manifest_path = self.run_dir / "orchestration.json"
        manifest = json.loads(manifest_path.read_text())
        missing = self.run_dir / "receipt-projected-manager.md"
        manifest["assignments"][0]["output"] = {
            "kind": "receipt-backed",
            "receipt_assignment_id": "producer",
            "path": missing.relative_to(self.root).as_posix(),
            "format": "markdown",
        }
        findings = validate_manifest(manifest, self.work_id, "handback", root=self.root)
        self.assertEqual([], findings)
        self.assertFalse(missing.exists())

        verify.return_value = {"attempt_id": self.attempt_id, "exit_code": 1, "status": "completed", "checks": []}
        findings = validate_manifest(manifest, self.work_id, "handback", root=self.root)
        self.assertIn("verified-receipt-output", {finding.rule for finding in findings})

        verify.return_value = {"attempt_id": self.attempt_id, "exit_code": 0, "status": "completed", "checks": []}
        manifest["assignments"][0]["output"]["receipt_assignment_id"] = "another-assignment"
        findings = validate_manifest(manifest, self.work_id, "handback", root=self.root)
        self.assertIn("receipt-assignment-binding", {finding.rule for finding in findings})

        receipt_path = self.run_dir / "execution" / self.attempt_id / "receipt.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["manager_calls"] = [{"status": "completed", "request": {"call_id": "manager-1", "phase": "plan"}}]
        receipt_path.write_text(json.dumps(receipt) + "\n")
        assignment = manifest["assignments"][0]
        assignment["id"] = "magentic-manager"
        assignment["role"] = "delivery-lead"
        assignment["output"]["receipt_assignment_id"] = "magentic-manager"
        findings = validate_manifest(manifest, self.work_id, "handback", root=self.root)
        self.assertEqual([], findings)
