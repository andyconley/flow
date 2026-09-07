"""Integration tests for read-only session-model facts and CLI envelopes."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
FLOW = REPO / "cli" / "flow.py"
sys.path.insert(0, str(REPO / "cli"))

import usage_store  # noqa: E402
from model_advice import context_payload, history_evidence, normalize_parent_context  # noqa: E402
from model_policy import merge_session_model_profiles  # noqa: E402
from flowtoml import read_toml  # noqa: E402


def _manifest() -> dict:
    framework = read_toml(REPO / "scaffolds" / "default" / "flow.toml")
    framework["session_model_profiles"] = merge_session_model_profiles(
        framework, None, framework_source="framework.toml", user_source="user.toml"
    )
    return framework


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ModelAdviceFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.manifest = _manifest()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _seed_history(self, store: Path, *, harvested_at: str, fresh_input: int | None = 12) -> None:
        usage_store.ensure_store(store)
        with sqlite3.connect(store) as conn:
            project = str(self.project.resolve())
            session_id = "fixture-session"
            conn.execute(
                "INSERT INTO session (harness, session_id, cwd, source_path) VALUES (?, ?, ?, ?)",
                ("codex", session_id, project, "/tmp/fixture.jsonl"),
            )
            session_row = conn.execute(
                "SELECT id FROM session WHERE harness = ? AND session_id = ?", ("codex", session_id)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO turn_raw (session_row_id, natural_turn_id, turn_seq, is_subagent, ts, model, payload, source_path, source_line_no, collector_version) "
                "VALUES (?, ?, ?, 0, ?, ?, '{}', ?, ?, 1)",
                (session_row, "turn-1", 1, "2026-09-06T12:00:00Z", "gpt-fixture", "/tmp/fixture.jsonl", 1),
            )
            raw_id = conn.execute("SELECT id FROM turn_raw WHERE session_row_id = ?", (session_row,)).fetchone()[0]
            conn.execute(
                "INSERT INTO turn_norm (turn_raw_id, ts, model, is_subagent, fresh_input_tokens, output_tokens, norm_version) "
                "VALUES (?, ?, ?, 0, ?, ?, 1)",
                (raw_id, "2026-09-06T12:00:00Z", "gpt-fixture", fresh_input, 5),
            )
            conn.execute(
                "INSERT INTO harvest (harness, source_path, host_id, last_size, last_offset, last_line_no, harvested_at, collector_version) "
                "VALUES (?, ?, '', 1, 1, 1, ?, 1)",
                ("codex", "/tmp/fixture.jsonl", harvested_at),
            )

    def test_absent_history_does_not_create_a_database_or_parent_directory(self) -> None:
        store = self.root / "absent-home" / "usage.sqlite3"
        before_parent = store.parent.exists()

        evidence = history_evidence(
            runtime="codex", project_root=self.project, store_path=store,
            now=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )

        self.assertFalse(before_parent)
        self.assertEqual(evidence["state"], "absent")
        self.assertFalse(store.exists())
        self.assertFalse(store.parent.exists())
        self.assertIn("not zero usage", evidence["limitations"][0])

    def test_existing_history_is_read_without_schema_content_or_sidecar_mutation(self) -> None:
        store = self.root / "history" / "usage.sqlite3"
        usage_store.ensure_store(store)
        before = _sha256(store)
        before_entries = sorted(path.name for path in store.parent.iterdir())

        evidence = history_evidence(
            runtime="codex", project_root=self.project, store_path=store,
            now=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(evidence["state"], "partial")
        self.assertEqual(evidence["schema_version"], usage_store.SCHEMA_VERSION)
        self.assertEqual(_sha256(store), before)
        self.assertEqual(sorted(path.name for path in store.parent.iterdir()), before_entries)
        self.assertFalse(store.with_name(store.name + "-wal").exists())
        self.assertFalse(store.with_name(store.name + "-shm").exists())

    def test_stale_harvest_remains_visible_when_attributable_rows_exist(self) -> None:
        store = self.root / "history" / "usage.sqlite3"
        self._seed_history(store, harvested_at="2026-09-01T12:00:00Z")

        evidence = history_evidence(
            runtime="codex", project_root=self.project, store_path=store,
            now=datetime(2026, 9, 7, tzinfo=timezone.utc),
        )

        self.assertEqual(evidence["state"], "stale")
        self.assertEqual(evidence["freshness"]["state"], "stale")
        self.assertEqual(evidence["models"][0]["model"], "gpt-fixture")
        self.assertTrue(any("stored evidence" in note for note in evidence["limitations"]))

    def test_older_and_newer_schema_versions_are_incompatible_without_read_repair(self) -> None:
        for version in (usage_store.SCHEMA_VERSION - 1, usage_store.SCHEMA_VERSION + 1):
            store = self.root / f"schema-{version}" / "usage.sqlite3"
            usage_store.ensure_store(store)
            with sqlite3.connect(store) as conn:
                conn.execute(f"PRAGMA user_version = {version}")
            before = _sha256(store)

            evidence = history_evidence(runtime="codex", project_root=self.project, store_path=store)

            self.assertEqual(evidence["state"], "incompatible")
            self.assertEqual(evidence["schema_version"], version)
            self.assertEqual(_sha256(store), before)

    def test_partial_token_evidence_is_visible_without_discarding_attribution(self) -> None:
        store = self.root / "partial" / "usage.sqlite3"
        self._seed_history(store, harvested_at="2026-09-07T11:30:00Z", fresh_input=None)

        evidence = history_evidence(
            runtime="codex", project_root=self.project, store_path=store,
            now=datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(evidence["state"], "partial")
        self.assertEqual(evidence["freshness"]["state"], "fresh")
        self.assertEqual(evidence["models"][0]["partial_turns"], 1)

    def test_caller_supplied_observed_parent_identity_remains_declared(self) -> None:
        supplied = {
            "runtime": "codex",
            "model": "gpt-6-astra",
            "effort": "high",
            "source": "fixture-runtime",
            "provenance": "observed",
            "observed_at": "2026-09-07T12:00:00Z",
            "session_binding": "current-session",
        }
        declared = normalize_parent_context("codex", supplied)
        wrong_runtime = normalize_parent_context(
            "codex", {**supplied, "runtime": "claude"}
        )

        self.assertEqual(declared["state"], "declared")
        self.assertEqual(wrong_runtime["state"], "unknown")
        self.assertIsNone(wrong_runtime["model"])
        self.assertIsNone(wrong_runtime["effort"])
        self.assertIn("different runtime", wrong_runtime["limitations"][0])
        self.assertIn("cannot prove", declared["limitations"][0])

    def test_context_envelope_keeps_mapping_parent_and_history_evidence_separate(self) -> None:
        payload = context_payload(
            self.manifest,
            runtime="codex",
            lane="boot",
            project_root=self.project,
            store_path=self.root / "missing.sqlite3",
        )

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["policy_version"], "session-model-advice-v1")
        self.assertRegex(payload["configuration"]["identity"], r"^[0-9a-f]{64}$")
        self.assertEqual(payload["configuration"]["source"], "effective merged session_model_profiles")
        self.assertEqual(payload["runtime"], {"name": "codex", "provenance": "command_argument"})
        self.assertEqual(set(payload["profiles"]), {"mechanical", "working", "judgment", "demanding"})
        self.assertTrue(all(row["availability"]["state"] == "unverified" for row in payload["profiles"].values()))
        self.assertEqual(payload["parent"]["state"], "unknown")
        self.assertEqual(payload["history"]["state"], "absent")
        self.assertIn("does not select a profile", payload["limitations"][-1])


class ModelAdviceCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.home = self.root / "home"
        (self.home / ".flow").mkdir(parents=True)
        (self.home / ".flow" / "source").symlink_to(REPO, target_is_directory=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_flow(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "HOME": str(self.home), "NO_COLOR": "1"}
        env.pop("FORCE_COLOR", None)
        return subprocess.run(
            [sys.executable, str(FLOW), *args], cwd=self.root, env=env,
            text=True, capture_output=True,
        )

    def test_resolve_json_returns_native_codex_mapping_without_switching(self) -> None:
        result = self.run_flow("model", "resolve", "--runtime", "codex", "--profile", "demanding", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "resolved")
        self.assertEqual(payload["model"], "gpt-6-astra")
        self.assertEqual(payload["effort"], "high")
        self.assertEqual(payload["availability"]["state"], "unverified")

    def test_context_json_records_user_parent_as_declared_and_keeps_absent_history_visible(self) -> None:
        result = self.run_flow(
            "model", "context", "--runtime", "claude", "--lane", "boot",
            "--parent-model", "claude-opus-5", "--parent-effort", "high", "--json",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["parent"]["state"], "declared")
        self.assertEqual(payload["history"]["state"], "absent")
        self.assertFalse((self.home / ".flow" / "usage.db").exists())

    def test_both_generated_runtimes_include_all_five_advice_entry_sources(self) -> None:
        for runtime in ("claude", "codex"):
            sync = self.run_flow("sync", runtime, "--user")
            self.assertEqual(sync.returncode, 0, sync.stderr)
            skill_root = self.home / (".claude/skills" if runtime == "claude" else ".agents/skills")
            for lane in ("boot", "resume", "define", "solution", "plan"):
                content = (skill_root / f"flow-{lane}" / "SKILL.md").read_text()
                self.assertIn("Generated by flow.", content)
                self.assertIn("standards/session-model-advice.md", content)
                self.assertIn(
                    f"flow model context --runtime <active-runtime> --lane {lane} --json", content
                )
                self.assertIn("### Session Model Advice", content)
                self.assertRegex(content, r"(?:no|performs no)\s+switch")
                self.assertIn("advisory", content)


if __name__ == "__main__":
    unittest.main()
