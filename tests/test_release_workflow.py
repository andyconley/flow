"""Integration and workflow-contract tests for the automated release gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
GATE_PATH = REPO_ROOT / "scripts" / "release_gate.py"
CANDIDATE_PATH = REPO_ROOT / "scripts" / "release_candidate.py"
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_candidate  # noqa: E402
sys.path.pop(0)


def load_gate():
    spec = importlib.util.spec_from_file_location("release_gate_workflow_test", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class ReleaseWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")

    def job_block(self, name: str, next_name: str | None) -> str:
        start = self.text.index(f"  {name}:\n")
        end = self.text.index(f"  {next_name}:\n", start) if next_name else len(self.text)
        return self.text[start:end]

    def test_four_jobs_are_ordered_and_dependent(self) -> None:
        positions = [self.text.index(f"  {name}:\n") for name in (
            "analyze", "validate-candidate", "publish", "verify-published",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("needs: analyze", self.job_block("validate-candidate", "publish"))
        self.assertIn("needs: [analyze, validate-candidate]", self.job_block("publish", "verify-published"))
        self.assertIn("needs: [analyze, validate-candidate, publish]", self.job_block("verify-published", None))

    def test_only_publish_has_write_permissions_and_token(self) -> None:
        header = self.text[:self.text.index("jobs:\n")]
        self.assertIn("permissions:\n  contents: read", header)
        analyze = self.job_block("analyze", "validate-candidate")
        candidate = self.job_block("validate-candidate", "publish")
        publish = self.job_block("publish", "verify-published")
        verify = self.job_block("verify-published", None)
        for read_only in (analyze, candidate, verify):
            self.assertNotIn("GITHUB_TOKEN", read_only)
            self.assertNotIn("contents: write", read_only)
        self.assertIn("contents: write", publish)
        self.assertIn("issues: write", publish)
        self.assertIn("pull-requests: write", publish)
        self.assertEqual(self.text.count("secrets.GITHUB_TOKEN"), 1)

    def test_exact_sha_and_no_release_conditions_are_explicit(self) -> None:
        analyze = self.job_block("analyze", "validate-candidate")
        candidate = self.job_block("validate-candidate", "publish")
        publish = self.job_block("publish", "verify-published")
        self.assertIn("ref: ${{ github.sha }}", analyze)
        self.assertIn("ref: ${{ needs.analyze.outputs.source_sha }}", candidate)
        self.assertIn("ref: ${{ needs.analyze.outputs.source_sha }}", publish)
        self.assertIn("needs.analyze.outputs.release_required == 'true'", candidate)
        self.assertIn("needs.validate-candidate.result == 'success'", publish)
        self.assertIn("needs.publish.result == 'success'", self.job_block("verify-published", None))
        self.assertEqual(self.text.count("persist-credentials: false"), 4)

    def test_preview_is_local_and_publication_is_single(self) -> None:
        self.assertEqual(self.text.count("FLOW_RELEASE_MODE: preview"), 2)
        self.assertEqual(self.text.count("FLOW_RELEASE_MODE: publish"), 1)
        self.assertEqual(self.text.count("name: Publish once"), 1)
        self.assertIn("repository_url: ${{ steps.mirror.outputs.repository_url }}", self.text)
        self.assertIn("verify-remote-baseline", self.text)
        self.assertIn("compare-analysis", self.text)

    def test_no_bypass_or_failure_tolerant_publication_constructs(self) -> None:
        forbidden = (
            "workflow_dispatch:",
            "continue-on-error",
            "always()",
            "git push --force",
            "git tag -d",
            "gh release delete",
        )
        for value in forbidden:
            with self.subTest(value=value):
                self.assertNotIn(value, self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_release_notes_are_data_not_shell_source(self) -> None:
        run_lines = [line for line in self.text.splitlines() if line.lstrip().startswith("run:")]
        self.assertFalse(any("new_release_notes" in line for line in run_lines))
        self.assertGreaterEqual(self.text.count("FLOW_RELEASE_NEW_RELEASE_NOTES:"), 3)

    def test_public_failure_is_named_repair_forward(self) -> None:
        verify = self.job_block("verify-published", None)
        self.assertIn("published verification failed", verify)
        self.assertIn("repair forward", verify)
        self.assertNotIn("publication prevented", verify.lower())


class CandidateRunnerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gate = load_gate()

    def test_injected_first_failure_retains_fail_fast_evidence(self) -> None:
        source_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
        previous_tag = subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"], cwd=REPO_ROOT, text=True
        ).strip()
        previous_commit = subprocess.check_output(
            ["git", "rev-parse", f"{previous_tag}^{{commit}}"], cwd=REPO_ROOT, text=True
        ).strip()
        previous_version = previous_tag.removeprefix("v")
        major, minor, _patch = (int(value) for value in previous_version.split("."))
        next_version = f"{major}.{minor + 1}.0"
        notes = "## Test\n\n* candidate mutation proof\n"
        env = {
            "FLOW_RELEASE_REQUIRED": "true",
            "FLOW_RELEASE_PREVIOUS_VERSION": previous_version,
            "FLOW_RELEASE_PREVIOUS_TAG": previous_tag,
            "FLOW_RELEASE_PREVIOUS_COMMIT": previous_commit,
            "FLOW_RELEASE_VERSION": next_version,
            "FLOW_RELEASE_TAG": f"v{next_version}",
            "FLOW_RELEASE_NOTES": notes,
            "FLOW_RELEASE_NEW_RELEASE_GIT_HEAD": source_sha,
            "FLOW_RELEASE_SOURCE_SHA": source_sha,
            "FLOW_RELEASE_REPOSITORY": "andyconley/flow",
            "FLOW_RELEASE_WORKFLOW": "test",
            "FLOW_RELEASE_RUN_ID": "1",
            "FLOW_RELEASE_RUN_ATTEMPT": "1",
            "FLOW_RELEASE_CREATED_AT": "2026-09-01T00:00:00Z",
        }
        plan = self.gate.plan_from_environment(env)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            plan_path = root / "release-plan.json"
            evidence_path = root / "release-evidence.json"
            self.gate.write_plan(plan_path, plan)
            result = subprocess.run(
                [
                    sys.executable,
                    str(CANDIDATE_PATH),
                    "--plan", str(plan_path),
                    "--output", str(evidence_path),
                    "--fail-check", "python-test-suite",
                    "--defer-exit",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                env=os.environ.copy(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            evidence = self.gate.load_evidence(evidence_path, plan=plan)
            self.assertEqual(evidence["overall_result"], "failed")
            self.assertEqual(evidence["checks"][0]["result"], "failed")
            self.assertTrue(all(check["result"] == "not_run" for check in evidence["checks"][1:]))
            self.assertTrue(all(check["exit_code"] is None for check in evidence["checks"][1:]))

    def test_doctor_contract_accepts_only_named_isolated_runner_warnings(self) -> None:
        allowed = {
            "ok": True,
            "errors": 0,
            "diagnostics": [
                {"id": "user.claude.runtime_smoke", "severity": "warning"},
                {"id": "user.codex.runtime_smoke", "severity": "warning"},
                {"id": "telemetry.usage.empty", "severity": "warning"},
                {"id": "telemetry.plugin_usage", "severity": "warning"},
            ],
        }
        with unittest.mock.patch.object(release_candidate, "_flow", return_value=(1, json.dumps(allowed))):
            code, output = release_candidate._doctor_check(Path("/isolated"))
        self.assertEqual(code, 0)
        self.assertIn("accepted by the release contract", output)

        allowed["diagnostics"].append({"id": "machine.config", "severity": "warning"})
        with unittest.mock.patch.object(release_candidate, "_flow", return_value=(1, json.dumps(allowed))):
            code, _output = release_candidate._doctor_check(Path("/isolated"))
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
