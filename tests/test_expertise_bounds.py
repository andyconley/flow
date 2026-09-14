"""Limits applied before parsing or embedding private expertise inputs."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

import expertise
import expertise_projection as projection
import expertise_service as service
from expertise_json import BoundedJSONError, read_json


class ExpertiseInputBoundsTests(unittest.TestCase):
    def test_corpus_rejects_oversize_and_symlink_before_json_parse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "large.jsonld"
            oversized.write_bytes(b"x" * (1024 * 1024 + 1))
            with self.assertRaises(expertise.ExpertiseError) as raised:
                expertise._read(oversized, "experience")
            self.assertEqual(raised.exception.rule, "invalid-expertise-json")
            alias = root / "alias.jsonld"
            alias.symlink_to(oversized)
            with self.assertRaises(BoundedJSONError):
                read_json(alias, maximum_bytes=1024 * 1024)

    def test_fact_definitions_reject_excess_patterns_and_nested_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "facts.json"
            path.write_text(json.dumps({"schema_version": 1, "revision": "v1", "normalizer_revision": "v1",
                                        "facts": [{"code": "test", "present_any": ["word"] * 33, "absent_any": []}]}))
            with self.assertRaises(service.ExpertiseServiceError):
                service.load_fact_definitions(path)
            path.write_text(json.dumps({"deep": [[[[[[["word"]]]]]]]}))
            with self.assertRaises(BoundedJSONError):
                read_json(path, maximum_bytes=1024, maximum_depth=3)

    def test_projection_rejects_large_dense_batch_before_provider_call(self):
        class Provider:
            calls = 0

            def embed(self, _texts):
                self.calls += 1
                return []

        provider = Provider()
        snapshot = {"entries": [{"_effective_current": True, "abstract": "x" * (1024 * 1024)}]}
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(projection.ExpertiseProjectionError):
                projection.publish(Path(temporary), snapshot, provider)
        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
