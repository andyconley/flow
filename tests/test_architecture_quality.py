"""Candidate-bound checks for the selected-function quality collector."""

from __future__ import annotations

import os
import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.architecture_evidence.adapters.coverage_json import collect_quality

TOOLS_PYTHON = os.environ.get("FLOW_ARCHITECTURE_PYTHON")
PINS = {"radon": "6.0.1", "coverage": "7.14.0", "mutmut": "3.7.0"}


class ArchitectureQualityTests(unittest.TestCase):
    def test_external_coverage_and_workspace_are_rejected(self) -> None:
        result = collect_quality(
            Path(__file__).parents[1],
            {
                "quality": {
                    "enabled": True,
                    "python_executable": TOOLS_PYTHON,
                    "coverage_json": "/tmp/stale.json",
                    "mutation_workspace": "/tmp/stale",
                }
            },
            Path(tempfile.mkdtemp()),
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("not candidate-bound", result["gaps"][0])

    def test_disabled_quality_is_explicitly_unsupported(self) -> None:
        result = collect_quality(
            Path(__file__).parents[1],
            {"quality": {"enabled": False}},
            Path(tempfile.mkdtemp()),
        )
        self.assertEqual(result["status"], "unsupported")

    def test_stale_source_hash_is_rejected_before_collection(self) -> None:
        result = collect_quality(
            Path(__file__).parents[1],
            {
                "quality": {
                    "enabled": True,
                    "python_executable": TOOLS_PYTHON,
                    "versions": PINS,
                    "source_sha256": "0" * 64,
                    "mutation_target": "stale",
                }
            },
            Path(tempfile.mkdtemp()),
        )
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("source_sha256", result["gaps"][0])

    @unittest.skipUnless(
        TOOLS_PYTHON, "set FLOW_ARCHITECTURE_PYTHON for pinned tool integration"
    )
    def test_fresh_collection_binds_coverage_and_mutation_to_candidate(self) -> None:
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            result = collect_quality(
                root,
                {
                    "quality": {
                        "enabled": True,
                        "required": True,
                        "python_executable": TOOLS_PYTHON,
                        "versions": PINS,
                        "mutation_target": "cli.jsonl_watermark.x_read_new_lines__mutmut_28",
                    }
                },
                Path(directory) / "raw",
            )
        self.assertEqual(result["status"], "available")
        record = result["records"][0]
        self.assertEqual(record["path"], "cli/jsonl_watermark.py")
        self.assertEqual(
            record["source_sha256"],
            hashlib.sha256((root / record["path"]).read_bytes()).hexdigest(),
        )
        self.assertEqual(
            record["mutation"]["source_input_sha256"], record["source_sha256"]
        )
        self.assertEqual(
            record["mutation"]["target_loaded_path"], "cli/jsonl_watermark.py"
        )
        self.assertIn(
            record["mutation"]["selected_status"], {"killed", "survived", "timeout"}
        )
        self.assertTrue(
            any(
                item["id"] == record["mutation"]["selected_mutant"]
                for item in record["mutation"]["records"]
            )
        )
        self.assertTrue(
            any(item["path"] == "coverage.json" for item in result["artifacts"])
        )
