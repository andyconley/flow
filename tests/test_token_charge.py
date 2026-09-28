"""Charged tokens (ADR 0020, AC9): the pure charge, gate and block functions, on captured real usage.

Fixture values are the exact ones recorded in research/spikes.md: S1 (a Codex
``last_token_usage``) and S2/S3 (the v8-live-validation-3 Claude editor and
managers).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
from execution_contracts import (attempt_token_charges, charge, normalized_charge, token_gate,  # noqa: E402
                                 token_maximum, token_usage_block, usage_values_valid)

U = 100_000
CLAUDE_EDITOR = {"input_tokens": 20, "output_tokens": 4024, "cache_creation_input_tokens": 78332,
                 "cache_read_input_tokens": 598695}
CLAUDE_MANAGER = {"cache_creation_input_tokens": 3834, "cache_read_input_tokens": 3397, "input_tokens": 2,
                  "output_tokens": 2253}
CODEX = {"input_tokens": 23537, "cached_input_tokens": 18176, "cache_write_input_tokens": 0, "output_tokens": 119,
         "reasoning_output_tokens": 56, "total_tokens": 23656}
ENVELOPE = {"manager": {"provider": "claude"},
            "limits": {"max_lineage_tokens": 200_000, "token_tranche": 100_000, "unobserved_send_tokens": U}}


class ChargeTableTests(unittest.TestCase):
    def test_the_charge_of_every_row_shape(self):
        cases = [
            ("claude editor (disjoint cache fields)", "completed", "claude", {"usage": CLAUDE_EDITOR}, (82_376, 598_695, True)),
            ("claude manager", "completed", "claude", {"usage": CLAUDE_MANAGER}, (6_089, 3_397, True)),
            ("codex (cached is a subset of input)", "completed", "codex", {"usage": CODEX}, (23537 - 18176 + 119, 18_176, True)),
            ("codex with a nested extra key", "completed", "codex", {"usage": {**CODEX, "future": {"x": 1}}},
             (5_480, 18_176, True)),
            ("unknown row", "unknown", "claude", None, (U, 0, True)),
            ("started row", "started", "codex", None, (U, 0, True)),
            ("failed without usage", "failed", "claude", {"output": "x"}, (U, 0, False)),
            ("completed, no usage", "completed", "claude", {"usage": None}, (U, 0, False)),
            ("completed, missing output_tokens", "completed", "claude", {"usage": {"input_tokens": 3}}, (U, 0, False)),
            # RS1 (approved): an unrecognised shape is never cheaper than it reported.
            ("renamed counters, large input", "completed", "claude", {"usage": {"input_tokens": 250_000}},
             (250_000, 0, False)),
            ("codex total above the charge", "completed", "codex", {"usage": {"total_tokens": 300_000, "tokens_in": 1}},
             (300_000, 0, False)),
            ("nested shape, nothing readable", "completed", "claude", {"usage": {"totals": {"input": 900_000}}},
             (U, 0, False)),
            ("codex cached above input", "completed", "codex",
             {"usage": {"input_tokens": 1, "cached_input_tokens": 2, "output_tokens": 1}}, (U, 0, False)),
            ("allowed", "allowed", "claude", None, (0, 0, True)),
            ("denied", "denied", "codex", None, (0, 0, True)),
            ("not_dispatched", "not_dispatched", "claude", None, (0, 0, True)),
            ("ollama is never charged", "completed", "ollama", {"usage": {"prompt_eval_count": 3533, "eval_count": 153}},
             (0, 0, True)),
        ]
        for label, status, provider, result, (charged, cache_read, recognised) in cases:
            with self.subTest(label):
                item = charge(status, provider, result, U)
                self.assertEqual((item["charged"], item["cache_read"], item["recognised"]), (charged, cache_read, recognised))

    def test_reasoning_is_inside_output_and_counted_once(self):
        # S1: total_tokens = input + output, and reasoning <= output.
        self.assertEqual(CODEX["total_tokens"], CODEX["input_tokens"] + CODEX["output_tokens"])
        self.assertEqual(normalized_charge("codex", CODEX), (23537 - 18176 + 119, 18176))

    def test_known_counters_must_be_valid_and_extras_are_ignored(self):
        self.assertTrue(usage_values_valid(None))
        self.assertTrue(usage_values_valid({**CODEX, "service_tier": "standard", "nested": {"a": [1]}}))
        for bad in ({"input_tokens": -1}, {"output_tokens": "1"}, {"eval_count": True}, ["input_tokens"]):
            with self.subTest(bad=bad):
                self.assertFalse(usage_values_valid(bad))


class AttemptChargeTests(unittest.TestCase):
    def rows(self):
        actions = [{"status": "completed", "request": {"provider": "claude"}, "result": {"usage": CLAUDE_EDITOR}},
                   {"status": "completed", "request": {"provider": "ollama"},
                    "result": {"usage": {"prompt_eval_count": 3533, "eval_count": 153}}},
                   {"status": "unknown", "request": {"provider": "codex"}, "result": None}]
        calls = [{"status": "completed", "result": {"usage": CLAUDE_MANAGER}},
                 {"status": "denied", "result": None}]
        return actions, calls

    def test_attempt_totals_split_observed_unobserved_and_reported_only(self):
        totals = attempt_token_charges(ENVELOPE, *self.rows())
        self.assertEqual(totals, {"observed_charged": 82_376 + 6_089, "unobserved_sends": 1, "unobserved_charged": U,
                                  "unrecognised_usage": 0, "cache_read_total": 598_695 + 3_397,
                                  "verifier_tokens": 3_686, "charged": 82_376 + 6_089 + U})

    def test_an_unpaid_manager_is_never_charged(self):
        envelope = {**ENVELOPE, "manager": {"provider": "ollama"}}
        actions, calls = self.rows()
        self.assertEqual(attempt_token_charges(envelope, [], calls)["charged"], 0)

    def test_the_v8_live_validation_3_lineage_charges_133898(self):
        managers = [{"cache_creation_input_tokens": w, "cache_read_input_tokens": r, "input_tokens": 2, "output_tokens": o}
                    for w, r, o in ((3834, 3397, 2253), (5285, 4353, 684), (6891, 4353, 1378), (9077, 4353, 1342),
                                    (10152, 4353, 541), (9594, 4353, 479))]
        totals = attempt_token_charges(ENVELOPE, [{"status": "completed", "request": {"provider": "claude"},
                                                   "result": {"usage": CLAUDE_EDITOR}}],
                                       [{"status": "completed", "result": {"usage": usage}} for usage in managers])
        self.assertEqual(totals["charged"], 133_898)


class GateTests(unittest.TestCase):
    def test_maximum_and_units(self):
        self.assertEqual(token_maximum(ENVELOPE, 0), 200_000)
        self.assertEqual(token_maximum(ENVELOPE, 2), 400_000)
        self.assertEqual(token_gate(199_999, ENVELOPE, 0), (False, 0))
        self.assertEqual(token_gate(200_000, ENVELOPE, 0), (True, 1))
        self.assertEqual(token_gate(299_999, ENVELOPE, 0), (True, 1), "one tranche clears a shortfall below a tranche")
        self.assertEqual(token_gate(300_000, ENVELOPE, 0), (True, 2), "a whole tranche over needs two")
        self.assertEqual(token_gate(300_000, ENVELOPE, 1), (True, 1))

    def test_block_recomputes_and_reports_overshoot(self):
        actions, calls = AttemptChargeTests().rows()
        block = token_usage_block(ENVELOPE, actions, calls, predecessor_charged=50_000, tranches_granted=0)
        self.assertEqual(block["charged_total"], 82_376 + 6_089 + U + 50_000)
        self.assertEqual(block["overshoot"], block["charged_total"] - 200_000)
        self.assertEqual(set(block), {"unit", "maximum", "tranches_granted", "observed_charged", "unobserved_sends",
                                      "unobserved_charged", "unrecognised_usage", "predecessor_charged", "charged_total",
                                      "overshoot", "cache_read_total", "verifier_tokens"})
        self.assertEqual(block["unit"], "charged_v1")




class RecordTimeToleranceTests(unittest.TestCase):
    """A4: an unknown extra usage key never turns a paid call into an uncertain one."""

    def test_codex_keeps_a_nested_extra_key_and_rejects_a_bad_counter(self):
        import json as _json
        from codex_worker import CodexWorkerError, _parse_events

        def stream(usage):
            events = [{"type": "thread.started", "thread_id": "thread-1"},
                      {"type": "item.completed", "item": {"type": "agent_message", "text": "Done"}},
                      {"type": "turn.completed", "usage": usage}]
            return ("\n".join(_json.dumps(item) for item in events) + "\n").encode()

        result = _parse_events(stream({**CODEX, "future_breakdown": {"audio": 3}}), "gpt-test")
        self.assertEqual(result["usage"]["future_breakdown"], {"audio": 3})
        self.assertEqual(charge("completed", "codex", result, U)["charged"], 5_480)
        with self.assertRaises(CodexWorkerError):
            _parse_events(stream({**CODEX, "output_tokens": -1}), "gpt-test")

    def test_a_manager_observation_keeps_a_string_extra_key(self):
        import hashlib
        import tempfile
        from execution_ledger import ExecutionLedger
        from tests.test_expansion_ledger import manager_request, v8

        with tempfile.TemporaryDirectory() as temporary:
            ledger = ExecutionLedger(Path(temporary) / "ledger.sqlite")
            env = v8(manager="claude", attempt="tolerance")
            ledger.create_attempt(env)
            request = manager_request(env, 1)
            decision = ledger.decide_manager_call(env, request, generation=1)
            self.assertTrue(ledger.consume_manager_grant(request["call_id"], decision["grant_id"], generation=1))
            ledger.observe_manager_response(request["call_id"], {
                "status": "completed", "output": "x", "output_sha256": hashlib.sha256(b'"x"').hexdigest(),
                "usage": {"input_tokens": 1, "output_tokens": 2, "service_tier": "standard"}}, generation=1)
            [call] = ledger.snapshot("tolerance")["manager_calls"]
            self.assertEqual(call["status"], "completed")


if __name__ == "__main__":
    unittest.main()
