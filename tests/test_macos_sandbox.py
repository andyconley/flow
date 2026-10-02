from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))

from macos_sandbox import confined_argv  # noqa: E402


@unittest.skipUnless(sys.platform == "darwin", "macOS sandbox contract")
class MacOSSandboxTests(unittest.TestCase):
    def test_staged_worker_cannot_read_sibling_user_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            private_home = root / "home"
            workspace.mkdir()
            private_home.mkdir()
            allowed = workspace / "allowed.txt"
            denied = root / "denied.txt"
            allowed.write_text("allowed")
            denied.write_text("secret")
            script = ("from pathlib import Path; import sys; "
                      "print(Path(sys.argv[1]).read_text()); "
                      "print(Path(sys.argv[2]).read_text())")
            argv = confined_argv(
                [sys.executable, "-c", script, str(allowed), str(denied)],
                workspace=workspace, private_home=private_home,
            )
            result = subprocess.run(argv, cwd=workspace, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if "sandbox_apply: Operation not permitted" in result.stderr:
                self.skipTest("outer process sandbox forbids nested sandbox-exec")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("allowed", result.stdout)
            self.assertNotIn("secret", result.stdout)

    def test_profile_names_only_staging_home_and_system_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            argv = confined_argv([sys.executable, "-c", "pass"], workspace=workspace,
                                 private_home=private_home)
            profile = argv[2]
            self.assertIn(str(workspace), profile)
            self.assertIn(str(private_home), profile)
            self.assertNotIn(str(root) + '\")', profile)

    def test_profile_allows_only_the_resolved_provider_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace, private_home = root / "workspace", root / "home"
            workspace.mkdir()
            private_home.mkdir()
            executable = root / "provider"
            executable.write_bytes(b"provider")
            with patch("macos_sandbox.shutil.which", return_value=str(executable)):
                argv = confined_argv(["provider"], workspace=workspace, private_home=private_home)
            profile = argv[2]
            self.assertIn(f'(require-not (literal "{executable.resolve()}"))', profile)
            self.assertNotIn(f'(require-not (subpath "{root}"))', profile)


if __name__ == "__main__":
    unittest.main()
