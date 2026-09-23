import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
import delivery_control  # noqa: E402
import runstate  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402


class DeliveryControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()
        self.work_id = "delivery-demo"
        self.run_dir = self.root / ".flow" / "runs" / self.work_id
        self.run_dir.mkdir(parents=True)
        self._write("requirements.md", "requirements\n")
        self._write("acceptance.md", "acceptance\n")
        self._write("shaper-intent.json", json.dumps(shaper_intent()) + "\n")
        payload = {
            "schema_version": 1, "protocol_revision": 2, "work_id": self.work_id,
            "state": "solution_approved", "lane": "solution", "phase": "solution_approved",
            "updated_at": "2026-09-22T00:00:00Z", "created_at": "2026-09-22T00:00:00Z",
            "artifacts": {
                "requirements": f".flow/runs/{self.work_id}/requirements.md",
                "acceptance_criteria": f".flow/runs/{self.work_id}/acceptance.md",
                "shaper_intent": f".flow/runs/{self.work_id}/shaper-intent.json",
            }, "dispositions": {"risk": "owned"}, "gates": {}, "last_event": "approve-solution",
            "approved_artifact_digests": {
                "shaper_intent": hashlib.sha256((self.run_dir / "shaper-intent.json").read_bytes()).hexdigest()
            },
        }
        (self.run_dir / "run.json").write_text(json.dumps(payload) + "\n")
        (self.run_dir / "events.jsonl").write_text(json.dumps({"event": "approve-solution", "to": "solution_approved"}) + "\n")

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name, body):
        (self.run_dir / name).write_text(body)

    def test_start_plan_is_atomic_idempotent_and_binds_authority(self):
        ok, run, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        self.assertEqual(run["state"], "planning")
        delivery = run["delivery"]
        self.assertEqual(delivery["owner_generation"], 1)
        self.assertEqual(delivery["owner_status"], "active")
        artifact_dir = self.run_dir / run["delivery"]["delivery_artifact_dir"]
        for name in ("shaper-contract.json", "delivery-charter.json", "handoff.json", "lead-claim.json"):
            self.assertTrue((artifact_dir / name).is_file())
        before = (self.run_dir / "run.json").read_bytes()
        ok, replay, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        self.assertEqual(replay["delivery"], delivery)
        self.assertEqual((self.run_dir / "run.json").read_bytes(), before)

    def test_changed_approved_source_refuses_replay_without_authority_change(self):
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        before = (self.run_dir / "run.json").read_bytes()
        self._write("requirements.md", "changed requirements\n")
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertFalse(ok)
        self.assertIn("source bytes changed", errors[0])
        self.assertEqual((self.run_dir / "run.json").read_bytes(), before)

    def test_changed_shaper_intent_after_approval_refuses_start_plan(self):
        before = ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes())
        self._write("shaper-intent.json", json.dumps(shaper_intent({
            "lead-developer": "a" * 64, "quality-reviewer": "b" * 64, "test-engineer": "c" * 64,
        })) + "\n")
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertFalse(ok)
        self.assertIn("changed after definition approval", errors[0])
        self.assertEqual(before[0], (self.run_dir / "run.json").read_bytes())
        self.assertEqual(before[1], (self.run_dir / "events.jsonl").read_bytes())

    def test_staged_artifacts_are_inert_if_commit_never_happens(self):
        ok, _, errors = delivery_control.start_plan(self.work_id, root=self.root, failure_point="after-staging")
        self.assertFalse(ok)
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["state"], "solution_approved")
        self.assertNotIn("delivery", run)
        self.assertTrue(any((self.run_dir / "delivery").rglob("delivery-charter.json")))

    def test_after_commit_replay_reconciles_history(self):
        ok, run, errors = delivery_control.start_plan(self.work_id, root=self.root, failure_point="after-run-replace")
        self.assertTrue(ok, errors)
        self.assertEqual(run["state"], "planning")
        self.assertEqual(len((self.run_dir / "events.jsonl").read_text().splitlines()), 1)
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        events = [json.loads(line) for line in (self.run_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual([event["event"] for event in events].count("start-plan"), 1)

    def test_explicit_resume_increments_generation_and_fences_stale_owner(self):
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        ok, paused, errors = delivery_control.change_lead_claim(
            self.work_id, "attention", root=self.root, expected_generation=1
        )
        self.assertTrue(ok, errors)
        self.assertEqual(paused["delivery"]["owner_status"], "attention_required")
        ok, resumed, errors = delivery_control.change_lead_claim(
            self.work_id, "resume", root=self.root, owner="codex:operator", expected_generation=1
        )
        self.assertTrue(ok, errors)
        self.assertEqual(resumed["delivery"]["owner_generation"], 2)
        ok, _, errors = delivery_control.change_lead_claim(
            self.work_id, "release", root=self.root, expected_generation=1
        )
        self.assertFalse(ok)
        self.assertIn("stale", errors[0])

    def test_revision_two_missing_source_fails_closed_without_lifecycle_write(self):
        (self.run_dir / "requirements.md").unlink()
        before = ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes())
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertFalse(ok)
        self.assertIn("unavailable", errors[0])
        self.assertEqual(before, ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes()))

    def test_other_run_source_path_is_refused_without_lifecycle_write(self):
        run = json.loads((self.run_dir / "run.json").read_text())
        run["artifacts"]["requirements"] = ".flow/runs/other/requirements.md"
        (self.run_dir / "run.json").write_text(json.dumps(run) + "\n")
        before = ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes())
        ok, _, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertFalse(ok)
        self.assertIn("outside the current run", errors[0])
        self.assertEqual(before, ((self.run_dir / "run.json").read_bytes(), (self.run_dir / "events.jsonl").read_bytes()))

    def test_changed_source_after_inert_stage_uses_new_authority_directory(self):
        ok, _, _ = delivery_control.start_plan(self.work_id, root=self.root, failure_point="after-staging")
        self.assertFalse(ok)
        self._write("requirements.md", "corrected requirements\n")
        ok, run, errors = runstate.apply_transition(self.work_id, "start-plan", root=self.root)
        self.assertTrue(ok, errors)
        self.assertTrue((self.run_dir / run["delivery"]["delivery_artifact_dir"]).is_dir())
        self.assertEqual(len([path for path in (self.run_dir / "delivery").iterdir() if path.is_dir()]), 2)
