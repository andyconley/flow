"""Version six contracts preserve the fixed Magentic profile separately."""

from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from execution_contracts import ContractError, validate_envelope, validate_receipt
from test_magentic_execution_contract import envelope


def chartered() -> dict:
    env = envelope()
    env["execution_protocol_version"] = 6
    env["allowed_paths"] = ["cli/example.py"]
    env["roster"][0]["capabilities"] = ["read"]
    env["roster"][1]["capabilities"] = ["read", "edit"]
    env["job_contract"] = {
        "task": "Repair the scoped example.",
        "baseline": {"kind": "clean", "diff_sha256": hashlib.sha256(b"").hexdigest()},
        "read_paths": ["cli/example.py", "tests/test_example.py"],
        "write_paths": ["cli/example.py"],
        "test": {"argv": ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_example.py"], "timeout_seconds": 120},
        "producer_instance_ids": [env["roster"][1]["instance_id"]],
        "verifier_instance_ids": [env["roster"][0]["instance_id"]],
    }
    return env


def structured_verifier() -> dict:
    env = chartered()
    env["execution_protocol_version"] = 8
    env["limits"] = {**env["limits"], "max_runtime_seconds": 300, "max_verifier_calls": 2}
    env.update({
        "shaper_contract_digest": "e" * 64,
        "delivery_charter_digest": "f" * 64,
        "handoff_digest": "0" * 64,
        "delivery_lead_claim_digest": "1" * 64,
        "delivery_lead_claim": {"lead_id": "delivery-lead", "generation": 1},
    })
    return env


class CharteredContractTests(unittest.TestCase):
    def test_v6_envelope_accepts_explicit_generic_job(self) -> None:
        validate_envelope(chartered())
        validate_envelope(envelope())

    def test_v6_refuses_changed_scope_capability_and_unsafe_test(self) -> None:
        for mutate in (
            lambda env: env["job_contract"]["write_paths"].append("cli/other.py"),
            lambda env: env["job_contract"]["read_paths"].append("../other"),
            lambda env: env["roster"][1].update(capabilities=["read"]),
            lambda env: env["job_contract"]["producer_instance_ids"].append("unknown"),
            lambda env: env["job_contract"]["test"].update(argv=["sh", "-c", "true"]),
            lambda env: env["job_contract"]["test"].update(argv=["python3", "-c", "print(1)"]),
        ):
            with self.subTest(mutate=mutate):
                env = copy.deepcopy(chartered())
                mutate(env)
                with self.assertRaises(ContractError):
                    validate_envelope(env)

    def test_v5_envelope_keeps_legacy_roster_shape(self) -> None:
        env = envelope()
        env["roster"][0]["capabilities"] = ["read"]
        with self.assertRaises(ContractError):
            validate_envelope(env)

    def test_v8_envelope_requires_a_sealed_verifier_allowance(self) -> None:
        validate_envelope(structured_verifier())
        for value in (0, 3):
            with self.subTest(value=value):
                env = structured_verifier()
                env["limits"]["max_verifier_calls"] = value
                with self.assertRaisesRegex(ContractError, "limits"):
                    validate_envelope(env)


if __name__ == "__main__":
    unittest.main()
