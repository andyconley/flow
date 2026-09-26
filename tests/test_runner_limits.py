"""One source for the runner ceilings, and the v8 envelope's headroom projection."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))
sys.path.insert(0, str(REPO_ROOT))
import runner_limits  # noqa: E402
from execution_contracts import ContractError, expansion_headroom, validate_envelope  # noqa: E402
from runtime.maf_runner import limits as runtime_limits  # noqa: E402
from tests.test_chartered_execution_contract import chartered, structured_verifier  # noqa: E402


class RunnerLimitsTests(unittest.TestCase):
    def test_cli_shim_loads_the_runner_module_file(self):
        self.assertEqual(Path(runtime_limits.__file__).resolve(), runner_limits.LIMITS_PATH)
        for name in ("MAX_MANAGER_CALLS", "MAX_MANAGER_ROUNDS", "MAX_ACTIONS", "MAX_VERIFIER_CALLS",
                     "MAX_CONCURRENT", "MAX_REPLANS"):
            self.assertEqual(getattr(runner_limits, name), getattr(runtime_limits, name), name)

    def test_runner_reads_its_ceilings_from_the_shared_module(self):
        source = (REPO_ROOT / "runtime" / "maf_runner" / "delivery_lead.py").read_text()
        self.assertIn("from runtime.maf_runner.limits import", source)
        for literal in ("manager_call > 12", "manager_round > 6", "action_number > 6", "max_round_count=6"):
            self.assertNotIn(literal, source)


class EnvelopeHeadroomTests(unittest.TestCase):
    def envelope(self, **headroom):
        env = structured_verifier()
        env["limits"].update({"max_delegations": 3, "max_paid_worker_calls": 2, "max_manager_calls": 8,
                              "max_manager_rounds": 4, "max_verifier_calls": 1})
        if headroom:
            env["expansion_headroom"] = headroom
        return env

    def test_absent_headroom_means_zero_and_valid_projection_is_accepted(self):
        env = self.envelope()
        validate_envelope(env)
        self.assertEqual(set(expansion_headroom(env).values()), {0})
        env = self.envelope(delegations=3, paid_worker_calls=1, verifier_calls=1, manager_calls=4, manager_rounds=2)
        validate_envelope(env)
        self.assertEqual(expansion_headroom(env)["manager_calls"], 4)

    def test_projection_beyond_a_ceiling_or_malformed_is_refused(self):
        cases = {
            "manager calls": {"manager_calls": 5},
            "manager rounds": {"manager_rounds": 3},
            "delegations": {"delegations": 4},
            "verifier": {"verifier_calls": 2},
            "paid outgrows delegations": {"paid_worker_calls": 2},
            "unknown key": {"replans": 1},
            "negative": {"delegations": -1},
            "all zero": {"delegations": 0},
        }
        for label, headroom in cases.items():
            with self.subTest(label), self.assertRaises(ContractError):
                validate_envelope(self.envelope(**headroom))

    def test_headroom_is_v8_only(self):
        env = chartered()
        env["expansion_headroom"] = {"delegations": 1}
        with self.assertRaises(ContractError):
            validate_envelope(env)


if __name__ == "__main__":
    unittest.main()
