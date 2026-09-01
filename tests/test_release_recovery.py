"""Integration tests for release drift, reconciliation, and public readback."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import release_gate  # noqa: E402
import release_reconcile  # noqa: E402
import release_verify_published  # noqa: E402
sys.path.pop(0)


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _plan(source_sha: str, previous_sha: str) -> dict:
    notes = "## Features\n\n* gated release\n"
    return release_gate.plan_from_environment({
        "FLOW_RELEASE_REQUIRED": "true",
        "FLOW_RELEASE_TYPE": "minor",
        "FLOW_RELEASE_VERSION": "0.22.0",
        "FLOW_RELEASE_TAG": "v0.22.0",
        "FLOW_RELEASE_NOTES": notes,
        "FLOW_RELEASE_ENTRY_COUNT": "1",
        "FLOW_RELEASE_SOURCE_SHA": source_sha,
        "FLOW_RELEASE_PREVIOUS_VERSION": "0.21.0",
        "FLOW_RELEASE_PREVIOUS_TAG": "v0.21.0",
        "FLOW_RELEASE_PREVIOUS_COMMIT": previous_sha,
        "FLOW_RELEASE_REPOSITORY": "andyconley/flow",
        "FLOW_RELEASE_WORKFLOW": "Release",
        "FLOW_RELEASE_RUN_ID": "1",
        "FLOW_RELEASE_RUN_ATTEMPT": "1",
        "FLOW_RELEASE_CREATED_AT": "2026-09-01T12:00:00Z",
    })


class RemoteBaselineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.work = root / "work"
        self.remote = root / "remote.git"
        _git(root, "init", "--bare", str(self.remote))
        _git(root, "init", "-b", "main", str(self.work))
        _git(self.work, "config", "user.name", "Flow Tests")
        _git(self.work, "config", "user.email", "flow@example.com")
        (self.work / "file").write_text("previous\n", encoding="utf-8")
        _git(self.work, "add", "file")
        _git(self.work, "commit", "-m", "feat: previous")
        self.previous = _git(self.work, "rev-parse", "HEAD")
        _git(self.work, "tag", "v0.21.0")
        (self.work / "file").write_text("source\n", encoding="utf-8")
        _git(self.work, "commit", "-am", "feat: source")
        self.source = _git(self.work, "rev-parse", "HEAD")
        _git(self.work, "remote", "add", "origin", str(self.remote))
        _git(self.work, "push", "origin", "main", "--tags")
        self.plan = _plan(self.source, self.previous)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_exact_remote_baseline_passes(self) -> None:
        result = release_gate.verify_remote_baseline(self.plan, self.work, "origin")
        self.assertEqual(result["main_sha"], self.source)
        self.assertTrue(result["candidate_tag_absent"])

    def test_moved_main_is_rejected(self) -> None:
        (self.work / "file").write_text("moved\n", encoding="utf-8")
        _git(self.work, "commit", "-am", "fix: moved")
        _git(self.work, "push", "origin", "main")
        with self.assertRaisesRegex(release_gate.ContractError, "remote main moved"):
            release_gate.verify_remote_baseline(self.plan, self.work, "origin")

    def test_existing_candidate_tag_is_rejected(self) -> None:
        _git(self.work, "tag", "v0.22.0")
        _git(self.work, "push", "origin", "v0.22.0")
        with self.assertRaisesRegex(release_gate.ContractError, "already exists"):
            release_gate.verify_remote_baseline(self.plan, self.work, "origin")


class PublicationReconciliationTests(unittest.TestCase):
    def _plan_file(self, root: Path) -> Path:
        path = root / "plan.json"
        release_gate.write_plan(path, _plan("a" * 40, "b" * 40))
        return path

    def test_clean_and_partial_readbacks_have_stable_classification(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            plan = self._plan_file(Path(raw))
            with unittest.mock.patch.object(
                release_reconcile, "_remote_ref", side_effect=["a" * 40, None, None]
            ), unittest.mock.patch.object(
                release_reconcile,
                "_public_release",
                return_value={"exists": False, "url": "", "tag": "", "body_sha256": ""},
            ):
                clean = release_reconcile.reconcile(plan, "https://example.invalid/repo.git", "owner/repo")
            self.assertEqual(clean["classification"], "publication-failed-without-observed-write")

            with unittest.mock.patch.object(
                release_reconcile, "_remote_ref", side_effect=["c" * 40, "d" * 40]
            ), unittest.mock.patch.object(
                release_reconcile,
                "_public_release",
                return_value={"exists": True, "url": "https://example/release", "tag": "v0.22.0", "body_sha256": "e" * 64},
            ):
                partial = release_reconcile.reconcile(plan, "https://example.invalid/repo.git", "owner/repo")
            self.assertEqual(partial["classification"], "partial-publication-observed")
            self.assertEqual(partial["inspection_errors"], [])

    def test_inspection_error_is_retained_instead_of_lost(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            plan = self._plan_file(Path(raw))
            with unittest.mock.patch.object(
                release_reconcile, "_remote_ref", side_effect=release_gate.ContractError("network down")
            ), unittest.mock.patch.object(
                release_reconcile, "_public_release", side_effect=release_gate.ContractError("api down")
            ):
                result = release_reconcile.reconcile(plan, "https://example.invalid/repo.git", "owner/repo")
            self.assertEqual(result["classification"], "inspection-incomplete")
            self.assertTrue(result["inspection_errors"])


class PublicReleaseReadbackTests(unittest.TestCase):
    def test_release_fixture_requires_tag_url_and_nonempty_notes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            fixture = Path(raw) / "release.json"
            fixture.write_text(json.dumps({
                "tag_name": "v0.22.0",
                "body": "## Features\n\n* gated release\n",
                "html_url": "https://github.com/andyconley/flow/releases/tag/v0.22.0",
            }), encoding="utf-8")
            body, url = release_verify_published._release_body("andyconley/flow", "v0.22.0", fixture)
            self.assertIn("gated release", body)
            self.assertTrue(url.endswith("v0.22.0"))
            payload = json.loads(fixture.read_text())
            payload["body"] = ""
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(release_gate.ContractError, "notes are empty"):
                release_verify_published._release_body("andyconley/flow", "v0.22.0", fixture)


if __name__ == "__main__":
    unittest.main()
