import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_gate.py"
SPEC = importlib.util.spec_from_file_location("release_gate_under_test", SCRIPT)
release_gate = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(release_gate)

SOURCE_SHA = "a" * 40
PREVIOUS_SHA = "b" * 40
RUNNER_SHA = SOURCE_SHA
LOG_SHA = "d" * 64


def release_environment(notes="## Features\n\n* safely ship $(touch SHOULD_NOT_EXIST); `echo nope`\n"):
    return {
        "FLOW_RELEASE_REQUIRED": "true",
        "FLOW_RELEASE_TYPE": "minor",
        "FLOW_RELEASE_VERSION": "0.22.0",
        "FLOW_RELEASE_TAG": "v0.22.0",
        "FLOW_RELEASE_NOTES": notes,
        "FLOW_RELEASE_ENTRY_COUNT": "1",
        "FLOW_RELEASE_SOURCE_SHA": SOURCE_SHA,
        "FLOW_RELEASE_PREVIOUS_VERSION": "0.21.0",
        "FLOW_RELEASE_PREVIOUS_TAG": "v0.21.0",
        "FLOW_RELEASE_PREVIOUS_COMMIT": PREVIOUS_SHA,
        "FLOW_RELEASE_REPOSITORY": "andyconley/flow",
        "FLOW_RELEASE_WORKFLOW": "Release",
        "FLOW_RELEASE_RUN_ID": "1234",
        "FLOW_RELEASE_RUN_ATTEMPT": "1",
        "FLOW_RELEASE_CREATED_AT": "2026-09-01T12:00:00Z",
    }


def valid_plan():
    return release_gate.plan_from_environment(release_environment())


def valid_evidence(plan=None):
    plan = plan or valid_plan()
    checks = [
        {
            "id": check_id,
            "result": "passed",
            "exit_code": 0,
            "duration_ms": index,
            "log_path": f"logs/{check_id}.log",
            "log_sha256": LOG_SHA,
        }
        for index, check_id in enumerate(release_gate.STABLE_CHECK_IDS)
    ]
    return {
        "schema_version": 1,
        "plan_digest": release_gate.canonical_digest(plan),
        "source_sha": SOURCE_SHA,
        "candidate_version": "0.22.0",
        "candidate_tag": "v0.22.0",
        "candidate_repository": {
            "url": "file:///tmp/isolated-flow.git",
            "main_sha": SOURCE_SHA,
            "tag_sha": SOURCE_SHA,
        },
        "runner_sha": RUNNER_SHA,
        "checks": checks,
        "overall_result": "passed",
    }


class PlanContractTests(unittest.TestCase):
    def test_normalizes_release_and_hashes_literal_notes(self):
        env = release_environment()
        plan = release_gate.plan_from_environment(env)
        predicted = plan["predicted_release"]
        self.assertTrue(plan["release_required"])
        self.assertEqual(predicted["notes"], env["FLOW_RELEASE_NOTES"])
        self.assertEqual(
            predicted["notes_sha256"],
            hashlib.sha256(env["FLOW_RELEASE_NOTES"].encode()).hexdigest(),
        )

    def test_action_output_aliases_are_supported(self):
        env = release_environment()
        env["FLOW_RELEASE_PUBLISHED"] = env.pop("FLOW_RELEASE_REQUIRED")
        for short, action in (
            ("TYPE", "NEW_RELEASE_TYPE"),
            ("VERSION", "NEW_RELEASE_VERSION"),
            ("TAG", "NEW_RELEASE_GIT_TAG"),
            ("NOTES", "NEW_RELEASE_NOTES"),
        ):
            env[f"FLOW_RELEASE_{action}"] = env.pop(f"FLOW_RELEASE_{short}")
        self.assertEqual(release_gate.plan_from_environment(env)["predicted_release"]["version"], "0.22.0")

    def test_no_release_has_no_prediction(self):
        env = release_environment()
        env["FLOW_RELEASE_REQUIRED"] = "false"
        for key in list(env):
            if key in {"FLOW_RELEASE_TYPE", "FLOW_RELEASE_VERSION", "FLOW_RELEASE_TAG", "FLOW_RELEASE_NOTES", "FLOW_RELEASE_ENTRY_COUNT"}:
                del env[key]
        plan = release_gate.plan_from_environment(env)
        self.assertFalse(plan["release_required"])
        self.assertIsNone(plan["predicted_release"])

    def test_malformed_release_boolean_is_rejected(self):
        env = release_environment()
        env["FLOW_RELEASE_REQUIRED"] = "yes"
        with self.assertRaises(release_gate.ContractError):
            release_gate.plan_from_environment(env)

    def test_empty_notes_are_rejected(self):
        with self.assertRaisesRegex(release_gate.ContractError, "notes"):
            release_gate.plan_from_environment(release_environment("  \n"))

    def test_malformed_no_release_cannot_hide_prediction(self):
        plan = valid_plan()
        plan["release_required"] = False
        with self.assertRaisesRegex(release_gate.ContractError, "must be null"):
            release_gate.validate_plan(plan)

    def test_canonical_digest_is_key_order_independent_and_drift_sensitive(self):
        plan = valid_plan()
        reordered = {key: plan[key] for key in reversed(plan)}
        self.assertEqual(release_gate.canonical_digest(plan), release_gate.canonical_digest(reordered))
        changed = copy.deepcopy(plan)
        changed["source_sha"] = "e" * 40
        self.assertNotEqual(release_gate.canonical_digest(plan), release_gate.canonical_digest(changed))

    def test_canonical_writer_digest_matches_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.json"
            digest = release_gate.write_plan(path, valid_plan())
            self.assertEqual(digest, release_gate.file_sha256(path))
            self.assertTrue(path.read_bytes().endswith(b"\n"))

    def test_shell_metacharacters_are_never_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / "SHOULD_NOT_EXIST"
            notes = f"## Fixes\n\n* $(touch {marker}); `touch {marker}`; $HOME; ' quote"
            plan = release_gate.plan_from_environment(release_environment(notes))
            self.assertEqual(plan["predicted_release"]["notes"], notes)
            self.assertFalse(marker.exists())

    def test_repeated_analysis_rejects_each_protected_field(self):
        plan = valid_plan()
        mutations = {
            "source_sha": lambda value: value.update(source_sha="e" * 40),
            "previous_release": lambda value: value["previous_release"].update(commit="e" * 40),
            "release_required": lambda value: (value.update(release_required=False), value.update(predicted_release=None)),
            "predicted_release": lambda value: value["predicted_release"].update(type="patch"),
            "policy": lambda value: value["policy"].update(identity="e" * 64),
        }
        for field, mutate in mutations.items():
            with self.subTest(field=field):
                repeated = copy.deepcopy(plan)
                mutate(repeated)
                if field == "policy":
                    with self.assertRaises(release_gate.ContractError):
                        release_gate.compare_analysis(plan, repeated)
                else:
                    with self.assertRaisesRegex(release_gate.ContractError, "drifted"):
                        release_gate.compare_analysis(plan, repeated)


class EvidenceContractTests(unittest.TestCase):
    def test_complete_evidence_validates_against_plan(self):
        plan = valid_plan()
        self.assertEqual(release_gate.validate_evidence(valid_evidence(plan), plan=plan)["overall_result"], "passed")

    def test_missing_duplicate_unknown_or_reordered_checks_are_rejected(self):
        plan = valid_plan()
        mutations = []
        missing = valid_evidence(plan)
        missing["checks"].pop()
        mutations.append(missing)
        duplicate = valid_evidence(plan)
        duplicate["checks"][1]["id"] = duplicate["checks"][0]["id"]
        mutations.append(duplicate)
        unknown = valid_evidence(plan)
        unknown["checks"][0]["id"] = "surprise"
        mutations.append(unknown)
        reordered = valid_evidence(plan)
        reordered["checks"][0], reordered["checks"][1] = reordered["checks"][1], reordered["checks"][0]
        mutations.append(reordered)
        for evidence in mutations:
            with self.subTest(ids=[item["id"] for item in evidence["checks"]]):
                with self.assertRaisesRegex(release_gate.ContractError, "stable check ID"):
                    release_gate.validate_evidence(evidence, plan=plan)

    def test_unsafe_log_path_is_rejected(self):
        evidence = valid_evidence()
        evidence["checks"][0]["log_path"] = "../secret"
        with self.assertRaisesRegex(release_gate.ContractError, "safe relative"):
            release_gate.validate_evidence(evidence)

    def test_runner_must_be_the_planned_source(self):
        evidence = valid_evidence()
        evidence["runner_sha"] = "c" * 40
        with self.assertRaisesRegex(release_gate.ContractError, "runner_sha"):
            release_gate.validate_evidence(evidence)

    def test_uploaded_logs_must_exist_and_match_their_digests(self):
        plan = valid_plan()
        evidence = valid_evidence(plan)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for check in evidence["checks"]:
                log = root / check["log_path"]
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(check["id"], encoding="utf-8")
                check["log_sha256"] = release_gate.file_sha256(log)
            release_gate.validate_evidence(evidence, plan=plan, logs_root=root)
            first_log = root / evidence["checks"][0]["log_path"]
            first_original = first_log.read_text(encoding="utf-8")
            first_log.write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(release_gate.ContractError, "log digest mismatch"):
                release_gate.validate_evidence(evidence, plan=plan, logs_root=root)
            first_log.write_text(first_original, encoding="utf-8")
            (root / evidence["checks"][1]["log_path"]).unlink()
            with self.assertRaisesRegex(release_gate.ContractError, "log file is missing"):
                release_gate.validate_evidence(evidence, plan=plan, logs_root=root)

    def test_uploaded_log_symlink_cannot_escape_evidence_root(self):
        plan = valid_plan()
        evidence = valid_evidence(plan)
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as outside:
            root = Path(temp)
            for check in evidence["checks"]:
                log = root / check["log_path"]
                log.parent.mkdir(parents=True, exist_ok=True)
                log.write_text(check["id"], encoding="utf-8")
                check["log_sha256"] = release_gate.file_sha256(log)
            escaped = Path(outside) / "escaped.log"
            escaped.write_text("outside", encoding="utf-8")
            first = root / evidence["checks"][0]["log_path"]
            first.unlink()
            first.symlink_to(escaped)
            evidence["checks"][0]["log_sha256"] = release_gate.file_sha256(escaped)
            with self.assertRaisesRegex(release_gate.ContractError, "escapes the evidence root"):
                release_gate.validate_evidence(evidence, plan=plan, logs_root=root)

    def test_each_failed_check_blocks_fake_publisher(self):
        plan = valid_plan()
        for index, check_id in enumerate(release_gate.STABLE_CHECK_IDS):
            with self.subTest(check_id=check_id):
                evidence = valid_evidence(plan)
                evidence["checks"][index]["result"] = "failed"
                evidence["checks"][index]["exit_code"] = 1
                for later in evidence["checks"][index + 1:]:
                    later["result"] = "not_run"
                    later["exit_code"] = None
                    later["duration_ms"] = 0
                evidence["overall_result"] = "failed"
                calls = []
                external_state = {"main": SOURCE_SHA, "tags": [], "releases": [], "changelog": "unchanged"}
                before = copy.deepcopy(external_state)
                with self.assertRaisesRegex(release_gate.ContractError, "did not pass"):
                    release_gate.authorize_publication(
                        plan,
                        evidence,
                        copy.deepcopy(plan),
                        lambda: (calls.append("publish"), external_state["tags"].append("v0.22.0")),
                    )
                self.assertEqual(calls, [])
                self.assertEqual(external_state, before)

    def test_evidence_rejects_a_check_running_after_failure(self):
        evidence = valid_evidence()
        evidence["checks"][0]["result"] = "failed"
        evidence["checks"][0]["exit_code"] = 1
        evidence["overall_result"] = "failed"
        with self.assertRaisesRegex(release_gate.ContractError, "cannot run after"):
            release_gate.validate_evidence(evidence)

    def test_plan_digest_and_candidate_identity_drift_block_publisher(self):
        plan = valid_plan()
        for field, value in (
            ("plan_digest", "e" * 64),
            ("source_sha", "e" * 40),
            ("candidate_version", "0.22.1"),
            ("candidate_tag", "v0.22.1"),
        ):
            with self.subTest(field=field):
                evidence = valid_evidence(plan)
                evidence[field] = value
                calls = []
                with self.assertRaises(release_gate.ContractError):
                    release_gate.authorize_publication(plan, evidence, copy.deepcopy(plan), lambda: calls.append("publish"))
                self.assertEqual(calls, [])

    def test_valid_evidence_calls_publisher_once(self):
        plan = valid_plan()
        calls = []
        result = release_gate.authorize_publication(plan, valid_evidence(plan), copy.deepcopy(plan), lambda: calls.append("publish") or "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(calls, ["publish"])


class ReleaseCommitShapeTests(unittest.TestCase):
    def valid_shape(self):
        return {
            "tag": "v0.22.0",
            "release_commit": "e" * 40,
            "parents": [SOURCE_SHA],
            "branch_tip": "e" * 40,
            "changes": [{"status": "M", "path": "CHANGELOG.md"}],
            "subject": "chore(release): 0.22.0 [skip ci]",
            "changelog_has_section": True,
        }

    def test_exact_generated_commit_shape_passes(self):
        release_gate.validate_release_commit_shape(valid_plan(), self.valid_shape())

    def test_wrong_parent_extra_file_subject_and_branch_tip_fail(self):
        mutations = (
            lambda shape: shape.update(parents=["f" * 40]),
            lambda shape: shape["changes"].append({"status": "M", "path": "README.md"}),
            lambda shape: shape.update(subject="chore: surprise"),
            lambda shape: shape.update(branch_tip="f" * 40),
        )
        for mutate in mutations:
            shape = self.valid_shape()
            mutate(shape)
            with self.assertRaises(release_gate.ContractError):
                release_gate.validate_release_commit_shape(valid_plan(), shape)


class PublicationResultTests(unittest.TestCase):
    def publication_environment(self):
        plan = valid_plan()
        return {
            "FLOW_RELEASE_NEW_RELEASE_PUBLISHED": "true",
            "FLOW_RELEASE_NEW_RELEASE_VERSION": plan["predicted_release"]["version"],
            "FLOW_RELEASE_NEW_RELEASE_GIT_TAG": plan["predicted_release"]["tag"],
            "FLOW_RELEASE_NEW_RELEASE_GIT_HEAD": "e" * 40,
            "FLOW_RELEASE_NEW_RELEASE_NOTES": plan["predicted_release"]["notes"],
        }

    def test_structured_publication_result_matches_plan(self):
        plan = valid_plan()
        result = release_gate.publication_from_environment(plan, self.publication_environment())
        self.assertEqual(result, {
            "schema_version": 1,
            "source_sha": SOURCE_SHA,
            "version": "0.22.0",
            "tag": "v0.22.0",
            "release_commit": "e" * 40,
            "notes_sha256": plan["predicted_release"]["notes_sha256"],
        })

    def test_version_tag_notes_and_head_mismatches_are_rejected(self):
        mutations = (
            ("FLOW_RELEASE_NEW_RELEASE_VERSION", "0.22.1"),
            ("FLOW_RELEASE_NEW_RELEASE_GIT_TAG", "v0.22.1"),
            ("FLOW_RELEASE_NEW_RELEASE_NOTES", "## Different\n\n* drift\n"),
            ("FLOW_RELEASE_NEW_RELEASE_GIT_HEAD", "not-a-sha"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                env = self.publication_environment()
                env[field] = value
                with self.assertRaises(release_gate.ContractError):
                    release_gate.publication_from_environment(valid_plan(), env)

    def test_cli_writes_strict_publication_artifact_and_outputs(self):
        plan = valid_plan()
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            result_path = Path(temp) / "publication.json"
            output_path = Path(temp) / "github-output"
            release_gate.write_plan(plan_path, plan)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "validate-publication", "--plan", str(plan_path), "--output", str(result_path), "--github-output", str(output_path)],
                cwd=REPO_ROOT,
                env={**os.environ, **self.publication_environment()},
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            artifact = json.loads(result_path.read_text())
            release_gate.validate_publication_result(artifact, plan=plan)
            self.assertIn("published=true\n", output_path.read_text())


class PolicyAndCliTests(unittest.TestCase):
    def run_node_full_config(self, mode, repository_url=None):
        env = {**os.environ, "FLOW_RELEASE_MODE": mode}
        if repository_url is None:
            env.pop("FLOW_RELEASE_REPOSITORY_URL", None)
        else:
            env["FLOW_RELEASE_REPOSITORY_URL"] = repository_url
        return subprocess.run(
            ["node", "-e", "console.log(JSON.stringify(require('./release.config.cjs')))"],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True,
        )

    def run_node_config(self, mode=None):
        env = os.environ.copy()
        if mode is None:
            env.pop("FLOW_RELEASE_MODE", None)
        else:
            env["FLOW_RELEASE_MODE"] = mode
        return subprocess.run(
            ["node", "-e", "const c=require('./release.config.cjs'); console.log(JSON.stringify(c.plugins.map(p=>Array.isArray(p)?p[0]:p)))"],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True,
        )

    def test_mode_is_explicit_and_unknown_rejected(self):
        self.assertNotEqual(self.run_node_config().returncode, 0)
        self.assertNotEqual(self.run_node_config("dry-run").returncode, 0)

    def test_preview_excludes_mutating_plugins(self):
        result = self.run_node_config("preview")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [
            "@semantic-release/commit-analyzer",
            "@semantic-release/release-notes-generator",
        ])

    def test_publish_adds_mutating_plugins_after_shared_policy(self):
        preview = json.loads(self.run_node_config("preview").stdout)
        publish_result = self.run_node_config("publish")
        self.assertEqual(publish_result.returncode, 0, publish_result.stderr)
        publish = json.loads(publish_result.stdout)
        self.assertEqual(publish[:2], preview)
        self.assertEqual(publish[2:], [
            "@semantic-release/changelog", "@semantic-release/git", "@semantic-release/github"
        ])

    def test_preview_and_publish_share_exact_policy_structure(self):
        preview = json.loads(self.run_node_full_config("preview").stdout)
        publish = json.loads(self.run_node_full_config("publish").stdout)
        self.assertEqual(preview["branches"], ["main"])
        self.assertEqual(preview["tagFormat"], "v${version}")
        self.assertEqual(preview["plugins"], publish["plugins"][:2])
        rules = preview["plugins"][0][1]["releaseRules"]
        self.assertIn({"breaking": True, "release": "minor"}, rules)
        self.assertIn({"type": "docs", "scope": "framework", "release": "minor"}, rules)
        self.assertIn({"type": "docs", "release": "patch"}, rules)
        self.assertIn({"type": "chore", "scope": "release", "release": False}, rules)
        visible_types = preview["plugins"][1][1]["presetConfig"]["types"]
        self.assertTrue(all(item["hidden"] is False for item in visible_types))

    def test_preview_repository_url_is_canonical_config_not_action_alias(self):
        canonical = "https://github.com/andyconley/flow.git"
        preview = json.loads(self.run_node_full_config("preview", canonical).stdout)
        self.assertEqual(preview["repositoryUrl"], canonical)
        invalid = self.run_node_full_config("preview", "/tmp/local-mirror")
        self.assertNotEqual(invalid.returncode, 0)

    def test_cli_plan_and_validate_emit_controlled_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            plan_path = Path(temp) / "plan.json"
            output_path = Path(temp) / "github-output"
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "plan", "--output", str(plan_path), "--github-output", str(output_path)],
                cwd=REPO_ROOT, env={**os.environ, **release_environment()}, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            digest = release_gate.file_sha256(plan_path)
            self.assertIn(f"plan_digest={digest}\n", output_path.read_text())
            checked = subprocess.run(
                [sys.executable, str(SCRIPT), "validate-plan", "--plan", str(plan_path), "--expected-digest", digest, "--expected-source-sha", SOURCE_SHA],
                cwd=REPO_ROOT, text=True, capture_output=True,
            )
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_cli_digest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.json"
            release_gate.write_plan(path, valid_plan())
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "validate-plan", "--plan", str(path), "--expected-digest", "e" * 64],
                cwd=REPO_ROOT, text=True, capture_output=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("digest mismatch", result.stderr)


if __name__ == "__main__":
    unittest.main()
