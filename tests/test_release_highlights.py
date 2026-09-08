import json
import os
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
NODE_DRIVER = r"""
const plugin = require('./scripts/release-highlights.cjs');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', async () => {
  try {
    const result = await plugin.generateNotes({}, JSON.parse(input));
    process.stdout.write(result);
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
});
"""


class ReleaseHighlightsTests(unittest.TestCase):
    def render(self, commits):
        return subprocess.run(
            ["node", "-e", NODE_DRIVER],
            cwd=REPO_ROOT,
            input=json.dumps({"commits": commits}),
            text=True,
            capture_output=True,
            env=os.environ.copy(),
            check=False,
        )

    def test_archive_outcomes_render_in_commit_order_before_ordinary_notes(self):
        commits = [
            {
                "hash": "a" * 40,
                "message": (
                    "feat(archive): add retrieval\n\n"
                    "Release-Note: Archive retrieval now searches current and ancestor decisions.\n"
                    "Refs: #24"
                ),
            },
            {"hash": "b" * 40, "message": "fix: internal repair without a highlight"},
            {
                "hash": "c" * 40,
                "message": (
                    "docs(archive): explain failure behavior\n\n"
                    "Release-Note: Retrieval failures leave Flow and archive closure usable."
                ),
            },
        ]
        result = self.render(commits)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "### Highlights\n\n"
            "- Archive retrieval now searches current and ancestor decisions.\n"
            "- Retrieval failures leave Flow and archive closure usable.\n",
        )
        combined = result.stdout + "\n### Features\n\n- add retrieval\n"
        self.assertLess(combined.index("### Highlights"), combined.index("### Features"))

    def test_no_trailer_returns_empty_output(self):
        result = self.render([{"message": "fix: preserve ordinary notes"}])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_duplicate_values_are_preserved(self):
        result = self.render([
            {"message": "feat: one\n\nRelease-Note: Same outcome"},
            {"message": "feat: two\n\nRelease-Note: Same outcome"},
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("- Same outcome"), 2)

    def test_utf8_limit_counts_bytes(self):
        accepted = self.render([{"message": f"feat: exact\n\nRelease-Note: {'€' * 80}"}])
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        rejected = self.render([{"message": f"feat: long\n\nRelease-Note: {'€' * 81}"}])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("243 UTF-8 bytes", rejected.stderr)

    def test_malformed_trailers_fail_generation(self):
        cases = {
            "empty": "feat: x\n\nRelease-Note:",
            "heading": "feat: x\n\nRelease-Note: ## Internal heading",
            "control": "feat: x\n\nRelease-Note: contains\ttab",
            "leading-control": "feat: x\n\nRelease-Note:\tleading tab",
            "trailing-control": "feat: x\n\nRelease-Note: trailing tab\t",
            "unicode-line-separator": "feat: x\n\nRelease-Note: first\u2028second",
            "html-comment": "feat: x\n\nRelease-Note: <!-- hides later notes",
            "bidi-override": "feat: x\n\nRelease-Note: safe\u202etxt",
            "arabic-letter-mark": "feat: x\n\nRelease-Note: safe\u061ctxt",
            "left-to-right-mark": "feat: x\n\nRelease-Note: safe\u200etxt",
            "multiline": "feat: x\n\nRelease-Note: first line\ncontinued line",
            "duplicate": "feat: x\n\nRelease-Note: one\nRelease-Note: two",
        }
        for name, message in cases.items():
            with self.subTest(name=name):
                result = self.render([{"hash": "d" * 40, "message": message}])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Release-Note", result.stderr)

    def test_body_text_is_not_mistaken_for_a_trailer(self):
        result = self.render([{
            "message": (
                "docs: discuss release notes\n\n"
                "Release-Note: is the supported token in a body paragraph.\n\n"
                "Refs: #9"
            )
        }])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_other_valid_trailers_and_their_continuations_are_allowed(self):
        result = self.render([{
            "message": (
                "feat!: change contract\n\n"
                "Release-Note: The capability now follows the new contract.\n"
                "BREAKING CHANGE: callers must pass a project id\n"
                "  and a source digest\n"
                "Co-Authored-By: Example <example@example.com>"
            )
        }])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("new contract", result.stdout)


if __name__ == "__main__":
    unittest.main()
