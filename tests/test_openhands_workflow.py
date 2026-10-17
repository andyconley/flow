"""Replacement contracts; optional SDK integration is in openhands_runtime_eval.py."""
import hashlib
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import openhands_config as config
import openhands_flow as flow
import runstate
from tests import verification_fixture


class OpenHandsWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / ".flow/runs/example"
        verification_fixture.prepare(self.root)
        self.args = Namespace(project_root=self.root, work_id="example", stage=None, disposition=[])

    def tearDown(self):
        self.temp.cleanup()

    def outputs(self, stage):
        for filename in config.OUTPUTS[stage].values():
            (self.directory / filename).write_text(f"Evidence for {stage}\n")
        verification_fixture.outputs(self.root, self.directory, stage, runstate.status("example", self.root))

    def test_delivery_lead_prompt_and_plan_approval_boundary(self):
        flow.initialize(self.args)
        self.outputs("define")
        self.args.stage = "define"
        flow.approve(self.args)
        flow._transition(self.root, "example", "start-solution")
        self.outputs("solution")
        self.args.stage = "solution"
        self.args.disposition = ["risk=accepted"]
        approved = flow.approve(self.args)
        self.assertEqual(approved["state"], "solution_approved")
        with self.assertRaises(config.RuntimeConfigurationError):
            flow._transition(self.root, "example", "start-implementation")
        planning = flow._transition(self.root, "example", "start-plan")
        prompt = flow._stage_prompt(self.root, self.directory, planning, "plan", "Plan the change")
        self.assertIn("solution", planning["artifacts"])
        self.assertIn("requirements", planning["artifacts"])
        self.assertIn("Planning basis: the approved solution takes precedence", prompt)
        self.assertNotIn("solution stage was skipped", prompt)
        self.assertIn("host assistant, who owns Delivery Lead coordination", prompt)
        self.assertNotIn("Act as Delivery Lead", prompt)
        self.assertIn("explicit plan approval", prompt)
        self.assertIn("Do not start implementation", prompt)
        self.outputs("plan")
        with self.assertRaises(config.RuntimeConfigurationError):
            flow._transition(self.root, "example", "start-implementation")
        self.args.stage = "plan"
        self.args.disposition = []
        task = self.root / "task.md"
        task.write_text("Plan the change")
        (self.root / ".flow/runtime.toml").write_text('default_profile="native"\n[profiles.native]\nkind="codex"\n')
        self.args.task_file = task
        self.args.role = self.args.profile = None
        handoff = flow.native_handoff(self.args)
        self.assertIn("As the host assistant, assume Delivery Lead coordination", Path(handoff["artifact"]).read_text())
        self.assertIn("explicit plan approval", Path(handoff["artifact"]).read_text())
        flow.approve(self.args)
        self.assertEqual(flow._transition(self.root, "example", "start-implementation")["state"], "implementing")

    def test_planning_from_approved_definition_keeps_host_specialist_boundary(self):
        flow.initialize(self.args)
        self.outputs("define")
        self.args.stage = "define"
        flow.approve(self.args)
        self.assertNotIn("solution", runstate.status("example", self.root)["artifacts"])
        task = self.root / "task.md"
        task.write_text("Plan from the approved definition")
        (self.root / ".flow/runtime.toml").write_text('default_profile="native"\n[profiles.native]\nkind="codex"\n')
        self.args.stage = "plan"
        self.args.task_file = task
        self.args.role = self.args.profile = None
        self.assertEqual(config.select(self.root, "plan").role, "lead-developer")
        result = flow.native_handoff(self.args)
        planning = runstate.status("example", self.root)
        self.assertEqual(planning["state"], "planning")
        specialist = flow._stage_prompt(self.root, self.directory, planning, "plan", task.read_text())
        self.assertIn("approved solution when available, otherwise the approved definition", specialist)
        self.assertIn("Planning basis: the approved definition; the optional solution stage was skipped", specialist)
        self.assertNotIn("Planning basis: the approved solution", specialist)
        self.assertIn("solution stage is optional", specialist)
        self.assertIn("executing specialist supplies technical expertise", specialist)
        self.assertNotIn("Act as Delivery Lead", specialist)
        self.assertNotIn("As the host assistant, assume", specialist)
        handoff = Path(result["artifact"]).read_text()
        self.assertIn("## Host coordination", handoff)
        self.assertIn("As the host assistant, assume Delivery Lead coordination", handoff)
        self.assertIn("do not transfer host ownership", handoff)
        role = config.select(self.root, "plan")
        self.assertIn(str(role.role_file), handoff)
        self.assertIn("only to a separately invoked specialist, not to the host assistant", handoff)
        self.assertNotIn(role.role_file.read_text(), handoff)
        self.assertNotIn("You are the **Lead Developer**", handoff)
        self.assertIn("explicit user approval before implementation", handoff)
        with self.assertRaises(config.RuntimeConfigurationError):
            flow._transition(self.root, "example", "start-implementation")

    def test_full_lifecycle_has_artifacts_without_legacy_orchestration(self):
        self.assertEqual(flow.initialize(self.args)["protocol_revision"], 3)
        for stage in ("define", "solution", "plan", "implement", "review"):
            self.args.stage = stage
            if stage != "define":
                start, state, _ = config.STAGES[stage]
                if runstate.status("example", self.root)["state"] != state:
                    flow._transition(self.root, "example", start)
            self.outputs(stage)
            self.args.disposition = ["risk=accepted"] if stage == "solution" else []
            flow.approve(self.args)
        self.args.disposition = ["memory=recorded", "capability_gaps=none"]
        self.assertEqual(flow.archive(self.args)["state"], "archived")
        ok, errors, payload = runstate.verify("example", self.root)
        self.assertTrue(ok, errors)
        self.assertFalse((self.directory / "execution/ledger.sqlite").exists())
        self.assertNotIn("orchestration_manifest", payload["artifacts"])
        self.assertIn("archive", payload["artifacts"])
        history = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        archived = next(event for event in history if event["event"] == "archive")
        self.assertEqual(archived["approved_artifact_digests"]["archive"], payload["approved_artifact_digests"]["archive"])

    def test_archive_enrichment_search_and_retry_preserve_approval_history(self):
        from archive_store import ensure_identity, ensure_ignore
        from archive_query import rebuild, search
        self.approved_through()
        ensure_ignore(self.root)
        ensure_identity(self.root)
        self.assertEqual(rebuild(self.root)["state"], "complete")
        (self.directory / "archive.md").write_text("# Archive Summary\n\n## Work Closed\n\nZephyr accounting repair completed with searchable evidence.\n")
        self.args.disposition = ["memory=recorded", "capability_gaps=none"]
        result = flow.archive(self.args)
        self.assertFalse(result["enrichment_diagnostics"], result)
        self.assertTrue((self.directory / "abstract.json").exists())
        import archive_preflight
        # A new CI machine has no receipt. Exercise the real probe in a
        # disposable home instead of depending on the developer's machine.
        with patch.object(archive_preflight.Path, "home", return_value=self.root / "machine-home"):
            self.assertEqual(archive_preflight.probe()["state"], "available")
            found = search(self.root, "Zephyr accounting")
        self.assertTrue(found["hits"], found)
        before = {name: (self.directory / name).read_bytes() for name in ("run.json", "events.jsonl", "archive.md", "abstract.json")}
        retry = flow.archive(self.args)
        self.assertFalse(retry["enrichment_diagnostics"], retry)
        for name, raw in before.items():
            self.assertEqual((self.directory / name).read_bytes(), raw, name)
        self.assertTrue(runstate.verify("example", self.root)[0])
        self.args.disposition = ["memory=changed", "capability_gaps=none"]
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "cannot amend dispositions"):
            flow.archive(self.args)

    def test_archive_generation_failure_is_retryable_without_reclosing(self):
        import archive_service
        self.approved_through()
        self.args.disposition = ["memory=recorded", "capability_gaps=none"]
        with patch.object(archive_service, "build_envelope", side_effect=OSError("injected write failure")):
            first = flow.archive(self.args)
        self.assertEqual(first["state"], "archived")
        self.assertTrue(first["enrichment_diagnostics"])
        before = (self.directory / "events.jsonl").read_bytes()
        retried = flow.archive(self.args)
        self.assertFalse(retried["enrichment_diagnostics"], retried)
        self.assertTrue((self.directory / "abstract.json").exists())
        self.assertEqual((self.directory / "events.jsonl").read_bytes(), before)

    def approved_through(self, last_stage="review"):
        flow.initialize(self.args)
        for stage in ("define", "solution", "plan", "implement", "review"):
            self.args.stage = stage
            start, state, _ = config.STAGES[stage]
            if runstate.status("example", self.root)["state"] != state:
                flow._transition(self.root, "example", start)
            self.outputs(stage)
            self.args.disposition = ["risk=accepted"] if stage == "solution" else []
            flow.approve(self.args)
            if stage == last_stage:
                return runstate.status("example", self.root)

    def test_every_approved_stage_records_byte_digests_and_journal_evidence(self):
        payload = self.approved_through()
        expected = {name for outputs in config.OUTPUTS.values() for name in outputs} | {"verification_plan", "verification"}
        self.assertEqual(set(payload["approved_artifact_digests"]), expected)
        for name in expected:
            self.assertEqual(payload["approved_artifact_digests"][name],
                             hashlib.sha256((self.root / payload["artifacts"][name]).read_bytes()).hexdigest())
        events = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        for event in events:
            if event["event"] in {"approve-definition", "approve-solution", "approve-plan", "mark-handback-ready", "accept-review"}:
                self.assertTrue(event["approved_artifact_digests"], event)

    def test_changed_approved_artifacts_block_verification_continuation_and_archive(self):
        payload = self.approved_through()
        self.args.disposition = ["memory=recorded", "capability_gaps=none"]
        for name in ("requirements", "solution", "plan", "review"):
            path = self.root / payload["artifacts"][name]
            original = path.read_bytes()
            with self.subTest(artifact=name):
                path.write_bytes(original + b"Unapproved change\n")
                ok, errors, _ = runstate.verify("example", self.root)
                self.assertFalse(ok)
                self.assertTrue(any(name in error and "changed after approval" in error for error in errors), errors)
                before = (self.directory / "run.json").read_bytes()
                with self.assertRaisesRegex(config.RuntimeConfigurationError, "changed after approval"):
                    flow._run(self.root, "example")
                with self.assertRaisesRegex(config.RuntimeConfigurationError, "changed after approval"):
                    flow.archive(self.args)
                self.assertEqual((self.directory / "run.json").read_bytes(), before)
                self.assertFalse((self.directory / "archive.md").exists())
                path.write_bytes(original)
        self.assertTrue(runstate.verify("example", self.root)[0])

    def test_hashless_approved_native_run_is_inspectable_without_silent_reapproval(self):
        payload = self.approved_through("define")
        payload.pop("approved_artifact_digests")
        runstate._write_run("example", payload, self.root)
        before = (self.directory / "run.json").read_bytes()
        self.assertEqual(runstate.status("example", self.root)["state"], "definition_approved")
        inspected = flow.show(self.args)
        self.assertEqual(inspected["state"], "definition_approved")
        self.assertFalse(inspected["approval_integrity"]["ok"])
        self.assertIn("unsealed approved artifact", flow._summary(inspected))
        ok, errors, _ = runstate.verify("example", self.root)
        self.assertFalse(ok)
        self.assertTrue(any("unsealed approved artifact" in error for error in errors), errors)
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "unsealed approved artifact"):
            flow._run(self.root, "example")
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "unsealed approved artifact"):
            flow._transition(self.root, "example", "start-solution")
        self.assertEqual((self.directory / "run.json").read_bytes(), before)

    def test_same_bytes_replaced_by_symlink_do_not_keep_approval(self):
        payload = self.approved_through("define")
        path = self.root / payload["artifacts"]["requirements"]
        replacement = self.directory / "replacement.md"
        replacement.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(replacement.name)
        ok, errors, _ = runstate.verify("example", self.root)
        self.assertFalse(ok)
        self.assertTrue(any("requirements" in error and "regular file" in error for error in errors), errors)
        with self.assertRaisesRegex(config.RuntimeConfigurationError, "regular file"):
            flow._run(self.root, "example")

    def test_authorized_refinement_releases_only_implementation_seals(self):
        payload = self.approved_through("implement")
        earlier = {name: digest for name, digest in payload["approved_artifact_digests"].items()
                   if name not in {"implementation_evidence", "handback", "review", "verification"}}
        self.outputs("review")
        proof = self.directory / "failure.txt"
        proof.write_text("Reviewer found a fixture concern")
        refined = flow._transition(self.root, "example", "request-refinement", dispositions={
            "failed_check": "behavior", "specialist": "lead-developer", "narrowed_scope": "fixture concern",
            "reason": "review finding", "failure_evidence": proof.relative_to(self.root).as_posix()})
        self.assertEqual(refined["approved_artifact_digests"], earlier)
        self.assertNotIn("mark-handback-ready", refined["gates"])
        self.assertNotIn("accept-review", refined["gates"])
        for filename in config.OUTPUTS["implement"].values():
            (self.directory / filename).write_text("Revised implementation evidence\n")
        verification_fixture.outputs(self.root, self.directory, "implement", refined)
        self.args.stage = "implement"
        resumed = flow.approve(self.args)
        self.assertEqual(resumed["state"], "reviewing")
        for name, digest in earlier.items():
            self.assertEqual(resumed["approved_artifact_digests"][name], digest)
        for name in config.OUTPUTS["implement"]:
            self.assertNotEqual(resumed["approved_artifact_digests"][name], payload["approved_artifact_digests"][name])
        self.assertTrue(runstate.verify("example", self.root)[0])

    def test_implementation_approval_retries_after_interrupted_review_transition(self):
        self.approved_through("plan")
        flow._transition(self.root, "example", "start-implementation")
        self.outputs("implement")
        self.args.stage = "implement"
        self.args.disposition = []
        original = flow._transition
        def interrupt_review(root, work_id, event, **kwargs):
            if event == "start-review":
                raise KeyboardInterrupt("interrupted after durable handback")
            return original(root, work_id, event, **kwargs)
        with patch.object(flow, "_transition", side_effect=interrupt_review):
            with self.assertRaises(KeyboardInterrupt):
                flow.approve(self.args)
        self.assertEqual(runstate.status("example", self.root)["state"], "handback_ready")
        self.assertEqual(flow.approve(self.args)["state"], "reviewing")
        events = [json.loads(line) for line in (self.directory / "events.jsonl").read_text().splitlines()]
        self.assertEqual(sum(event["event"] == "mark-handback-ready" for event in events), 1)
        self.assertEqual(sum(event["event"] == "start-review" for event in events), 1)

    def test_missing_outputs_do_not_advance(self):
        flow.initialize(self.args)
        before = (self.directory / "run.json").read_bytes()
        with self.assertRaises(config.RuntimeConfigurationError):
            flow.approve(self.args)
        self.assertEqual((self.directory / "run.json").read_bytes(), before)

    def test_artifact_cannot_escape_run(self):
        flow.initialize(self.args)
        outside = self.root / "outside.md"
        outside.write_text("wrong scope")
        (self.directory / "requirements.md").symlink_to(outside)
        (self.directory / "acceptance-criteria.md").write_text("criteria")
        with self.assertRaises(config.RuntimeConfigurationError):
            flow.approve(self.args)
        self.assertEqual(runstate.status("example", self.root)["state"], "defining")

    def test_native_handoff_preserves_subscription_and_does_not_launch(self):
        flow.initialize(self.args)
        task = self.root / "task.md"
        task.write_text("Review code")
        runtime = self.root / ".flow/runtime.toml"
        runtime.write_text('default_profile="native"\n[profiles.native]\nkind="codex"\n')
        self.args.task_file = task
        self.args.role = self.args.profile = None
        result = flow.native_handoff(self.args)
        self.assertEqual(result["provider"], "codex")
        self.assertIn("permission settings", Path(result["artifact"]).read_text())
        self.assertNotIn("sessions", runstate.status("example", self.root))

    def test_native_access_decision_precedes_execution_and_state_mutation(self):
        flow.initialize(self.args)
        task = self.root / "task.md"
        task.write_text("Do not launch without scoped access approval")
        (self.root / ".flow/runtime.toml").write_text('default_profile="native"\n[profiles.native]\nkind="codex"\npermission_requests="interactive"\n')
        self.args.task_file = task
        self.args.role = self.args.profile = None
        self.args.stage = "define"
        before = (self.directory / "run.json").read_bytes()
        with patch("openhands_flow.Terminal", side_effect=OSError("no tty")), self.assertRaisesRegex(config.RuntimeConfigurationError, "human controlling terminal"):
            flow.execute(self.args)
        self.assertEqual(before, (self.directory / "run.json").read_bytes())
        import openhands_runtime
        selection = config.select(self.root, "define")
        agent = openhands_runtime.build_native_agent(selection, self.root)
        self.assertIn("acp_permissions.py", agent.acp_command[1])
        self.assertEqual(agent.acp_session_mode, "agent")

    def test_sdk_error_status_is_cli_failure(self):
        handler = flow._handler(lambda _: {"work_id": "example", "stage": "define",
                                          "session": {"status": "error", "conversation_id": "test"}})
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(handler(Namespace(json=True)), 1)

    def test_legacy_runs_are_not_migrated_or_resumed(self):
        runstate.apply_transition("example", "start-definition", root=self.root)
        before = (self.directory / "run.json").read_bytes()
        with self.assertRaises(config.RuntimeConfigurationError):
            flow._run(self.root, "example")
        self.assertEqual(before, (self.directory / "run.json").read_bytes())

    def test_overlay_and_different_specialist_profiles(self):
        user = self.root / "user"
        user.mkdir()
        (user / "runtime.toml").write_text('default_profile="cpu"\n[profiles.cpu]\nkind="local"\nmodel="openai/coder"\nbase_url="http://localhost:8000/v1"\n')
        (self.root / ".flow").mkdir()
        (self.root / ".flow/runtime.toml").write_text('[profiles.gpu]\nkind="local"\nmodel="ollama_chat/coder"\nbase_url="http://self-hosted:11434"\nmax_input_tokens=16384\n[roles.quality-reviewer]\nprofile="gpu"\n')
        self.assertEqual(config.select(self.root, "implement", user_overlay=user).profile, "cpu")
        self.assertEqual(config.select(self.root, "review", user_overlay=user).profile, "gpu")

    def test_local_profiles_cannot_fall_back_to_vendor_api_or_native_key(self):
        for change in ({"base_url": "https://api.openai.com/v1"}, {"api_key_env": "ANTHROPIC_API_KEY"}, {"api_key": "not-allowed"}, {"base_url": ""}):
            provider = {"kind": "local", "model": "openai/coder", "base_url": "http://localhost:8000/v1", **change}
            with self.subTest(change=change), self.assertRaises(config.RuntimeConfigurationError):
                config.select(self.root, "define", config={"default_profile": "test", "profiles": {"test": provider}})


if __name__ == "__main__":
    unittest.main()
