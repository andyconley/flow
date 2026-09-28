import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
import delivery_control  # noqa: E402
import runstate  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402


class DeliveryOwnerProjectionRegressionTests(unittest.TestCase):
    """A Delivery Lead control event must not become lifecycle history."""

    def test_attention_preserves_implementing_lifecycle_and_verify(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname).resolve()
            (root / ".git").mkdir()
            work_id = "owner-projection-regression"
            run_dir = root / ".flow" / "runs" / work_id
            run_dir.mkdir(parents=True)

            artifacts = {
                "requirements": "requirements.md",
                "acceptance_criteria": "acceptance.md",
                "shaper_intent": "shaper-intent.json",
                "solution": "solution.md",
                "orchestration_manifest": "orchestration.json",
            }
            bodies = {
                "requirements.md": "requirements\n",
                "acceptance.md": "acceptance\n",
                "shaper-intent.json": json.dumps(shaper_intent()) + "\n",
                "solution.md": "solution\n",
                "orchestration.json": "{}\n",
            }
            for name, body in bodies.items():
                (run_dir / name).write_text(body)

            run = {
                "schema_version": 1,
                "protocol_revision": 2,
                "work_id": work_id,
                "state": "solution_approved",
                "lane": "solution",
                "phase": "solution_approved",
                "updated_at": "2026-09-27T00:00:00Z",
                "created_at": "2026-09-27T00:00:00Z",
                "artifacts": {key: f".flow/runs/{work_id}/{value}" for key, value in artifacts.items()},
                "dispositions": {"risk": "owned"},
                "gates": {},
                "last_event": "approve-solution",
                "approved_artifact_digests": {
                    key: hashlib.sha256((run_dir / value).read_bytes()).hexdigest()
                    for key, value in artifacts.items()
                },
            }
            (run_dir / "run.json").write_text(json.dumps(run) + "\n")
            (run_dir / "events.jsonl").write_text(
                json.dumps({"event": "approve-solution", "to": "solution_approved"}) + "\n"
            )

            ok, _, errors = runstate.apply_transition(work_id, "start-plan", root=root)
            self.assertTrue(ok, errors)
            implementing = json.loads((run_dir / "run.json").read_text())
            implementing.update({
                "state": "implementing",
                "phase": "implementing",
                "lane": "implement",
                "last_event": "start-implementation",
            })
            (run_dir / "run.json").write_text(json.dumps(implementing) + "\n")
            with (run_dir / "events.jsonl").open("a") as history:
                history.write(json.dumps({"event": "approve-plan", "from": "planning", "to": "plan_approved"}) + "\n")
                history.write(json.dumps({"event": "start-implementation", "from": "plan_approved", "to": "implementing"}) + "\n")

            ok, controlled, errors = delivery_control.change_lead_claim(
                work_id, "attention", root=root, expected_generation=1
            )
            self.assertTrue(ok, errors)
            self.assertEqual(controlled["state"], "implementing")
            self.assertEqual(controlled["last_event"], "start-implementation")
            verified, messages, _ = runstate.verify(work_id, root=root)
            self.assertTrue(verified, messages)


if __name__ == "__main__":
    unittest.main()
