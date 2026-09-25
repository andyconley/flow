"""The MAF-gated tests take their interpreter only from FLOW_MAF_PYTHON."""

import re
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
MAF_GATED = ("test_delivery_gateway.py", "test_maf_continuation_supervisor.py", "test_maf_delivery_lead.py",
             "test_maf_post_resolution_continuation.py", "test_maf_recovery.py")


class MafInterpreterConfigurationTests(unittest.TestCase):
    def test_no_test_file_hardcodes_the_maf_interpreter_path(self):
        hardcoded = [path.name for path in TESTS.glob("*.py")
                     if path.name != Path(__file__).name
                     and re.search(r"/private/tmp/flow-maf|flow-maf-runtime-spike", path.read_text())]
        self.assertEqual(hardcoded, [])
        for name in MAF_GATED:
            with self.subTest(module=name):
                self.assertIn("from maf_env import", (TESTS / name).read_text())


if __name__ == "__main__":
    unittest.main()
