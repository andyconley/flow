import copy
from pathlib import Path
import sys
import unittest
import uuid

CLI = Path(__file__).resolve().parents[1] / "cli"
sys.path.insert(0, str(CLI))

from archive_legacy_model import (effective_disposition, make_review, validate_chain,
    validate_legacy_envelope, validate_review)
from archive_model import digest, validate_envelope


SOURCE_ID = "11111111-1111-4111-8111-111111111111"
WORK_ID = "legacy"
SHA = "a" * 64


def pointer(name):
    return {"source_id": SOURCE_ID, "work_id": WORK_ID, "path": "runs/legacy/" + name,
            "selector": "heading:work closed:1", "digest": SHA}


def request(action="approve", action_id="22222222-2222-4222-8222-222222222222"):
    outcome, closure = pointer("outcome.md"), pointer("closure.md")
    value = {
        "schema_version": 1, "identity": {"source_id": SOURCE_ID, "work_id": WORK_ID},
        "action_id": action_id, "action": action, "reviewer": "andy",
        "reviewer_is_author": True, "reason": "reviewed retained evidence",
        "expected_base_fingerprint": "b" * 64,
        "closed_at": {"state": "unknown"},
        "evidence": [
            {"kind": "local", "role": "final_outcome", "source": outcome, "explanation": "final outcome"},
            {"kind": "local", "role": "closure_evidence", "source": closure, "explanation": "accepted closure"},
        ],
        "selected_final_outcome_sources": [outcome],
        "field_selections": [],
        "closure_assertion": "The recorded final outcome was accepted and closed.",
    }
    if action in {"reject", "unresolved", "withdraw"}:
        value["evidence"] = []
        value["selected_final_outcome_sources"] = []
        value.pop("closure_assertion")
    return value


class LegacyModelTests(unittest.TestCase):
    def test_positive_review_requires_typed_evidence_and_selected_final_source(self):
        valid = request()
        validate_review(valid)
        missing = copy.deepcopy(valid)
        missing["evidence"] = missing["evidence"][:1]
        with self.assertRaisesRegex(ValueError, "closure evidence"):
            validate_review(missing)
        external = copy.deepcopy(valid)
        external["evidence"][0]["kind"] = "external_capture"
        with self.assertRaisesRegex(ValueError, "URL"):
            validate_review(external)
        external["evidence"][0].update({"url": "https://example.test/closure", "captured_at": "2026-09-07T00:00:00Z"})
        validate_review(external)

    def test_known_date_is_bound_to_closure_evidence(self):
        valid = request()
        valid["closed_at"] = {"state": "known", "value": "2026-01-02T03:04:05Z", "source": pointer("closure.md")}
        validate_review(valid)
        invalid = copy.deepcopy(valid)
        invalid["closed_at"]["source"] = pointer("outcome.md")
        with self.assertRaisesRegex(ValueError, "closure evidence"):
            validate_review(invalid)

    def test_chain_is_digest_linked_and_old_approval_cannot_be_current(self):
        approval = make_review(request(), review_id="33333333-3333-4333-8333-333333333333", previous_revision_digest=None, recorded_at="2026-09-07T00:00:00Z")
        withdrawal_request = request("withdraw", "44444444-4444-4444-8444-444444444444")
        withdrawal_request["expected_base_fingerprint"] = "c" * 64
        withdrawal = make_review(withdrawal_request, review_id=approval["review_id"], previous_revision_digest=approval["revision_digest"], recorded_at="2026-09-07T01:00:00Z")
        chain = validate_chain(withdrawal, {approval["revision_digest"]: approval})
        self.assertEqual([item["action"] for item in chain], ["approve", "withdraw"])
        self.assertEqual(effective_disposition(withdrawal), "withdrawn")
        corrupted = copy.deepcopy(approval)
        corrupted["reason"] = "altered"
        with self.assertRaisesRegex(ValueError, "digest"):
            validate_chain(withdrawal, {approval["revision_digest"]: corrupted})

    def test_schema_versions_are_exclusive(self):
        canonical = {"schema_version": 1, "identity": {"source_id": SOURCE_ID, "work_id": WORK_ID},
                     "declarations": {}, "generated": None, "refinement": None, "provenance": {"origin": "test"},
                     "legacy_review": {}}
        with self.assertRaisesRegex(ValueError, "schema 2"):
            validate_envelope(canonical)
        review = make_review(request(), review_id="33333333-3333-4333-8333-333333333333", previous_revision_digest=None, recorded_at="2026-09-07T00:00:00Z")
        legacy = {"schema_version": 2, "identity": review["identity"], "declarations": {"supersedes": [], "selections": []},
                  "legacy_review": review, "generated": None, "refinement": None,
                  "provenance": {"origin": "reviewed_legacy"}}
        validate_legacy_envelope(legacy)
        validate_envelope(legacy)


    def test_strict_timestamp_and_unknown_schema_inputs(self):
        for timestamp in ['2026-09-07 12:00:00+00:00', '2026-09-07T12:00:00', '2026-09-07Z12:00:00Z']:
            value = request()
            value['evidence'][0].update(kind='external_capture', url='https://example.invalid/capture', captured_at=timestamp)
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                validate_review(value)
        for schema in [True, 1.0, 2, None, []]:
            value = request(); value['schema_version'] = schema
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                validate_review(value)
        for relationship in [1, 0, {}, [], None]:
            value = request(); value['reviewer_is_author'] = relationship
            with self.subTest(relationship=relationship), self.assertRaises(ValueError):
                validate_review(value)
