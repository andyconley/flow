"""Replay the frozen synthetic comparison against the production BM25 scorer.

This checks rank order transfer only, not production response sizes or lane judgment.
"""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
import archive_model as model
import archive_query as query

FIXTURES = Path(__file__).parent / "fixtures" / "archive"
DISTANCE = {"project": 0, "parent": 1, "grandparent": 2}


def record(doc):
    identity = {"source_id": str(uuid.uuid5(uuid.NAMESPACE_URL, doc["overlay"])), "work_id": doc["id"].split("/", 1)[1]}
    source = {**identity, "path": "runs/fixture/archive.md", "selector": "heading:decision:1", "digest": "0" * 64}
    fields = {name: {"state": "unknown", "value": None, "sources": [], "reason": "fixture rank input only"} for name in model.FIELDS}
    for field, fixture_key in (("decision", "decision"), ("applies_when", "conditions"), ("rationale", "rationale")):
        fields[field] = {"state": "known", "value": doc[fixture_key], "sources": [source]}
    return {"qualified_id": model.qualified(identity), "fixture_id": doc["id"], "identity": identity, "distance": DISTANCE[doc["overlay"]], "envelope": {"schema_version": 1, "identity": identity, "generated": {"extractor_version": 1, "source_digest": "0" * 64, "fields": fields}, "declarations": {}, "refinement": None, "provenance": {"origin": "synthetic_comparison"}}}


class FrozenRankerTests(unittest.TestCase):
    def test_all_frozen_postfilter_rank_orders_match_production(self):
        corpus_bytes = (FIXTURES / "ranker-corpus.json").read_bytes()
        corpus = json.loads(corpus_bytes)
        expected = json.loads((FIXTURES / "bm25-orders.json").read_text())
        self.assertEqual(hashlib.sha256(corpus_bytes).hexdigest(), expected["source_fixture_sha256"])
        for case in corpus["cases"]:
            with self.subTest(case=case["id"]):
                filters = case["filters"]
                eligible = [d for d in corpus["documents"]
                            if d["overlay"] in filters.get("sources", list(DISTANCE))
                            and (filters.get("include_superseded", False) or not d["superseded"])
                            and all(d.get(key) == filters[key] for key in ("component", "work_type") if key in filters)
                            and ("since" not in filters or d["closed_at"] >= filters["since"])]
                actual = [r["fixture_id"] for r in query.rank([record(d) for d in eligible], case["query"])]
                self.assertEqual(actual, expected["orders"][case["id"]])


if __name__ == "__main__":
    unittest.main()
