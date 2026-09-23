"""Compatibility behavior for historical chartered v6 delivery records."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))

from legacy_delivery import LegacyDeliveryError, inspect_legacy_delivery, refuse_legacy_execution  # noqa: E402


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "delivery-compatibility"


class LegacyDeliveryInspectionTests(unittest.TestCase):
    def test_valid_v6_is_readable_but_has_no_execution_or_resume_capability(self) -> None:
        report = inspect_legacy_delivery(FIXTURES / "valid-v6.json")

        self.assertTrue(report["readable"])
        self.assertFalse(report["executable"])
        self.assertFalse(report["resumable"])
        self.assertEqual(report["compatibility"], "v6-inspection-only")
        self.assertEqual(report["integrity"]["status"], "passed")
        self.assertEqual(report["normalized"]["attempt_id"], "legacy-attempt")
        self.assertIn("raw_sha256", report)

    def test_malformed_v6_keeps_a_structured_parse_diagnostic_and_is_ineligible(self) -> None:
        report = inspect_legacy_delivery(FIXTURES / "malformed-v6.json")

        self.assertFalse(report["readable"])
        self.assertFalse(report["executable"])
        self.assertFalse(report["resumable"])
        self.assertEqual(report["diagnostics"][0]["code"], "legacy_json_invalid")
        self.assertIn("raw_sha256", report)

    def test_digest_mismatch_remains_readable_but_integrity_failed_and_ineligible(self) -> None:
        report = inspect_legacy_delivery(FIXTURES / "digest-mismatch-v6.json")

        self.assertTrue(report["readable"])
        self.assertFalse(report["executable"])
        self.assertFalse(report["resumable"])
        self.assertEqual(report["integrity"]["status"], "failed")
        self.assertIn("legacy_charter_digest_mismatch", {item["code"] for item in report["diagnostics"]})

    def test_non_v6_current_record_gets_an_actionable_compatibility_diagnostic(self) -> None:
        report = inspect_legacy_delivery(FIXTURES / "current-v7.json")

        self.assertTrue(report["readable"])
        self.assertFalse(report["executable"])
        self.assertEqual(report["diagnostics"][0]["code"], "legacy_protocol_unexpected")

    def test_execute_and_resume_refuse_even_an_integrity_clean_v6_record(self) -> None:
        report = inspect_legacy_delivery(FIXTURES / "valid-v6.json")

        for operation in ("execute", "resume"):
            with self.subTest(operation=operation), self.assertRaisesRegex(LegacyDeliveryError, f"cannot {operation}"):
                refuse_legacy_execution(report, operation)

    def test_refusal_api_rejects_an_undefined_operation(self) -> None:
        with self.assertRaisesRegex(ValueError, "execute or resume"):
            refuse_legacy_execution({}, "dispatch")


if __name__ == "__main__":
    unittest.main()
