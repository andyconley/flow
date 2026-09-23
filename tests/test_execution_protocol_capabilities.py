import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
from execution_contracts import (  # noqa: E402
    DELIVERY_PROTOCOL_VERSION,
    STRUCTURED_VERIFIER_PROTOCOL_VERSION,
    has_structured_verifier_evaluations,
    is_chartered_protocol,
    is_delivery_protocol,
    is_magentic_protocol,
    supported_execution_protocol_versions,
)


class ExecutionProtocolCapabilityTests(unittest.TestCase):
    def test_v8_capabilities_are_named_without_changing_v7_construction(self):
        self.assertIn(STRUCTURED_VERIFIER_PROTOCOL_VERSION, supported_execution_protocol_versions())
        self.assertTrue(is_magentic_protocol(STRUCTURED_VERIFIER_PROTOCOL_VERSION))
        self.assertTrue(is_chartered_protocol(STRUCTURED_VERIFIER_PROTOCOL_VERSION))
        self.assertTrue(is_delivery_protocol(STRUCTURED_VERIFIER_PROTOCOL_VERSION))
        self.assertTrue(has_structured_verifier_evaluations(STRUCTURED_VERIFIER_PROTOCOL_VERSION))
        self.assertFalse(has_structured_verifier_evaluations(DELIVERY_PROTOCOL_VERSION))
