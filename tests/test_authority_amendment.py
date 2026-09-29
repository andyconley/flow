import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))

from delivery_contracts import DeliveryContractError  # noqa: E402
from runstate import _apply_authority_amendment  # noqa: E402
from tests.shaper_intent_fixture import shaper_intent  # noqa: E402


class AuthorityAmendmentTests(unittest.TestCase):
    def test_explicit_handoff_authority_is_projected(self):
        amended = _apply_authority_amendment(
            shaper_intent(),
            {"authority_amendment": {"allowed_lifecycle_operations": ["handoff_to_review"]}},
        )
        self.assertEqual(amended["allowed_lifecycle_operations"], ["handoff_to_review"])

    def test_unknown_lifecycle_operation_is_rejected(self):
        with self.assertRaisesRegex(DeliveryContractError, "unsupported or duplicate"):
            _apply_authority_amendment(
                shaper_intent(),
                {"authority_amendment": {"allowed_lifecycle_operations": ["accept_review"]}},
            )

    def test_authority_amendment_rejects_extra_fields(self):
        with self.assertRaisesRegex(DeliveryContractError, "must contain only"):
            _apply_authority_amendment(
                shaper_intent(),
                {"authority_amendment": {"allowed_lifecycle_operations": [], "accept_review": True}},
            )


if __name__ == "__main__":
    unittest.main()
