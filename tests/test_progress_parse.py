"""Manager progress reply parsing shared by the runner and Flow (ADR 0018)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "cli"))

from maf_env import MAF_PYTHON, requires_maf  # noqa: E402
from runner_progress import UNPARSABLE_SENTINEL, classify, parse_progress  # noqa: E402

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "manager-progress" / "invalid-escape.txt"


def ledger(**overrides: object) -> dict:
    value = {"is_request_satisfied": {"reason": "not yet", "answer": False},
             "is_in_loop": {"reason": "no", "answer": False},
             "is_progress_being_made": {"reason": "yes", "answer": True},
             "next_speaker": {"reason": "review next", "answer": "local-verifier"},
             "instruction_or_question": {"reason": "needs review", "answer": "Review the diff."}}
    value.update(overrides)
    return value


def corpus() -> dict[str, str]:
    good = json.dumps(ledger())
    return {
        "valid": good,
        "fenced": "Here you go:\n```json\n" + good + "\n```\nDone.",
        "wrapped": "Progress: " + good + " (end)",
        "python_literals": good.replace("false", "False").replace("true", "True"),
        "invalid_escape": FIXTURE.read_text(),
        "escaped_backslash_then_backtick": good.replace("Review the diff.", "Row `a \\\\` b`"),
        "bad_unicode_short": good.replace("Review the diff.", "a \\u12 b"),
        "bad_unicode_letters": good.replace("Review the diff.", "a \\uZZZZ b"),
        "valid_escapes": good.replace("Review the diff.", 'q \\" s \\\\ n \\n u \\u00e9 /\\/'),
        "fenced_object_in_instruction": json.dumps(ledger(instruction_or_question={
            "reason": "r", "answer": "Check ```{\"a\": 1}``` in the table."})),
        "garbage": "I think the local-verifier should go next.",
        "unbalanced": good[:-1],
        "missing_item": json.dumps({key: value for key, value in ledger().items() if key != "is_in_loop"}),
        "non_object_item": json.dumps(ledger(is_in_loop=False)),
        "item_without_answer": json.dumps(ledger(next_speaker={"reason": "x"})),
        "list_top_level": "[" + good + "]",
    }


class ProgressParseTests(unittest.TestCase):
    def test_recorded_live_reply_is_repaired_and_selects_the_verifier(self) -> None:
        parsed = parse_progress(FIXTURE.read_text())
        self.assertTrue(parsed.repaired)
        self.assertEqual(parsed.value["next_speaker"]["answer"], "local-verifier")
        self.assertEqual(json.loads(parsed.canonical), parsed.value)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(FIXTURE.read_text())

    def test_valid_escapes_are_untouched_and_never_marked_repaired(self) -> None:
        text = corpus()["valid_escapes"]
        parsed = parse_progress(text)
        self.assertFalse(parsed.repaired)
        self.assertEqual(parsed.value, json.loads(text))

    def test_repair_doubles_only_invalid_backslashes(self) -> None:
        cases = {
            "escaped_backslash_then_backtick": "Row `a \\` b`",
            "bad_unicode_short": "a \\u12 b",
            "bad_unicode_letters": "a \\uZZZZ b",
        }
        for name, expected in cases.items():
            with self.subTest(name):
                parsed = parse_progress(corpus()[name])
                self.assertTrue(parsed.repaired or name == "escaped_backslash_then_backtick")
                self.assertEqual(parsed.value["instruction_or_question"]["answer"], expected)

    def test_classification(self) -> None:
        expected = {
            "valid": "parsed", "fenced": "parsed", "wrapped": "parsed", "python_literals": "parsed",
            "invalid_escape": "repaired", "valid_escapes": "parsed",
            # MAF's fence rule wins even inside a string, so this is retried, as MAF would.
            "fenced_object_in_instruction": "unparsable", "garbage": "unparsable", "unbalanced": "unparsable",
            "missing_item": "unparsable", "non_object_item": "unparsable",
            # The first balanced object is the ledger, as for MAF.
            "item_without_answer": "unparsable", "list_top_level": "parsed",
        }
        for name, want in expected.items():
            with self.subTest(name):
                self.assertEqual(classify(corpus()[name]), want)

    def test_sentinel_has_no_object(self) -> None:
        self.assertNotIn("{", UNPARSABLE_SENTINEL)
        self.assertEqual(classify(UNPARSABLE_SENTINEL), "unparsable")


PARITY_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from agent_framework_orchestrations._magentic import MagenticProgressLedger, _coerce_model, _extract_json
from runtime.maf_runner.progress_parse import UNPARSABLE_SENTINEL, parse_progress
results = {}
for name, text in json.loads(sys.stdin.read()).items():
    parsed = parse_progress(text)
    handed = parsed.canonical if parsed.value is not None else UNPARSABLE_SENTINEL
    try:
        maf_value = _extract_json(handed)
        _coerce_model(MagenticProgressLedger, maf_value)
        maf_ok, same = True, maf_value == parsed.value
    except Exception:
        maf_ok, same = False, False
    results[name] = {"flow_ok": parsed.value is not None, "maf_ok": maf_ok, "same": same}
print(json.dumps(results))
"""


@requires_maf
class ProgressParseMafParityTests(unittest.TestCase):
    def test_maf_reads_what_flow_hands_it_exactly_as_flow_decided(self) -> None:
        result = subprocess.run([MAF_PYTHON, "-c", PARITY_SCRIPT, str(REPO_ROOT)], input=json.dumps(corpus()),
                                capture_output=True, text=True, check=True, cwd=REPO_ROOT)
        for name, outcome in json.loads(result.stdout).items():
            with self.subTest(name):
                self.assertEqual(outcome["maf_ok"], outcome["flow_ok"])
                if outcome["flow_ok"]:
                    self.assertTrue(outcome["same"])


if __name__ == "__main__":
    unittest.main()
